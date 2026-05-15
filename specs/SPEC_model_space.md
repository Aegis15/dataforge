# SPEC: DataForge 0.5B Gradio Space

> Status: Reviewed
> Owner: Praneshrajan15
> Last updated: 2026-05-15

## 1. Purpose

Stage a second Hugging Face Gradio Space that demos the published
`Praneshrajan15/DataForge-0.5B-SFT` checkpoint on small CSV snippets. The demo
is honest about the checkpoint's current quality status and uses ZeroGPU only
for burst inference calls.

## 2. Outcomes

- [x] `playground-model/app.py` launches a Gradio interface locally or on HF
      Spaces.
- [x] The UI accepts a CSV snippet capped at 50 rows and returns a tabular list
      of detected/proposed repairs.
- [x] Model weights are loaded with `from_pretrained()` from the Hugging Face
      Hub and are never committed.
- [x] README frontmatter uses supported Space metadata keys and documents
      ZeroGPU queue/quota behavior without stale unsupported hardware claims.

## 3. Scope

**IN**:
- Gradio SDK Space source files under `playground-model/`.
- `@spaces.GPU` inference wrapper.
- Small, defensive parser for model output into stable table rows.
- README with setup and limitation notes.

**OUT**:
- Direct push to Hugging Face Hub.
- Hosted Space deployment automation.
- Quality claims beyond the verified Week 9 release evidence.

## 4. Constraints

- Input cap: maximum 50 parsed data rows.
- Free-tier discipline: no committed weights or generated caches.
- Compatibility: Gradio SDK Space, Python 3.10/3.12-compatible app code.
- Failure mode: malformed CSV or malformed model output returns table rows, not
  an uncaught traceback.

## 5. Prior decisions

- Use `sdk: gradio` and `app_file: app.py` in README frontmatter.
- Select ZeroGPU in the Space settings; do not encode unsupported hardware
  metadata.
- Document current ZeroGPU behavior using current Hugging Face docs rather than
  stale prompt wording.

## 6. Task breakdown

### 6.1 Space scaffold
- Acceptance: README, requirements, and app file exist under `playground-model/`.
- Depends on: none.
- Estimated complexity: S.

### 6.2 Defensive CSV handling
- Acceptance: empty, malformed, and over-50-row inputs return stable UI output.
- Depends on: 6.1.
- Estimated complexity: S.

### 6.3 Model inference path
- Acceptance: `from_pretrained()` loads model/tokenizer and the generation
  function is decorated with `@spaces.GPU`.
- Depends on: 6.1.
- Estimated complexity: M.

## 7. Verification

- Unit tests: `tests/unit/test_model_space_contract.py`.
- Checks:
  - README frontmatter parses and uses supported keys.
  - CSV cap rejects 51 data rows.
  - malformed model text produces stable table columns.

## 8. Acceptance gate

- [x] Section 2 outcomes are met.
- [x] No model weights or cache directories are added.
- [x] Root tests still pass.

## Appendix A - Toy cases

### Case A.1: Too many rows
Input: header plus 51 CSV data rows.
Expected output: one table row with `status=error` and a row-limit message.
Reasoning: protects ZeroGPU quota and keeps the public demo bounded.

### Case A.2: Non-JSON model output
Input: model text `not json`.
Expected output: one table row with a raw model summary and stable columns.
Reasoning: public demos must degrade gracefully when a warmup model emits
unstructured text.
