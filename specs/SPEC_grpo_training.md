# SPEC: Week 12 GRPO training

> Status: Draft
> Owner: DataForge maintainers
> Last updated: 2026-05-16

## 1. Purpose

Week 12 adds a free-tier-only GRPO post-training path after the verified SFT
warmup checkpoint. The workflow must train, evaluate, and publish GRPO
checkpoints only when generated evidence proves a real held-out improvement.

## 2. Outcomes

- [ ] `training/configs/grpo_05b.yaml` and `grpo_15b.yaml` encode the corrected
  TRL v1-era GRPO stack, exact package pins, and free-tier memory limits.
- [ ] `training/rewards/dataforge_reward.py` scores completions locally through
  the `repair_contract_v1` parser and exact cell-repair metrics.
- [ ] `training/kaggle/grpo_kaggle.ipynb` trains with checkpoint resume and
  blocks upload unless the GRPO release gate passes.
- [ ] `scripts/bench/refresh_benchmark_table.py` merges Week 4 agents with
  trained-model rows and refreshes README/BENCHMARK_REPORT from JSON evidence.
- [ ] `scripts/model/verify_grpo_release.py` rejects incomplete or below-gate
  GRPO model repos before docs cite them.

## 3. Scope

**IN**:

- 0.5B GRPO from `Praneshrajan15/DataForge-0.5B-SFT` with fp16 LoRA.
- 1.5B GRPO from a verified `DataForge-1.5B-SFT` prerequisite with 4-bit QLoRA.
- DataForge-Bench-light-verified evaluation over seeds `0,1,2`.
- GPU-hour accounting for free-tier compute.

**OUT**:

- Training or publishing 3B+ models on free tier.
- Reward calls to the mutable OpenEnv HTTP singleton during GRPO rollouts.
- Public quality claims without generated verifier artifacts.

## 4. Constraints

- `TRL v0.11` is unsupported for this path. GRPO configs target the repo's
  TRL v1-era stack and fail fast on stale pins.
- `max_prompt_length` is treated as local `prompt_token_budget: 1024` and only
  passed to `GRPOConfig` if the installed TRL signature supports it.
- P100/T4 free-tier runs use `num_generations: 4`, completion length `256`,
  batch size `1`, gradient accumulation `16`, fp16, and no bf16.
- The `0.5B-GRPO` release requires at least `+0.03` absolute macro F1 over
  `0.5B-SFT` on DataForge-Bench-light-verified, plus parse success `>=0.99`
  and zero schema-case errors.

## 5. Prior Decisions

- The Week 9 SFT workflow remains the warmup source and must not be described
  as a quality milestone unless verifier output proves improvement.
- README benchmark rows are generated from JSON artifacts only.
- GRPO is selected before GiGPO for the free-tier path because it ships in TRL;
  GiGPO/verl-agent remains heavier setup and memory work.

## 6. Task Breakdown

### 6.1 Configs and import preflight

- Acceptance: exact pins, no TRL v0.11, fp16/no-bf16, prompt-token budget
  mapping, and `PYTHONUTF8=1` import guidance are covered by tests.
- Depends on: none.
- Estimated complexity: S.

### 6.2 Reward function

- Acceptance: exact repairs, no-op finish records, malformed JSON, duplicate
  repairs, and schema-case errors are scored deterministically without network.
- Depends on: `dataforge.repair_contract`.
- Estimated complexity: M.

### 6.3 Kaggle notebook

- Acceptance: six main cells load config, train with `GRPOTrainer`, resume
  checkpoints, merge adapters, write diagnostics, and upload only after gate.
- Depends on: configs and reward function.
- Estimated complexity: M.

### 6.4 Benchmark and release gates

- Acceptance: trained rows merge with agent rows, GPU-hours render in reports,
  and GRPO Hub repos fail verification without complete metrics and diagnostics.
- Depends on: benchmark report helpers and HF model evidence.
- Estimated complexity: M.

## 7. Verification

- Unit: `tests/unit/test_grpo_configs.py`,
  `tests/unit/test_dataforge_grpo_reward.py`,
  `tests/unit/test_grpo_notebook_contract.py`,
  `tests/unit/test_grpo_benchmark_refresh.py`,
  `tests/unit/test_grpo_release_verifier.py`.
- Existing benchmark/report tests must continue to pass.
- Documentation gate: `python scripts/ci/readme_truth.py`.
- Before citing a GRPO checkpoint:
  `python scripts/model/verify_grpo_release.py --model-repo <repo> --output eval/results/<repo>.json`.

## 8. Acceptance Gate

- [ ] Section 2 outcomes are met.
- [ ] Focused GRPO tests pass.
- [ ] README contains no trained-model quality claim without verifier evidence.
- [ ] Failed GRPO runs write diagnostics and do not push model repos.

## Appendix A - Toy Cases

### Case A.1: malformed completion

Input: completion text `not json`.
Expected output: reward `0.0`, parse diagnostic recorded.
Reasoning: prevents rewarding invalid model output.

### Case A.2: clean chunk finish

Input: `{"action":"finish","repairs":[]}` with empty ground truth.
Expected output: reward `1.0`.
Reasoning: clean train chunks must teach no unnecessary edits.

### Case A.3: failed release gate

Input: GRPO F1 only `0.01` above SFT.
Expected output: verifier rejects and notebook upload is blocked.
Reasoning: prevents publishing a worse or meaningless model as progress.
