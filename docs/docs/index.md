# DataForge

DataForge is a CLI-first toolkit for finding and repairing data-quality issues
in tabular files. It profiles CSVs, proposes deterministic repairs, checks
changes through safety and verification gates, and records applied fixes in a
reversible transaction log.

The 0.1.0 release is an alpha meant for local CSV profiling, repair
experiments, benchmarks, and training/evaluation research. It is not a
warehouse-native service and it does not make production model-quality claims.

## What ships in 0.1.0

- `dataforge profile`, `dataforge repair`, `dataforge revert`, and
  `dataforge bench`.
- Detector families for type mismatches, decimal shifts, and functional
  dependency violations.
- Deterministic repairers wired through `SafetyFilter` and `SMTVerifier`.
- Append-only transaction journals with immutable source snapshots.
- OpenEnv-compatible actions for data inspection, SQL, statistics, diagnosis,
  repair, and root-cause analysis.
- Benchmark scripts and generated reports for Hospital, Flights, and Beers.
- A React playground deployed through Cloudflare Workers Static Assets, backed
  by a Hugging Face Docker Space API.

## Core flow

```mermaid
flowchart LR
    A["CSV + optional schema"] --> B["Detectors"]
    B --> C["Repairers"]
    C --> D["SafetyFilter"]
    D --> E["SMTVerifier"]
    E --> F["Transaction journal"]
    F --> G["CSV mutation or revert"]
```

## Start here

Run the [quickstart](quickstart.md) first. Use the [playground
guide](playground.md) for the hosted Profile -> Repair -> Verify -> Revert
surface, then read the [architecture reference](architecture.md) if you need
the full mental model before extending the system.
