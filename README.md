# DataForge15

DataForge15 is the official release name for the DataForge codebase, a
CLI-first data-quality repair toolkit for tabular data. It
detects common CSV issues, proposes deterministic repairs, checks proposed
changes through safety and verification gates, and records applied changes in a
reversible transaction log.

The planned PyPI distribution is `dataforge15`, but it is not published yet.
The Python import namespace remains `dataforge` for the 0.1 line to avoid
unnecessary churn. Use the source install below for now; after PyPI publication,
the install name will be `dataforge15` and the import will be `import dataforge`.

The current repository is an alpha implementation. It also contains the
OpenEnv-compatible training environment, the SFT warmup workflow, a local MCP
server package, and playground/demo sources. Warehouse integrations and
production model-quality claims remain future work.

## Reproducible Benchmark Snapshot

Generated from `eval/results/agent_comparison.json` on commit `829e8a2`
(`2026-05-11`, 3 seeds). Reproduce with:

```bash
dataforge15 bench --methods random,heuristic --datasets hospital,flights,beers --seeds 3 --json
```

95% confidence intervals use a t interval over the three seed-level F1 scores.
Only locally reproducible DataForge baselines are shown here; citation-only
HoloClean/Raha/BClean rows intentionally stay out of the first-screen table.

| Method | Dataset | F1 mean (95% CI) | Precision | Recall | Avg steps | Provider |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| heuristic | hospital | 0.4000 [0.4000, 0.4000] | 0.5000 | 0.3333 | 3.0 | local |
| random | hospital | 0.0000 [0.0000, 0.0000] | 0.0000 | 0.0000 | 25.0 | local |
| random | flights | 0.0004 [0.0000, 0.0021] | 0.0050 | 0.0002 | 200.0 | local |
| heuristic | flights | 0.0000 [0.0000, 0.0000] | 0.0000 | 0.0000 | 93.0 | local |
| random | beers | 0.0000 [0.0000, 0.0000] | 0.0000 | 0.0000 | 200.0 | local |
| heuristic | beers | 0.0000 [0.0000, 0.0000] | 0.0000 | 0.0000 | 270.0 | local |

## Current Status

Shipped in the current worktree:

- `dataforge15 profile`, `dataforge15 repair`, `dataforge15 revert`,
  `dataforge15 watch`, `dataforge15 audit`, and `dataforge15 bench`
- Three detector families: `type_mismatch`, `decimal_shift`, `fd_violation`
- Reviewable schema inference in `profile --json`, including inferred column
  types, domains, regex candidates, uniqueness, and FD candidates
- Matching deterministic repairers wired through SafetyFilter -> SMTVerifier
- Reversible hash-chained transaction journals with immutable source snapshots
- Public backend repair engine at `dataforge.engine.repair`
- Real-world benchmark harness for Hospital, Flights, and Beers
- OpenEnv-compatible HTTP environment with eight typed actions, including
  read-only `ROOT_CAUSE`
- Causal root-cause analyzer for cascading data-quality errors
- Standalone `dataforge15-mcp` package exposing DataForge15 tools over MCP
- Week 9 SFT oracle trajectory workflow, readiness gate, Kaggle notebook, and
  release verifier
- Separate Gradio model-demo Space source for the published 0.5B SFT smoke
  checkpoint

Not shipped yet:

- warehouse-native or external adapter packages
- a hosted product domain
- design-partner, pilot-user, or customer validation evidence is not yet claimed
- A production-quality trained model family
- Autonomous repair in the playground or model demo

## Quickstart

```bash
python -m pip install -e ".[dev]"
dataforge15 profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml
dataforge15 repair fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --dry-run
dataforge15 watch fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --once --json
dataforge15 bench --methods random,heuristic --datasets hospital,flights,beers --seeds 3
```

`dataforge` remains a temporary CLI compatibility alias for the first
DataForge15 release.

To apply repairs, use `--apply`. Applied repairs write a transaction journal and
source snapshot before mutating the CSV, so they can be reverted:

```bash
dataforge15 repair path/to/file.csv --schema path/to/schema.yaml --apply
dataforge15 audit <txn-id>
dataforge15 revert <txn-id>
dataforge15 revert <txn-id> --search-root path/to --json
```

New transaction logs are local tamper-evident hash chains. `dataforge15 audit`
verifies the chain head, event order, replayability, and revert prerequisites;
legacy v1 logs remain replayable but are reported as unverified because they do
not contain event hashes.

## Week 9 SFT Warmup

The current SFT workflow builds split-safe `expert_v1` trajectory records from
dirty/clean CSV diffs. Exact repairs in the primary dataset are labeled
`oracle_from_clean_diff`, not inferred from Groq, Cerebras, or Gemini teacher
guesses. Clean train chunks are retained as `finish` examples so the model
learns when no repair is justified.

```powershell
$env:HF_TOKEN="..."
.\.venv\Scripts\python.exe scripts\data\build_oracle_sft_trajectories.py
.\.venv\Scripts\python.exe scripts\data\validate_sft_readiness.py
```

This writes local ignored JSONL at `data/sft_traj/expert_v1.jsonl` and an
auditable row split at `data/sft_traj/split_manifest.json`. Push the dataset
bundle only after the readiness gate passes:

```powershell
$env:HF_TOKEN="..."
.\.venv\Scripts\python.exe scripts\data\build_oracle_sft_trajectories.py --push-to-hub --hf-dataset-repo Praneshrajan15/dataforge15-sft-trajectories
```

The current historical smoke checkpoint still uses the old DataForge artifact
name:
`Praneshrajan15/DataForge-0.5B-SFT`, with trajectories at
`Praneshrajan15/dataforge-sft-trajectories`. New public artifacts should use
DataForge15 names, for example `DataForge15-0.5B-SFT` and
`dataforge15-sft-trajectories`. The historical checkpoint proves the dataset,
Kaggle training, merge, evaluation, and Hub upload path; it is not a
model-quality claim. Verify release artifacts before citing them:

```powershell
.\.venv\Scripts\python.exe scripts\model\verify_sft_release.py --output eval\results\sft_release_v0_smoke.json
.\.venv\Scripts\python.exe scripts\model\verify_sft_release.py --min-dataset-records 272 --require-sha-metrics --output eval\results\sft_release_contract_v2_20260515.json
```

## Week 12 GRPO Path

The repository now contains a gated GRPO post-training path for free-tier
experiments:

- `training/configs/grpo_05b.yaml` targets `DataForge-0.5B-SFT` -> `DataForge-0.5B-GRPO`.
- `training/configs/grpo_15b.yaml` requires a verified `DataForge-1.5B-SFT`
  prerequisite before attempting `DataForge-1.5B-GRPO`.
- `training/rewards/dataforge_reward.py` scores completions locally through the
  `repair_contract_v1` exact-repair contract.
- `training/kaggle/grpo_kaggle.ipynb` blocks Hub upload unless GRPO beats SFT
  by at least 3 absolute F1 points on `DataForge-Bench-light-verified`.

No GRPO checkpoint is described as a quality milestone in this README until
`scripts/model/verify_grpo_release.py` produces committed verification
evidence. Refresh benchmark tables only from generated JSON:

After GRPO eval evidence exists:

```powershell
.\.venv\Scripts\python.exe scripts\bench\refresh_benchmark_table.py --skip-agent-run --trained-model-json eval\results\grpo_model_comparison.json
```

## MCP Server

The nested `dataforge-mcp/` source directory builds the standalone
`dataforge15-mcp` distribution. It is not published yet, so install it from
source while release ownership is pending:

```bash
cd dataforge-mcp
python -m pip install -e ".[dev]"
dataforge15-mcp serve
```

Tools: `dataforge_profile`, `dataforge_detect_errors`,
`dataforge_verify_fix`, `dataforge_apply_repairs`, and `dataforge_revert`.
The default transport is stdio. MCP reads and writes are sandboxed to configured
allowed roots; dry-run works by default, while apply requires `--enable-apply`.
Streamable HTTP is available for local experiments.

## Playground And Model Demo

- `playground/api/` is the API backend for the CSV playground. New public Space
  deployments should use `dataforge15-playground`; older `dataforge-playground`
  deployments are historical.
- `playground/web/` is the static browser UI deployed through Cloudflare
  Workers Static Assets.
- `playground-model/` is a separate Gradio Space demo for the published
  `DataForge-0.5B-SFT` smoke checkpoint. It accepts small CSV snippets and is
  intentionally limited to demo use.

The playground does not persist uploaded files and does not call an LLM unless a
backend provider key is explicitly configured.

## Benchmark Results

<!-- BENCH:START -->
Generated from `eval/results/agent_comparison.json`.

| Method | Precision | Recall | F1 | Avg Steps | Quota Units | GPU Hours |
| --- | --- | --- | --- | --- | --- | --- |
| heuristic | 0.1667 | 0.1111 | 0.1333 | 122.00 | 0.0000 | 0.0000 |
| random | 0.0017 | 0.0001 | 0.0001 | 141.67 | 0.0000 | 0.0000 |

See `BENCHMARK_REPORT.md` for per-dataset tables, error bars, and citation-only SOTA rows.
<!-- BENCH:END -->

## Local Setup

```bash
make setup
make lint
make type
make test
make backend-gate
make release-gate
```

Verification works on Linux, macOS, and Windows with Git Bash available for GNU
Make recipes. Python support is `>=3.11,<3.13`.

`make backend-gate` is the release-quality backend check: lint, format, strict
mypy, root tests, MCP tests, README truth, OpenAPI snapshot drift, secret scan,
dependency audit availability, SBOM generation availability, and package build
availability for both `dataforge15` and `dataforge15-mcp`. The gate covers the
core `dataforge` distribution and release surfaces; the historical
`data_quality_env` namespace remains source-tree regression coverage, not part
of the `dataforge15` wheel.

Release doctor scopes:

```bash
dataforge15 release doctor --core --json
dataforge15 release doctor --maintainer-deploy --json
dataforge15 release gate --json
```

`--core` is the default OSS release check. `--maintainer-deploy` additionally
checks maintainer-specific Hugging Face, Kaggle, Cloudflare, and domain state.
`release gate` is the authoritative fresh-user proof: it builds the
distribution, audits wheel contents, creates a dependency wheelhouse, installs
with `pip --no-index --find-links`, then runs profile, repair dry-run, apply,
audit, revert, and post-revert audit from outside the source checkout.

Windows setup:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id ezwinports.make
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[all]"
make lint && make type && make test
```

## Environment Variables

Provider keys belong in a root `.env` file, which is gitignored and loaded with
`python-dotenv` where needed.

- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `CEREBRAS_API_KEY`
- `OPENROUTER_API_KEY`
- `HF_TOKEN`

## When DataForge15 Is The Wrong Tool

Do not use DataForge15 for streaming data, very large warehouse tables, regulated
workflows where every fix must be human-authored, strict low-latency SLAs, or
teams already well served by maintained Great Expectations/dbt suites. DataForge15
is currently best suited to local CSV profiling, repair experiments, benchmark
runs, and training/evaluation research.

## Repository Docs

- [.cursor/rules/dataforge.md](.cursor/rules/dataforge.md) - always-applied contribution rules
- [ARCHITECTURE.md](ARCHITECTURE.md) - current system architecture and dependencies
- [DECISIONS.md](DECISIONS.md) - technical decision log
- [CONTRIBUTING.md](CONTRIBUTING.md) - workflow and code standards
- [CLAUDE.md](CLAUDE.md) - living gotcha log for agent sessions
- [CURSOR_MASTER.md](CURSOR_MASTER.md) - context and prompt pack
- [META_CONTEXT.md](META_CONTEXT.md) - project meta-context
- [FILE_STRUCTURE.md](FILE_STRUCTURE.md) - current and planned directory map
- [SECURITY.md](SECURITY.md) - vulnerability reporting policy
- [specs/SPEC_TEMPLATE.md](specs/SPEC_TEMPLATE.md) - template for new module specs

## License

Apache-2.0. See [LICENSE](LICENSE).
