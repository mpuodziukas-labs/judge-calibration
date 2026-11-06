#!/usr/bin/env python3
"""Judge calibration gate. Replays judge verdicts from cassettes, compares them
with human labels, enforces floors from thresholds.json. No network, no model calls.

Exit codes: 0 pass, 1 floor breach or selftest failure, 2 cassette miss.
"""
import argparse
import itertools
import json
import math
import os
import sys

LABELS = ("a", "b", "tie")
JUDGES = ("length_biased", "position_biased", "rubric")
HERE = os.path.dirname(os.path.abspath(__file__))


class CassetteMiss(Exception):
    pass


class LeakError(Exception):
    pass


def kappa(h, j):
    n = len(h)
    po = sum(x == y for x, y in zip(h, j)) / n
    pe = sum((h.count(k) / n) * (j.count(k) / n) for k in LABELS)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def normalize(v, order):
    if v == "tie":
        return "tie"
    if order == "orig":
        return v.lower()
    return "b" if v == "A" else "a"


def swap_flips(orig, swp):
    return sum(x != y for x, y in zip(orig, swp))


def view(row):
    """What a judge may see: never the human label."""
    return {"id": row["id"], "prompt": row["prompt"], "a": row["a"], "b": row["b"]}


def replay(cassettes, judge, v, order):
    key = v["id"] + "|" + order
    try:
        return cassettes["judges"][judge][key]
    except KeyError:
        raise CassetteMiss(judge + " " + key)


def collect(rows, cassettes, relabel=None):
    """Per judge: normalized verdicts in original and swapped order."""
    out = {}
    for judge in JUDGES:
        o, s = [], []
        for i, row in enumerate(rows):
            r = dict(row)
            if relabel is not None:
                r["label"] = relabel[i]
            v = view(r)
            o.append(normalize(replay(cassettes, judge, v, "orig"), "orig"))
            s.append(normalize(replay(cassettes, judge, v, "swap"), "swap"))
        out[judge] = (o, s)
    return out


def blind_check(rows, cassettes):
    """Verdicts must not change when the human labels are rotated."""
    base = collect(rows, cassettes)
    rot = [rows[(i + 1) % len(rows)]["label"] for i in range(len(rows))]
    if collect(rows, cassettes, relabel=rot) != base:
        raise LeakError("judge verdicts depend on the human label")
    return base


def rel_diff(row):
    la, lb = len(row["a"]), len(row["b"])
    return abs(la - lb) / max(1, min(la, lb))


def _agree(rows, verdicts):
    n = len(rows)
    k = sum(r["label"] == v for r, v in zip(rows, verdicts))
    return {"n": n, "agreement": round(k / n, 6) if n else None}


def verbosity(rows, verdicts):
    """Agreement split by which response was longer. Ties are excluded from the split."""
    longer, shorter, bins = [], [], {"lt25pct": [], "25to100pct": [], "ge100pct": []}
    for r, v in zip(rows, verdicts):
        if r["label"] == "tie" or len(r["a"]) == len(r["b"]):
            continue
        a_longer = len(r["a"]) > len(r["b"])
        (longer if (r["label"] == "a") == a_longer else shorter).append((r, v))
        d = rel_diff(r)
        bins["lt25pct" if d < 0.25 else "25to100pct" if d < 1.0 else "ge100pct"].append((r, v))

    def agg(pairs):
        return _agree([p[0] for p in pairs], [p[1] for p in pairs])

    res = {"longer_wins": agg(longer), "shorter_wins": agg(shorter),
           "by_length_diff": {k: agg(v) for k, v in bins.items()}}
    la, sa = res["longer_wins"]["agreement"], res["shorter_wins"]["agreement"]
    res["gap"] = None if la is None or sa is None else round(la - sa, 6)
    return res


def confusion(x, y):
    return {p: {q: sum(1 for i, j in zip(x, y) if i == p and j == q) for q in LABELS} for p in LABELS}


def evaluate(rows, cassettes):
    coll = blind_check(rows, cassettes)
    human = [r["label"] for r in rows]
    n = len(rows)
    res = {"n_rows": n, "label_counts": {k: human.count(k) for k in LABELS}, "judges": {}}
    for judge, (o, s) in coll.items():
        k = sum(x == y for x, y in zip(human, o))
        lo, hi = wilson(k, n)
        flips = swap_flips(o, s)
        res["judges"][judge] = {
            "kappa": round(kappa(human, o), 6),
            "agreement": round(k / n, 6),
            "agreement_ci95": [round(lo, 6), round(hi, 6)],
            "swap_flips": flips,
            "swap_consistency": round(1 - flips / n, 6),
            "verbosity": verbosity(rows, o),
        }
    res["judge_vs_judge"] = {a + "__" + b: confusion(coll[a][0], coll[b][0])
                             for a, b in itertools.combinations(JUDGES, 2)}
    return res


def check_floors(res, th):
    breaches = []
    for judge, f in sorted(th.items()):
        m = res["judges"][judge]
        got = {"min_kappa": m["kappa"], "min_agreement_lower": m["agreement_ci95"][0],
               "min_swap_consistency": m["swap_consistency"], "max_verbosity_gap": m["verbosity"]["gap"]}
        for name, floor in sorted(f.items()):
            val = got[name]
            bad = val < floor if name.startswith("min_") else abs(val) > floor
            if bad:
                breaches.append("BREACH %s %s=%s floor=%s" % (judge, name, val, floor))
    return breaches


def load_rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---- selftest: 4 planted defects + 1 clean control, checked by known-answer oracles ----

def _oracle(mod):
    """Return the set of failed check names for a (possibly mutated) module namespace."""
    bad = set()
    h = ["a", "a", "b", "b", "tie", "a", "b", "tie", "a", "b"]
    j = ["a", "b", "b", "b", "tie", "a", "a", "tie", "a", "tie"]
    if abs(mod["kappa"](h, j) - 0.36 / 0.66) > 1e-9:
        bad.add("kappa")
    lo, hi = mod["wilson"](9, 10)
    if abs(lo - 0.5958) > 5e-4 or abs(hi - 0.9821) > 5e-4:
        bad.add("wilson")
    if mod["swap_flips"](["a", "b", "tie", "a"], ["a", "a", "tie", "b"]) != 2:
        bad.add("swap_flips")
    rows = [{"id": "r%d" % i, "prompt": "p", "a": "x", "b": "y", "label": lab}
            for i, lab in enumerate(["a", "b", "tie", "a", "b", "tie"])]
    cas = {"judges": {jn: {} for jn in JUDGES}}
    for r in rows:
        for jn in JUDGES:
            cas["judges"][jn][r["id"] + "|orig"] = "A"
            cas["judges"][jn][r["id"] + "|swap"] = "B"
    try:
        mod["blind_check"](rows, cas)
    except LeakError:
        bad.add("leak")
    return bad


def selftest():
    g = globals()

    def off_by_one(h, j):
        n = len(h)
        po = sum(x == y for x, y in zip(h, j)) / n
        pe = sum(h.count(k) * j.count(k) for k in LABELS) / ((n - 1) ** 2)
        return (po - pe) / (1.0 - pe)

    def normal_ci(k, n, z=1.96):
        p = k / n
        hw = z * math.sqrt(p * (1 - p) / n)
        return p - hw, p + hw

    def leaky_view(row):
        return dict(row)

    def leaky_replay(cassettes, judge, v, order):
        return {"a": "A", "b": "B", "tie": "tie"}[v["label"]]

    cases = [
        ("kappa_off_by_one", {"kappa": off_by_one}, "kappa"),
        ("swap_flips_uncounted", {"swap_flips": lambda o, s: 0}, "swap_flips"),
        ("wilson_replaced_by_normal", {"wilson": normal_ci}, "wilson"),
        ("label_leak", {"view": leaky_view, "replay": leaky_replay}, "leak"),
        ("clean_control", {}, None),
    ]
    ok = 0
    for name, patch, expect in cases:
        saved = {k: g[k] for k in patch}
        g.update(patch)
        try:
            bad = _oracle(g)
        finally:
            g.update(saved)
        good = (expect in bad) if expect else (not bad)
        ok += good
        print("%s %s %s" % (name, "detected" if expect else "clean", "ok" if good else "FAIL"))
    print("selftest %d/%d" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default=os.path.join(HERE, "data", "subset.jsonl"))
    ap.add_argument("--cassettes", default=os.path.join(HERE, "cassettes.json"))
    ap.add_argument("--thresholds", default=os.path.join(HERE, "thresholds.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "results.json"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    rows = load_rows(a.data)
    if not rows:
        print("no rows", file=sys.stderr)
        return 1
    with open(a.cassettes, encoding="utf-8") as fh:
        cas = json.load(fh)
    with open(a.thresholds, encoding="utf-8") as fh:
        th = json.load(fh)
    try:
        res = evaluate(rows, cas)
    except CassetteMiss as e:
        print("CASSETTE MISS: " + str(e), file=sys.stderr)
        return 2
    except LeakError as e:
        print("LEAK: " + str(e), file=sys.stderr)
        return 1
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
        fh.write("\n")
    breaches = check_floors(res, th)
    for b in breaches:
        print(b)
    print("gate %s: %d rows, %d breaches" % ("RED" if breaches else "PASS", len(rows), len(breaches)))
    return 1 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
