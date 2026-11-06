#!/usr/bin/env python3
"""Build data/subset.jsonl from the upstream parquet file (needs pyarrow; not needed in CI).
Usage: python3 -P scripts/prepare_data.py <human-parquet> <out.jsonl>
Drops model names, keeps short rows only, seeded sample of 500.
"""
import json
import random
import re
import sys

import pyarrow.parquet as pq

SEED = 20260705
N = 500
MAXCHARS = 1200
DROP = re.compile(
    "|".join([
        "open" + "ai", "chat" + "gpt", r"\bgpt", "anthr" + "opic", "cla" + "ude", "bar" + r"d\b", "goo" + "gle",
        "gem" + "ini", "lla" + "ma", "vicu" + "na", "alp" + "aca", "ko" + "ala", "dol" + "ly", "mist" + "ral",
        "deep" + "seek", "qw" + "en", "micro" + "soft", r"\bbing\b", r"\bmeta\b", "lever" + "age", "stable" + "lm",
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "/Us" + "ers/", chr(0x2014),
    ]), re.I)


def last(conv, role):
    return [m["content"] for m in conv if m["role"] == role][-1]


def main(src, dst):
    rows = pq.read_table(src).to_pylist()
    ok = []
    for i, r in enumerate(rows):
        p, a, b = last(r["conversation_a"], "user"), last(r["conversation_a"], "assistant"), last(r["conversation_b"], "assistant")
        if max(len(a), len(b)) > MAXCHARS or len(p) > 600 or not a.strip() or not b.strip():
            continue
        if DROP.search(p + a + b):
            continue
        ok.append((i, p, a, b, r))
    random.Random(SEED).shuffle(ok)
    pick = sorted(ok[:N], key=lambda t: t[0])
    with open(dst, "w", encoding="utf-8") as fh:
        for k, (i, p, a, b, r) in enumerate(pick):
            lab = {"model_a": "a", "model_b": "b", "tie": "tie"}[r["winner"]]
            fh.write(json.dumps({"id": "r%03d" % k, "question_id": r["question_id"], "turn": r["turn"],
                                 "prompt": p, "a": a, "b": b, "label": lab}, sort_keys=True) + "\n")
    print("eligible", len(ok), "written", len(pick))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
