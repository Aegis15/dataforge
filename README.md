# DataForge

DataForge currently ships a real Week 3 CLI for CSV profiling and repair.

This repository now includes shipped detectors, deterministic repairers,
constitutional safety gating, SMT-backed structural verification, reversible
transaction logs, real-world benchmark infrastructure, and a Week 9 Kaggle SFT
warmup workflow. The hosted playground, warehouse integrations, and production
trained model family remain future work.

## Current Status

- `dataforge profile`, `dataforge repair`, `dataforge revert`, and `dataforge bench`
- Three shipped detectors: `type_mismatch`, `decimal_shift`, `fd_violation`
- Three shipped repairers with safety + verifier gating in the apply path
- Reversible transaction logs with byte-identical revert via source snapshots
- Benchmark/report generation infrastructure for Hospital / Flights / Beers
- Week 9 SFT warmup scripts for collecting expert trajectories and publishing a
  Kaggle-trained 0.5B checkpoint
- `Makefile` targets for setup, lint, type-checking, and tests
- CI plus unit / integration / property / adversarial coverage

## Week 9 SFT Warmup

The Week 9 workflow trains a warmup checkpoint from chunk-level expert
trajectories without committing generated API-derived data to git. Start with
the laptop-safe smoke preset; it is network-bound, uses no local GPU training,
prints progress during Groq calls, and refuses to push partial data that cannot
pass the readiness gate.

```powershell
$env:DATAFORGE_LLM_PROVIDER="groq"
$env:GROQ_API_KEY="..."
$env:HF_TOKEN="..."

.\.venv\Scripts\python.exe scripts\data\collect_sft_trajectories.py --preset smoke --push-to-hub
.\.venv\Scripts\python.exe scripts\data\validate_sft_readiness.py
```

This writes ignored local JSONL at `data/sft_traj/expert_v1.jsonl` and can push
the dataset artifacts to `<hf_user>/dataforge-sft-trajectories`. Upload
`training/kaggle/sft_warmup_kaggle.ipynb` to Kaggle only after the readiness
check passes and `HF_TOKEN` is configured. The notebook validates the dataset
again before training, evaluates the merged checkpoint, and publishes
`<hf_user>/DataForge-0.5B-SFT` only after numeric metrics are written.

Use `--preset full` only after the smoke path works; the full collector restores
the larger multi-dataset run shape and can take thousands of Groq requests.

The notebook prints base-vs-SFT held-out F1 when run; this README does not
claim a model-quality result until those metrics are generated.

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

Verification works on Linux, macOS, or Windows (with Git Bash as the
shell substrate for GNU Make). Requires Python 3.11 or 3.12
(`requires-python = ">=3.11,<3.13"`).

### Windows-specific setup

```powershell
# Install Python 3.12 and GNU Make if not present
winget install -e --id Python.Python.3.12
winget install -e --id ezwinports.make

# Create and activate a project venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies and verify
python -m pip install -e ".[all]"
make lint && make type && make test
```

Git for Windows provides the Bash implementation the Makefile uses on Windows.
Do not rely on `C:\Windows\System32\bash.exe` (WSL).

## Environment Variables

Future provider keys belong in a root `.env` file that is gitignored and meant
to be loaded with `python-dotenv`.

- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `CEREBRAS_API_KEY`
- `OPENROUTER_API_KEY`
- `HF_TOKEN`

## Repository Docs

- [.cursor/rules/dataforge.md](.cursor/rules/dataforge.md) — always-applied rules
- [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram and dependency justification
- [DECISIONS.md](DECISIONS.md) — technical decision log
- [CONTRIBUTING.md](CONTRIBUTING.md) — workflow and code standards
- [CLAUDE.md](CLAUDE.md) — living knowledge base for Cursor sessions
- [CURSOR_MASTER.md](CURSOR_MASTER.md) — full context and prompt pack
- [META_CONTEXT.md](META_CONTEXT.md) — meta-context (read before writing code)
- [FILE_STRUCTURE.md](FILE_STRUCTURE.md) — canonical target directory tree
- [SECURITY.md](SECURITY.md) — vulnerability reporting policy
- [specs/SPEC_TEMPLATE.md](specs/SPEC_TEMPLATE.md) — spec template for new modules

## License

Apache-2.0. See [LICENSE](LICENSE).
