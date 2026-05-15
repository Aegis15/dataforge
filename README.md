# DataForge

DataForge is a CLI-first data-quality repair toolkit for tabular data. It
detects common CSV issues, proposes deterministic repairs, checks proposed
changes through safety and verification gates, and records applied changes in a
reversible transaction log.

The current repository is an alpha implementation. It also contains the
OpenEnv-compatible training environment, the SFT warmup workflow, a local MCP
server package, and playground/demo sources. Warehouse integrations and
production model-quality claims remain future work.

## Current Status

Shipped in the current worktree:

- `dataforge profile`, `dataforge repair`, `dataforge revert`, and
  `dataforge bench`
- Three detector families: `type_mismatch`, `decimal_shift`, `fd_violation`
- Matching deterministic repairers wired through SafetyFilter -> SMTVerifier
- Reversible transaction journals with immutable source snapshots
- Real-world benchmark harness for Hospital, Flights, and Beers
- OpenEnv-compatible HTTP environment with eight typed actions, including
  read-only `ROOT_CAUSE`
- Causal root-cause analyzer for cascading data-quality errors
- Standalone `dataforge-mcp` package exposing DataForge tools over MCP
- Week 9 SFT oracle trajectory workflow, readiness gate, Kaggle notebook, and
  release verifier
- Separate Gradio model-demo Space source for the published 0.5B SFT smoke
  checkpoint

Not shipped yet:

- warehouse-native or external adapter packages
- a hosted product domain
- A production-quality trained model family
- Autonomous repair in the playground or model demo

## Quickstart

```bash
python -m pip install -e ".[dev]"
dataforge profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml
dataforge repair fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --dry-run
dataforge bench --methods llm_zeroshot --datasets hospital --seeds 1
```

To apply repairs, use `--apply`. Applied repairs write a transaction journal and
source snapshot before mutating the CSV, so they can be reverted:

```bash
dataforge repair path/to/file.csv --schema path/to/schema.yaml --apply
dataforge revert <txn-id>
```

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
.\.venv\Scripts\python.exe scripts\data\build_oracle_sft_trajectories.py --push-to-hub --hf-dataset-repo Praneshrajan15/dataforge-sft-trajectories
```

The published smoke checkpoint is
`Praneshrajan15/DataForge-0.5B-SFT`, with trajectories at
`Praneshrajan15/dataforge-sft-trajectories`. It proves the dataset, Kaggle
training, merge, evaluation, and Hub upload path. It is not a model-quality
claim. Verify release artifacts before citing them:

```powershell
.\.venv\Scripts\python.exe scripts\model\verify_sft_release.py --output eval\results\sft_release_v0_smoke.json
.\.venv\Scripts\python.exe scripts\model\verify_sft_release.py --min-dataset-records 272 --require-sha-metrics --output eval\results\sft_release_contract_v2_20260515.json
```

## MCP Server

The nested `dataforge-mcp/` package is a standalone distribution that exposes
DataForge through local MCP clients:

```bash
cd dataforge-mcp
python -m pip install -e ".[dev]"
dataforge-mcp serve
```

Tools: `dataforge_profile`, `dataforge_detect_errors`,
`dataforge_verify_fix`, `dataforge_apply_repairs`, and `dataforge_revert`.
The default transport is stdio. Streamable HTTP is available for local
experiments.

## Playground And Model Demo

- `playground/api/` is the API backend for the CSV playground. It is staged into
  a Hugging Face Docker Space.
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

| Method | Precision | Recall | F1 | Avg Steps | Quota Units |
| --- | --- | --- | --- | --- | --- |
| llm_zeroshot | 0.2500 | 0.3333 | 0.2857 | 2.00 | 0.0053 |

See `BENCHMARK_REPORT.md` for per-dataset tables, error bars, and citation-only SOTA rows.
<!-- BENCH:END -->

## Local Setup

```bash
make setup
make lint
make type
make test
```

Verification works on Linux, macOS, and Windows with Git Bash available for GNU
Make recipes. Python support is `>=3.11,<3.13`.

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

## When DataForge Is The Wrong Tool

Do not use DataForge for streaming data, very large warehouse tables, regulated
workflows where every fix must be human-authored, strict low-latency SLAs, or
teams already well served by maintained Great Expectations/dbt suites. DataForge
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
