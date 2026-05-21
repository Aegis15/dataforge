# DataForge15 Reference README

This file is reference material for a future public README. The shipped public
README is `README.md`. Do not copy claims from this file into `README.md` until
the corresponding features are implemented, tested, and documented.

## Current Core

DataForge15 currently ships a CLI-first CSV repair workflow:

```bash
dataforge15 profile path/to/data.csv
dataforge15 repair path/to/data.csv --dry-run
dataforge15 repair path/to/data.csv --apply
dataforge15 revert <txn-id>
dataforge15 bench --methods llm_zeroshot --datasets hospital --seeds 1
```

The repair path uses detectors, deterministic repairers, SafetyFilter,
SMTVerifier, and reversible transaction logs.

## Future Public Positioning

When the required integrations and hosted surfaces exist, the public positioning
can expand toward:

- local and hosted CSV profiling
- warehouse/dbt integration
- MCP-first agent integration
- open model checkpoints for air-gapped repair planning
- benchmark and evaluation packages

Until then, keep public claims centered on the shipped CLI/library, benchmark
harness, OpenEnv environment, MCP package, and SFT smoke-release evidence.

## Wrong-Tool Language

DataForge15 is not a data catalog, lineage system, observability platform,
warehouse, or replacement for maintained Great Expectations/dbt suites. It is
not currently appropriate for production autonomous repair, streaming data, or
strict regulated workflows requiring human-authored fixes.
