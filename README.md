# judge-calibration

[![CI](https://github.com/mpuodziukas-labs/judge-calibration/actions/workflows/ci.yml/badge.svg)](https://github.com/mpuodziukas-labs/judge-calibration/actions/workflows/ci.yml)

Quickstart: `bash scripts/verify.sh` prints `GREEN` (details: [Reproduce](#reproduce)).

Measures how far a pairwise judge agrees with human labels, and gates on floors. No model calls and no network in CI: judges are deterministic stand-ins whose verdicts are replayed from `cassettes.json`.

Human labels: 500 rows from a CC-BY-4.0 human-preference set (see DATA.md). Label counts: a 184, b 164, tie 152.

## Honesty Statement

The human labels are real: 500 rows from a CC-BY-4.0 human-preference set described in DATA.md. The judges are not real: they are deterministic stand-ins written for this repo and replayed from cassettes. The numbers describe how those stand-ins agree with those labels and what the gate floors pin. They say nothing about any real model judge. See Limitations.

## What the judges are

Stand-ins written for this repo (`scripts/make_cassettes.py`), not real model outputs.

- `length_biased`: picks the longer answer, tie if lengths are within 5 percent, random pick for 8 percent of calls (hash-seeded).
- `position_biased`: says A for 60 percent of calls, tie for 5 percent, otherwise picks the longer answer (hash-seeded per order).
- `rubric`: scores each answer on 5 binary items (3 or more sentences, list structure, 40 to 400 words, no refusal phrase, 3 or more prompt keywords reused); higher score wins, equal is a tie.

## Measured results (500 rows)

| judge | kappa | agreement | Wilson 95% CI | swap flips | swap consistency | agree when longer won | agree when shorter won |
|---|---|---|---|---|---|---|---|
| length_biased | 0.278 | 0.528 | 0.484 to 0.571 | 37 | 0.926 | 0.958 (n=261) | 0.047 (n=86) |
| position_biased | 0.104 | 0.424 | 0.381 to 0.468 | 359 | 0.282 | 0.644 (n=261) | 0.326 (n=86) |
| rubric | 0.221 | 0.480 | 0.437 to 0.524 | 0 | 1.000 | 0.628 (n=261) | 0.058 (n=86) |

Chance agreement on a 3-way label is about 0.33. Judge-vs-judge confusion tables (3 pairs, counts) and agreement by relative length difference are in `results.json`.

Floors in `thresholds.json` sit just under these measured values. They are regression floors for the stand-ins, not a claim about what a usable judge needs.

## Metrics

- Cohen's kappa over labels a, b, tie.
- Raw agreement with a Wilson 95% interval.
- Position-swap: each pair is judged in both orders; a flip is a different underlying choice after mapping slots back.
- Verbosity: agreement split by whether the human-preferred answer was the longer one (ties excluded), and by relative length difference.
- Blind check: verdicts must be identical when human labels are rotated; a judge that reads the label fails the gate with exit 1.

## Gate and exit codes

`python3 -P judgecal.py` writes `results.json` and exits 0 (pass), 1 (floor breach or label leak), 2 (cassette miss).

## Reproduce

    bash scripts/verify.sh

Needs python3, pytest and shellcheck. It runs the tests, the gate twice (outputs compared with `cmp`), the selftest (`selftest 5/5`: four planted defects and one clean control) and shellcheck, then prints GREEN.

## Limitations

- The judges are stand-ins. Results say nothing about any real model judge.
- Rows are not independent: the same question and answer pair can appear under several annotators, so the Wilson interval is narrower than the true uncertainty.
- Subset is filtered to short answers (1200 characters or fewer) with no brand names, which skews toward simpler prompts and removes the long-answer region where length bias matters most.
- Human labels have their own noise; no inter-annotator agreement is computed here.
- Ties are 30 percent of labels, which pulls agreement down for judges that rarely say tie.
- Turn 2 prompts omit turn 1 context.
- The selftest uses small hand-computed fixtures; it checks the formulas and the blind check, not every possible defect.
