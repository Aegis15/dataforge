# Reference

## CLI

```bash
dataforge15 profile <csv> [--schema schema.yaml]
dataforge15 repair <csv> [--schema schema.yaml] --dry-run
dataforge15 repair <csv> [--schema schema.yaml] --apply
dataforge15 watch <csv> [--schema schema.yaml] --once --json
dataforge15 audit <txn-id>
dataforge15 revert <txn-id>
dataforge15 bench --methods heuristic --datasets hospital --seeds 1
```

## Public modules

| Module | Purpose |
| --- | --- |
| `dataforge.detectors` | Detector registry and detector implementations |
| `dataforge.repairers` | Deterministic repair proposal generation |
| `dataforge.safety` | Constitution-backed repair policy |
| `dataforge.verifier` | SMT-backed repair verification |
| `dataforge.transactions` | Hash-chained journals, snapshots, audit, and revert |
| `dataforge.env` | OpenEnv-compatible environment |
| `dataforge.causal` | Causal DAG and root-cause utilities |
| `dataforge.bench` | Benchmark runners, metrics, and reports |

## Version support

DataForge15 0.1.0 supports Python 3.11 and 3.12. The core package is intentionally
separate from playground, training, and model-demo dependencies.
