---
license: apache-2.0
task_categories:
- text-generation
language:
- en
tags:
- dataforge
- data-quality
- supervised-fine-tuning
- tabular
- expert-trajectories
size_categories:
- 1K<n<10K
---

# DataForge SFT Trajectories

This dataset contains chunk-level `expert_v1` supervised-fine-tuning records for
the DataForge Week 9 warmup model. The current milestone is built from
split-safe dirty/clean CSV diffs (`oracle_from_clean_diff`) so model training is
anchored to audited labels rather than teacher guesses.

The earlier `v0-smoke` checkpoint proved the Kaggle-to-Hugging-Face handoff. It
is not a performance-improvement claim.

## Contents

- `expert_v1.jsonl`: auditable chat-style repair trajectories.
- `split_manifest.json`: deterministic train/eval row manifest containing row
  ids and dirty-row SHA-256 hashes only; it contains no clean labels, suggested
  values, or repair targets.
- `sft_05b.yaml`: pinned Kaggle training configuration.
- `MODEL_CARD_TEMPLATE.md`: model-card template used by the publishing notebook.

Each JSONL row includes the schema version, trajectory id, task id, dataset,
difficulty, seed, chunk index, observed state, chat messages, tool-call summary,
proposed fixes, teacher/oracle metadata, evaluation metrics, split metadata, and
source provenance.

Chunks with no dirty/clean differences are kept as hard-negative `finish`
examples. They teach the same inference contract as evaluation: do not repair a
cell unless the dirty rows justify an exact replacement.

## Provenance

Primary records are generated from deterministic train rows over the Raha
Hospital, Flights, and Beers benchmark sources. The held-out row split is chosen
before chunking, and held-out rows are excluded from target rows, context rows,
normalization candidates, fixes, and messages.

Flights is supervised from dirty/clean labels. Schedule and actual-time repairs
are marked as `oracle_from_clean_diff`; they are not Groq, Cerebras, or Gemini
discoveries.

Legacy `llm_react_chunk` records may remain for smoke-lineage auditability, but
they are not the source of exact Flights schedule labels.

## Intended Use

- Reproducing the DataForge 0.5B SFT warmup workflow.
- Auditing the exact data handed to the Kaggle notebook.
- Training or debugging small tabular repair agents under DataForge's verifier
  and transaction assumptions.

## Limitations

- This is a supervised training dataset, not a leaderboard.
- It should not be treated as a broad data-cleaning benchmark.
- Legacy teacher outputs can contain mistakes even after filtering.
- The dataset is not a substitute for held-out evaluation; use
  `dataforge-evals` to compare model outputs against exact cell-level ground
  truth before making quality claims.
