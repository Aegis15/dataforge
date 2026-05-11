# Benchmark Report

## Reproduction

`dataforge bench --methods llm_zeroshot --datasets hospital --seeds 1`

## Configuration

- Methods: llm_zeroshot
- Datasets: hospital
- Seeds: 1
- Free-tier quota units: `max(llm_calls / 1000, (prompt_tokens + completion_tokens) / 100000)`

## Cross-Dataset Local Results

| Method | Precision | Recall | F1 | Avg Steps | Quota Units |
| --- | --- | --- | --- | --- | --- |
| llm_zeroshot | 0.2500 | 0.3333 | 0.2857 | 2.00 | 0.0053 |

## Per-Dataset Local Results

### Hospital

| Method | Precision | Recall | F1 | Avg Steps | Quota Units |
| --- | --- | --- | --- | --- | --- |
| llm_zeroshot | 0.2500 +/- 0.0000 | 0.3333 +/- 0.0000 | 0.2857 +/- 0.0000 | 2.0000 +/- 0.0000 | 0.0053 +/- 0.0000 |

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

Local rows are reproduced from generated JSON. Citation-only SOTA rows are copied from literature and are not rerun in this repository. Quota units are reported in free-tier fractions rather than dollars.
