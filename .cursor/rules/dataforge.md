# DataForge - Always-Applied Rules

You are contributing to DataForge, a production-grade open-source data-quality
repair project. Keep the repository honest: documentation must describe shipped
behavior, and future plans must be labeled as future work.

## Non-Negotiables

1. Never modify a public API without updating its spec in `specs/`.
2. Never delete or weaken an existing test. If a test is wrong, update the spec
   and the test together with an explicit rationale.
3. Write the failing test before implementation for feature work.
4. Every public function, class, and module has type hints and a useful
   Google-style docstring.
5. Run the relevant gate before handing off:
   `make lint`, `make type`, and `make test-mapped FILE=<source_file>`.
6. Commit messages follow Conventional Commits with a subject of 72 characters
   or fewer.
7. Do not use silent catch-all exception handlers.
8. Do not use `print()` in library code. Use `logging`; CLI output uses `rich`.
9. Avoid global mutable state. Inject dependencies where practical.
10. Do not leave TODO/FIXME comments in merged code; open an issue instead.

## Safety Invariants

- Every agent-proposed applied fix must pass through SafetyFilter -> SMTVerifier
  -> transaction log.
- The transaction journal and source snapshot are written before disk mutation.
- `dataforge revert <txn_id>` must restore the byte-for-byte pre-state when the
  current file matches the recorded post-state hash.
- The playground and MCP server must not bypass the core repair safety path.
- No browser-visible API key and no browser-run LLM call are allowed.

## Current Public Interfaces

- Core package: `dataforge` `0.1.0`, Python `>=3.11,<3.13`.
- CLI commands: `profile`, `repair`, `revert`, `bench`.
- Environment actions: `INSPECT_ROWS`, `SQL_QUERY`, `STAT_TEST`,
  `PATTERN_MATCH`, `HYPOTHESIS`, `DIAGNOSE`, `FIX`, `ROOT_CAUSE`.
- MCP command: `dataforge-mcp serve`.
- MCP tools: `dataforge_profile`, `dataforge_detect_errors`,
  `dataforge_verify_fix`, `dataforge_apply_repairs`, `dataforge_revert`.

## Verification Commands

Use the smallest relevant gate while developing, then broaden before handoff.

```bash
make lint
make type
make test-mapped FILE=dataforge/agent/tool_actions.py
make test-mapped FILE=dataforge/env/environment.py
python scripts/ci/readme_truth.py
python -m pytest dataforge-mcp/tests -v
python -m pytest tests/unit/test_model_space_contract.py -v
python -m pytest tests/unit/test_sft_trajectories.py tests/unit/test_sft_release_verifier.py -v
```

For SFT handoff work:

```bash
python scripts/data/build_oracle_sft_trajectories.py
python scripts/data/validate_sft_readiness.py
python scripts/model/verify_sft_release.py --min-dataset-records 272 --require-sha-metrics
```

## Documentation Rules

- `README.md` is the public truth source. Do not claim unshipped integrations,
  hosted domains, or model-quality wins.
- Generated Hugging Face staging mirrors are deployment artifacts, not canonical
  documentation sources.
- Benchmark and model metrics must come from committed scripts or verifier
  output.
- Use ASCII punctuation in docs unless a file has a clear reason to use Unicode.
- If a section is aspirational, label it as planned or future work.

## When Uncertain

- If a spec is ambiguous, record the real question in `specs/QUESTIONS.md` and
  proceed with the safest documented assumption.
- If a dependency seems useful, justify it in `ARCHITECTURE.md` before adding it.
- If documentation and code disagree, inspect the code and tests first; then
  update the docs or add a spec/test change that explains the new behavior.
