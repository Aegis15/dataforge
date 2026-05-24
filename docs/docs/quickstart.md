# Quickstart

This walkthrough takes about five minutes from a fresh checkout.

## 1. Install

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The PyPI package is not published yet. After PyPI publication, use `python -m pip install dataforge15`; the import namespace remains `dataforge` for the 0.1 line.

## 2. Profile the hospital fixture

```bash
dataforge15 profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml
```

The command prints a Rich table of detected issues, including issue type,
severity, confidence, and reason.

For machine-readable CI or agent calls:

```bash
dataforge15 profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --json
dataforge15 profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --fail-on unsafe
```

## 3. Preview repairs

```bash
dataforge15 repair fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --dry-run
```

Dry-run mode exercises detection, repair proposal, safety, and verification
without writing to disk.

## 4. Watch once for CI

```bash
dataforge15 watch fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --once --json
```

Without `--once`, watch polls the path and reruns `profile` or dry-run repair
when the file changes. It does not mutate files unless `--action repair --apply`
is passed explicitly.

## 5. Apply and revert on a copy

```bash
cp fixtures/hospital_10rows.csv /tmp/hospital_10rows.csv
dataforge15 repair /tmp/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --apply
dataforge15 audit <txn-id>
dataforge15 revert <txn-id>
```

Applied repairs write a transaction journal and source snapshot before the CSV
is mutated. Audit verifies the local hash chain for newly written logs. Revert
restores the original bytes when the current file still matches the recorded
post-state hash.

## 6. Regenerate benchmark docs

```bash
python scripts/bench/run_agent_comparison.py --methods random,heuristic --datasets hospital,flights,beers --seeds 3 --output-json eval/results/agent_comparison.json
python scripts/bench/run_sota_comparison.py
python scripts/bench/generate_report.py
```

The README benchmark block and `BENCHMARK_REPORT.md` are generated from
committed JSON evidence. Public benchmark numbers should not be edited by hand.
