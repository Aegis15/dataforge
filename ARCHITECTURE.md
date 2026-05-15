# DataForge Architecture

Last updated: 2026-05-15.

DataForge is organized around a local, auditable repair pipeline:

```text
CSV/schema -> detectors -> repairers -> SafetyFilter -> SMTVerifier -> transaction log -> data
```

The same core package is reused by the CLI, benchmark harness, OpenEnv
environment, playground API, and MCP server. Demo and training surfaces are kept
separate from the core runtime so the CLI remains installable without model or
web dependencies.

## Current Layers

- **CLI and terminal UI**: Typer commands in `dataforge/cli/` with Rich output.
  Current commands are `profile`, `repair`, `revert`, and `bench`.
- **Detectors**: pure pandas-based detector classes for `type_mismatch`,
  `decimal_shift`, and `fd_violation`.
- **Repairers**: deterministic proposal generators for the shipped detector
  families. LLM fallback is optional and explicit where supported.
- **Safety**: constitutional safety rules compiled from YAML and enforced before
  writes.
- **Verification**: Z3-backed SMT checks plus typed verifier gates.
- **Transactions**: append-only JSONL journals, immutable source snapshots,
  post-state hash guards, and byte-for-byte revert.
- **Benchmarks**: Hospital, Flights, and Beers loaders, local method runners,
  quota accounting, and markdown report generation.
- **OpenEnv environment**: HTTP and in-process environment with eight typed
  actions: `INSPECT_ROWS`, `SQL_QUERY`, `STAT_TEST`, `PATTERN_MATCH`,
  `HYPOTHESIS`, `DIAGNOSE`, `FIX`, and `ROOT_CAUSE`.
- **Causal analyzer**: column-level DAG construction, FD-prior PC discovery,
  and minimal root-set analysis for cascading errors.
- **Playground**: FastAPI backend staged into a Hugging Face Docker Space and a
  static frontend deployed through Cloudflare Workers Static Assets.
- **Training and model demos**: SFT trajectory builders, readiness/release
  verifiers, Kaggle notebook, dataset/model card templates, and a separate
  Gradio model-demo Space.
- **MCP integration**: nested standalone `dataforge-mcp/` package exposing
  structured DataForge tools over stdio by default.

## Dependency Guidance

Core runtime dependencies in `pyproject.toml`:

- `pandas` and `pyarrow` - CSV/tabular data handling.
- `pydantic` - typed issue, fix, schema, environment, and MCP result models.
- `typer` and `rich` - CLI application and terminal output.
- `pyyaml` - schema and constitution loading.
- `z3-solver` - SMT verification.
- `networkx` - causal DAG representation and reachability.
- `causal-learn` - PC causal discovery after missing-value cleanup.
- `hyppo` and `scipy` - independence tests used by causal discovery.
- `httpx`, `tenacity`, and `python-dotenv` - optional provider clients and
  environment loading.
- `sqlglot` and `duckdb` - read-only SQL parsing/execution inside the
  environment.

Optional extras:

- `dev` - pytest, ruff, mypy, Hypothesis, benchmark, and Hub tooling.
- `train` - pinned Kaggle SFT stack (`trl`, `transformers`, `accelerate`,
  `peft`, `bitsandbytes`, `datasets`, `huggingface_hub`).
- `eval` - plotting libraries for evaluation summaries.
- `playground` - FastAPI, Uvicorn, multipart upload, and rate limiting.
- `openenv` - OpenEnv protocol dependency.
- `all` - aggregate development install.

Scoped non-core dependencies:

- `dataforge-mcp/pyproject.toml` depends on `dataforge` and `mcp`; MCP transport
  dependencies are not part of the core package.
- `playground-model/requirements.txt` contains Gradio/Spaces/model-demo
  dependencies only.
- `playground/api/requirements.txt` contains the hosted playground API stack.

## Safety Invariant

Every applied repair must follow this order:

```text
proposed fix -> SafetyFilter -> SMTVerifier -> transaction journal/snapshot -> disk mutation
```

Dry-run paths may stop before mutation, but they should still exercise the same
proposal, safety, and verification logic where feasible. The MCP server and
playground API must preserve this invariant instead of bypassing the CLI.

## Release Boundaries

- `dataforge` is the core CLI/library package.
- `dataforge-mcp` is a nested standalone package with its own PyPI release flow
  from `dataforge-mcp-v*` tags.
- SFT datasets and checkpoints are Hugging Face artifacts verified by
  `scripts/model/verify_sft_release.py`.
- Generated Space staging directories are deployment artifacts, not canonical
  documentation sources.
