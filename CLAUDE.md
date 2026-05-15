# CLAUDE.md - DataForge Living Knowledge Base

This file accumulates gotchas, decisions, and context that should survive across
Cursor, Claude, and Codex sessions. Append new discoveries to the bottom with
the date.

## Project Conventions

- Python 3.11 / 3.12. `pyproject.toml` pins `requires-python = ">=3.11,<3.13"`.
- The top-level `dataforge/` package exports the product API. Root-level legacy
  wrappers exist only for compatibility.
- CLI commands live in `dataforge/cli/` and are registered in
  `dataforge/cli/__init__.py`.
- Rich is used for user-facing CLI output. Do not use `print()` in library code.
- `data_quality_env/` is the frozen legacy compatibility package.

## Known Gotchas

- `pandas.read_csv(..., dtype=str)` is the safest default for messy CSVs. Pandas
  type inference can lose precision on monetary or identifier-like values.
- Z3 `Real` variables are mathematical reals, not IEEE-754 floats. Use `FP` only
  when actual floating-point behavior matters.
- TRL v1+ manages `remove_unused_columns` internally in `GRPOConfig`; do not
  hand-set it from older tutorials.
- `causal-learn` PC does not accept NaN values. Impute or drop missing values
  before discovery.
- OpenEnv's current primary API is `reset()`, `step()`, and `state()`. The local
  server also exposes `close()` for compatibility.

## 2026-05-15 Notes

- The environment action space is now eight actions. `ROOT_CAUSE` is read-only
  and returns analyzer-backed root indices; it does not authorize repairs.
- `R_ROOT_CAUSE` is a small dense bonus and only applies when task metadata
  exposes root labels.
- `dataforge-mcp/` is a nested standalone package. Keep MCP transport
  dependencies out of core `dataforge`.
- The SFT oracle workflow reserves held-out rows before chunking. Held-out rows
  must not appear in target rows, context rows, normalization candidates, fixes,
  or messages.
- The published 0.5B SFT checkpoint is smoke-release evidence, not a quality
  milestone. Do not describe it as deployment-ready unless verifier metrics
  show a real held-out gain and the docs are updated with that evidence.
- The Gradio model demo is separate from the CSV playground. It caps inputs at
  50 parsed data rows and may return malformed or incorrect model output.
- Hugging Face ZeroGPU is selected in Space settings. Do not document unsupported
  README frontmatter keys for hardware selection.

## Performance Notes

- Detector pass on a 10k-row CSV should finish in under 2 seconds.
- SMT verification can become expensive if FDs are expanded into concrete row
  pairs. Prefer symbolic constraints where possible.
- Rich tables are slow for large output. Summarize or paginate beyond a few
  hundred rows.

## Append-Only From Here Onward
