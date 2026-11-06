#!/usr/bin/env python3
"""Generate cassettes.json: deterministic stand-in judges, replayed by judgecal.py.
Usage: python3 -P scripts/make_cassettes.py [out.json]
Verdicts are slot-based: "A", "B" or "tie" for the order shown ("orig" or "swap").
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = "cassette-v1"


def u(*parts):
    h = hashlib.sha256("|".join((SEED,) + parts).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2.0 ** 64


def by_length(sa, sb):
    la, lb = len(sa), len(sb)
    if abs(la - lb) / max(la, lb, 1) < 0.05:
        return "tie"
    return "A" if la > lb else "B"


def length_biased(jid, order, prompt, sa, sb):
    if u("len", jid, order) < 0.08:
        return "A" if u("lenpick", jid, order) < 0.5 else "B"
    return by_length(sa, sb)


def position_biased(jid, order, prompt, sa, sb):
    x = u("pos", jid, order)
    if x < 0.6:
        return "A"
    if x < 0.65:
        return "tie"
    return by_length(sa, sb)


REFUSAL = ("i'm sorry", "i am sorry", "as an ai", "i cannot", "i can't")


def rubric_score(prompt, text):
    low = text.lower()
    words = re.findall(r"[a-z']+", low)
    keys = {w for w in re.findall(r"[a-z]{5,}", prompt.lower())}
    s = 0
    s += len(re.findall(r"[.!?](\s|$)", text)) >= 3
    s += bool(re.search(r"^\s*(\d+[.)]|[-*])\s", text, re.M))
    s += 40 <= len(words) <= 400
    s += not any(r in low for r in REFUSAL)
    s += len(keys & set(words)) >= 3
    return s


def rubric(jid, order, prompt, sa, sb):
    x, y = rubric_score(prompt, sa), rubric_score(prompt, sb)
    return "tie" if x == y else ("A" if x > y else "B")


STANDINS = {"length_biased": length_biased, "position_biased": position_biased, "rubric": rubric}


def build(data_path):
    rows = [json.loads(line) for line in open(data_path, encoding="utf-8") if line.strip()]
    out = {"meta": {"note": "deterministic stand-ins, not real model outputs", "seed": SEED}, "judges": {}}
    for name, fn in STANDINS.items():
        d = {}
        for r in rows:
            d[r["id"] + "|orig"] = fn(r["id"], "orig", r["prompt"], r["a"], r["b"])
            d[r["id"] + "|swap"] = fn(r["id"], "swap", r["prompt"], r["b"], r["a"])
        out["judges"][name] = d
    return out


if __name__ == "__main__":
    dst = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "cassettes.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(build(os.path.join(HERE, "data", "subset.jsonl")), fh, indent=0, sort_keys=True)
        fh.write("\n")
