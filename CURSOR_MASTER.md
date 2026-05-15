# DataForge Cursor Context Pack

Document version: v2.1, updated 2026-05-15.

This file points agents to the canonical project context. It is intentionally
shorter than the original planning pack because the repository now has concrete
source docs for each surface.

## Read First

1. `META_CONTEXT.md` - project identity, current scope, quality bar, and
   pre-mortem.
2. `.cursor/rules/dataforge.md` - rules that apply to every change.
3. `README.md` - public truth source for shipped capabilities.
4. `ARCHITECTURE.md` - current layers and dependency boundaries.
5. `DECISIONS.md` - technical decisions and reversal criteria.
6. `CLAUDE.md` - session-to-session gotchas.

## Current Public Interfaces

- Package: `dataforge` `0.1.0`, Python `>=3.11,<3.13`.
- CLI: `profile`, `repair`, `revert`, `bench`.
- Environment actions: `INSPECT_ROWS`, `SQL_QUERY`, `STAT_TEST`,
  `PATTERN_MATCH`, `HYPOTHESIS`, `DIAGNOSE`, `FIX`, `ROOT_CAUSE`.
- MCP package: `dataforge-mcp serve`.
- MCP tools: `dataforge_profile`, `dataforge_detect_errors`,
  `dataforge_verify_fix`, `dataforge_apply_repairs`, `dataforge_revert`.

## Working Loop

1. Read the relevant spec in `specs/`.
2. Check `test_map.json` for mapped tests.
3. Write or update tests first for behavior changes.
4. Implement the minimum change.
5. Run the smallest relevant gate, then broaden before handoff.
6. Update docs and `DECISIONS.md` when public behavior or architecture changes.

Common gates:

```bash
make lint
make type
make test-mapped FILE=<source_file>
python scripts/ci/readme_truth.py
python -m pytest dataforge-mcp/tests -v
```

## Documentation Rule

`README.md` and the canonical runbooks are the source of truth. Generated
Hugging Face staging mirrors are outputs and should be regenerated, not edited
by hand.

## Future Work

Warehouse adapters, dbt/Airbyte packages, standalone evals, agent-patterns
libraries, hosted product domains, and production model families are planned
surfaces. Keep them out of shipped-capability prose until the code, tests, and
release evidence exist.
