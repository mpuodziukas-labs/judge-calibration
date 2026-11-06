#!/usr/bin/env bash
# Runs every check. Prints GREEN only if all pass.
set -eu
set -o pipefail

ROOT="$PWD"
[ -f "$ROOT/judgecal.py" ] || { echo "run from the repo root"; exit 1; }
OUT="$ROOT/.verify"
mkdir -p "$OUT"


pytest -q
python3 -P "$ROOT/judgecal.py" --out "$OUT/one.json"
python3 -P "$ROOT/judgecal.py" --out "$OUT/two.json"
cmp "$OUT/one.json" "$OUT/two.json"
cmp "$OUT/one.json" "$ROOT/results.json"
echo "results.json byte-identical across runs"
python3 -P "$ROOT/judgecal.py" --selftest | tail -1
shellcheck scripts/verify.sh
echo "shellcheck rc 0"
echo GREEN
