# SPEC: Week 9 SFT warmup

> Status: Draft
> Owner: DataForge maintainers
> Last updated: 2026-05-02

## 1. Purpose

Week 9 introduces a supervised-fine-tuning warmup for a 0.5B DataForge repair
model using only free-tier Kaggle GPU compute. The workflow must collect
auditable chunk-level expert trajectories, train Qwen2.5-0.5B-Instruct with
LoRA/QLoRA, and publish a merged checkpoint with a complete model card.

## 2. Outcomes

- [ ] `scripts/data/collect_sft_trajectories.py` writes valid `expert_v1` JSONL
  and resumes without duplicating `(task_id, seed, chunk_index)`.
- [ ] `scripts/data/validate_sft_readiness.py` fails locally before Kaggle if
  the SFT JSONL/config handoff is missing, too small, duplicated, unpinned, or
  below the configured episode-F1 floor.
- [ ] `training/kaggle/sft_warmup_kaggle.ipynb` can be uploaded to Kaggle and
  run with `HF_TOKEN` to publish `<hf_user>/DataForge-0.5B-SFT`.
- [ ] `scripts/publish_model.py` refuses incomplete model-card evidence and
  uploads merged weights plus `README.md` via `huggingface_hub`.
- [ ] No commercial/API-generated trajectories are committed to git.

## 3. Scope

**IN**:
- Chunk-level SFT trajectory collection from Groq ReAct teacher episodes.
- DataForge-Bench-light windows over Hospital, Flights, and Beers with easy and
  medium difficulty bands.
- Kaggle P100-targeted 4-bit LoRA SFT configuration and notebook.
- HF dataset/model repo publishing helpers and model-card template.

**OUT**:
- Running paid 7B training.
- Committing generated expert trajectories.
- Replacing the benchmark CLI or the separate `dataforge-evals` package.
- Claiming benchmark improvements before the Kaggle notebook produces metrics.

## 4. Constraints

- Compute: target <6 wall-clock hours on a single Kaggle P100 16GB runtime.
- Budget: default 2,800 total Groq requests, 900-request daily planning budget,
  and 2,000 retained chunk-level examples.
- Local smoke collection: `--preset smoke` is the first-run default for laptops
  and targets 32 valid Hospital/easy trajectories with visible progress,
  per-request timeout/retry bounds, and a wall-clock deadline.
- Filtering: only retain chunks from episodes with exact-match F1 >= 0.6.
- Compatibility: Python 3.11/3.12 locally; Kaggle notebook uses CUDA fp16 and
  never bf16 because P100 does not support bf16.
- Provenance: trajectory records must include teacher, metrics, source citation,
  and source URLs.

## 5. Prior Decisions

- DataForge-Bench-light uses deterministic windows over the existing real-world
  Hospital, Flights, and Beers datasets rather than creating new benchmark data.
- A “trajectory” is one chunk-level SFT example keyed by
  `(task_id, seed, chunk_index)`, not a whole benchmark episode.
- HF repo ownership is automatic via `HF_TOKEN` and `whoami`.
- Training package versions are pinned in `training/configs/sft_05b.yaml`, not
  hardcoded throughout the notebook.

## 6. Task Breakdown

### 6.1 Trajectory collector
- Acceptance: validates `expert_v1`, enforces budget/deadline limits, prints
  chunk/API progress, filters by F1, slices accepted records to the remaining
  cap, gates HF push on readiness, and skips existing chunk keys.
- Depends on: existing benchmark Groq ReAct helpers.
- Estimated complexity: M.

### 6.2 Kaggle SFT notebook and config
- Acceptance: six main cells load YAML, train LoRA in fp16, checkpoint every 100
  steps, merge adapters, push weights, and print held-out F1.
- Depends on: trajectory dataset repo.
- Estimated complexity: M.

### 6.3 Model publishing
- Acceptance: renders a complete model card from metrics and uploads via HF API.
- Depends on: merged model directory and metrics JSON.
- Estimated complexity: S.

### 6.4 Documentation and mapping
- Acceptance: README, ARCHITECTURE, DECISIONS, `.gitignore`, and `test_map.json`
  describe the workflow without fabricated metrics.
- Depends on: implementation files.
- Estimated complexity: S.

## 7. Verification

- Unit tests: `tests/unit/test_sft_trajectories.py`,
  `tests/unit/test_publish_model.py`, `tests/unit/test_sft_notebook_contract.py`.
- Integration: existing benchmark workflow tests continue to pass.
- Local gate: `make lint && make type && make test-mapped` for touched mapped
  files; full `make test` when runtime allows.
- Notebook gate: Kaggle run-all with `HF_TOKEN` ends with a public model repo,
  model card, `training_metrics.json`, and printed base/SFT F1.
- Handoff gate: `python scripts/data/validate_sft_readiness.py` passes before
  uploading the notebook to Kaggle.

## 8. Acceptance Gate

- [ ] Section 2 outcomes are met.
- [ ] New unit tests pass.
- [ ] Existing benchmark and OpenEnv tests pass.
- [ ] No generated JSONL trajectories are tracked.
- [ ] Model-card metrics are notebook-generated, not hand-edited.

## Appendix A - Toy Cases

### Case A.1: duplicate chunk skip
Input: JSONL already contains `hospital:easy`, seed 7, chunk 0.
Expected output: rerun does not call the teacher for that chunk and does not
append a duplicate record.

### Case A.2: low-F1 episode
Input: teacher returns only `finish` actions for an episode with known errors.
Expected output: no SFT records are retained.

### Case A.3: incomplete model-card evidence
Input: merged model directory lacks `model_license` in `training_metrics.json`.
Expected output: publisher raises before creating or uploading an HF repo.
