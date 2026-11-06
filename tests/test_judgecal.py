import hashlib
import json
import os
import subprocess
import sys

import pytest

import judgecal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(*args):
    return subprocess.run(
        [sys.executable, "-P", os.path.join(ROOT, "judgecal.py"), *args],
        cwd=ROOT, capture_output=True, text=True)


def test_kappa_known_answer():
    h = ["a", "a", "b", "b", "tie", "a", "b", "tie", "a", "b"]
    j = ["a", "b", "b", "b", "tie", "a", "a", "tie", "a", "tie"]
    assert judgecal.kappa(h, j) == pytest.approx(0.36 / 0.66, abs=1e-9)


def test_wilson_known_answer():
    lo, hi = judgecal.wilson(9, 10)
    assert lo == pytest.approx(0.5958, abs=5e-4)
    assert hi == pytest.approx(0.9821, abs=5e-4)


def test_swap_flips_counts_disagreements():
    assert judgecal.swap_flips(["a", "b", "tie", "a"], ["a", "a", "tie", "b"]) == 2


def test_normalize_maps_slots_back():
    assert judgecal.normalize("A", "orig") == "a"
    assert judgecal.normalize("A", "swap") == "b"
    assert judgecal.normalize("tie", "swap") == "tie"


def test_verbosity_split():
    rows = [
        {"a": "x" * 100, "b": "x" * 10, "label": "a"},
        {"a": "x" * 10, "b": "x" * 100, "label": "a"},
    ]
    v = judgecal.verbosity(rows, ["a", "a"])
    assert v["longer_wins"]["n"] == 1 and v["longer_wins"]["agreement"] == 1.0
    assert v["shorter_wins"]["n"] == 1 and v["shorter_wins"]["agreement"] == 1.0


def test_gate_pass_writes_results_deterministically(tmp_path):
    o1, o2 = tmp_path / "1.json", tmp_path / "2.json"
    assert run("--out", str(o1)).returncode == 0
    assert run("--out", str(o2)).returncode == 0
    assert o1.read_bytes() == o2.read_bytes()
    res = json.loads(o1.read_bytes())
    assert res["n_rows"] > 0 and set(res["judges"]) == {"length_biased", "position_biased", "rubric"}


def test_gate_breach_exits_1(tmp_path):
    th = tmp_path / "th.json"
    th.write_text(json.dumps({"rubric": {"min_kappa": 0.99}}))
    r = run("--thresholds", str(th), "--out", str(tmp_path / "o.json"))
    assert r.returncode == 1 and "BREACH" in r.stdout


def test_cassette_miss_exits_2(tmp_path):
    c = json.load(open(os.path.join(ROOT, "cassettes.json")))
    first = next(iter(c["judges"]["rubric"]))
    del c["judges"]["rubric"][first]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(c))
    r = run("--cassettes", str(p), "--out", str(tmp_path / "o.json"))
    assert r.returncode == 2 and "CASSETTE MISS" in r.stderr


def test_selftest_5_of_5():
    r = run("--selftest")
    assert r.returncode == 0 and "selftest 5/5" in r.stdout


def test_cassettes_regenerate_identically(tmp_path):
    out = tmp_path / "c.json"
    r = subprocess.run([sys.executable, "-P", os.path.join(ROOT, "scripts", "make_cassettes.py"), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    assert out.read_bytes() == open(os.path.join(ROOT, "cassettes.json"), "rb").read()


def test_subset_size_and_hash_recorded():
    p = os.path.join(ROOT, "data", "subset.jsonl")
    raw = open(p, "rb").read()
    n = sum(1 for _ in open(p))
    assert 0 < n <= 500
    assert hashlib.sha256(raw).hexdigest() in open(os.path.join(ROOT, "DATA.md")).read()


def test_hygiene_forbidden_strings_absent():
    forbidden = [
        chr(0x2014), "/Us" + "ers/", "lever" + "age",
        "open" + "ai", "anthr" + "opic", "chat" + "gpt", "gp" + "t-", "cla" + "ude",
        "gem" + "ini", "lla" + "ma", "mist" + "ral", "vicu" + "na", "alp" + "aca",
        "ko" + "ala",
    ]
    ipv4 = __import__("re").compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    seen = 0
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in (".pytest_cache", "__pycache__", ".git")]
        for f in files:
            seen += 1
            text = open(os.path.join(d, f), encoding="utf-8").read()
            low = text.lower()
            for s in forbidden:
                assert s not in low, (f, s)
            assert not ipv4.search(text), f
    assert seen >= 8
