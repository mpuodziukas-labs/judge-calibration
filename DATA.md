# Data

Source: MT-Bench human judgments (pairwise expert votes on two model answers per question).

- URL: https://huggingface.co/datasets/lmsys/mt_bench_human_judgments
- File: data/human-00000-of-00001-25f4910818759289.parquet
- License: CC-BY-4.0 (read from the dataset card metadata on the hub API, tag `license:cc-by-4.0`). Attribution: the MT-Bench authors (arXiv 2306.05685).
- sha256 of the upstream parquet file: `4877bc46a40929f4082c3c79593700fb897b1d6c7f4c473032694a01322f5769` (3355 rows, 738612 bytes)

This is real human data. It is not SYNTHETIC.

## Subset committed here

- File: `data/subset.jsonl`, 500 rows
- sha256: `81134ce485c5ad4de40f88e9062d08fd93f1ad1abae4bad88bac4ac85c46bafa`
- Built by `scripts/prepare_data.py` (seed 20260705): rows whose answers are 1200 characters or fewer, prompt 600 or fewer, and no brand names or dash characters that the repo hygiene test rejects. 1822 of 3355 rows were eligible; 500 sampled.
- Fields kept: id, question_id, turn, prompt (last user message), a, b (last assistant message of each side), label (a, b or tie).
- Model names and the annotator id are dropped. For turn 2 rows the prompt is the second user message only, without the first turn.
- Several rows can share a question and differ by annotator or model pair, so rows are not independent (see README, Limitations).
