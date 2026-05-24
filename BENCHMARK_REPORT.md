# Benchmark Report

## Reproduction

`python scripts\bench\run_agent_comparison.py --methods random,heuristic --datasets hospital,flights,beers --seeds 3 --output-json eval\results\agent_comparison.json`

## Configuration

- Methods: random, heuristic
- Datasets: hospital, flights, beers
- Seeds: 3
- Free-tier quota units: `max(llm_calls / 1000, (prompt_tokens + completion_tokens) / 100000)`
- GRPO compute cost is reported as free-tier GPU-hours, not dollars.

## Cross-Dataset Local Results

| Method | Precision | Recall | F1 | Avg Steps | Quota Units | GPU Hours |
| --- | --- | --- | --- | --- | --- | --- |
| heuristic | 0.1667 | 0.1111 | 0.1333 | 122.00 | 0.0000 | 0.0000 |
| random | 0.0017 | 0.0001 | 0.0001 | 141.67 | 0.0000 | 0.0000 |

## Per-Dataset Local Results

### Hospital

| Method | Precision | Recall | F1 | Avg Steps | Quota Units | GPU Hours |
| --- | --- | --- | --- | --- | --- | --- |
| random | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 25.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |
| heuristic | 0.5000 +/- 0.0000 | 0.3333 +/- 0.0000 | 0.4000 +/- 0.0000 | 3.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |

### Flights

| Method | Precision | Recall | F1 | Avg Steps | Quota Units | GPU Hours |
| --- | --- | --- | --- | --- | --- | --- |
| random | 0.0050 +/- 0.0087 | 0.0002 +/- 0.0003 | 0.0004 +/- 0.0007 | 200.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |
| heuristic | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 93.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |

### Beers

| Method | Precision | Recall | F1 | Avg Steps | Quota Units | GPU Hours |
| --- | --- | --- | --- | --- | --- | --- |
| random | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 200.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |
| heuristic | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 270.0000 +/- 0.0000 | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |

## Citation-Only SOTA Reference

Source: [BClean: A Bayesian Data Cleaning System](https://szudseg.cn/assets/papers/vldb2024-qin.pdf)

HoloClean rows are transcribed from BClean Table 4; see [HoloClean 2017](https://www.vldb.org/pvldb/vol10/p1190-rekatsinas.pdf) for the original system description.

| Method | Dataset | Precision | Recall | F1 | Note |
| --- | --- | --- | --- | --- | --- |
| HoloClean | hospital | 1.000 | 0.456 | 0.626 | Citation-only literature result. |
| HoloClean | flights | 0.742 | 0.352 | 0.477 | Citation-only literature result. |
| HoloClean | beers | 1.000 | 0.024 | 0.047 | Citation-only literature result. |
| Raha+Baran | hospital | 0.971 | 0.585 | 0.730 | Citation-only literature result. |
| Raha+Baran | flights | 0.829 | 0.650 | 0.729 | Citation-only literature result. |
| Raha+Baran | beers | 0.873 | 0.872 | 0.873 | Citation-only literature result. |

## Methodology

Local rows are reproduced from generated JSON. Citation-only SOTA rows are copied from literature and are not rerun in this repository. LLM quota units are free-tier fractions; GRPO compute cost is GPU-hours, not dollars.
