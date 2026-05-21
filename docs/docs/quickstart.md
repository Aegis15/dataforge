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

For a released install, use `python -m pip install dataforge15`. The import
namespace remains `dataforge` for the 0.1 line.

## 2. Profile the hospital fixture

```bash
dataforge15 profile fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml
```

The command prints a Rich table of detected issues, including issue type,
severity, confidence, and reason.

## 3. Preview repairs

```bash
dataforge15 repair fixtures/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --dry-run
```

Dry-run mode exercises detection, repair proposal, safety, and verification
without writing to disk.

## 4. Apply and revert on a copy

```bash
cp fixtures/hospital_10rows.csv /tmp/hospital_10rows.csv
dataforge15 repair /tmp/hospital_10rows.csv --schema fixtures/hospital_schema.yaml --apply
dataforge15 revert <txn-id>
```

Applied repairs write a transaction journal and source snapshot before the CSV
is mutated. Revert restores the original bytes when the current file still
matches the recorded post-state hash.

## 5. Regenerate benchmark docs

```bash
python scripts/bench/generate_report.py
```

The README benchmark block and `BENCHMARK_REPORT.md` are generated from
committed JSON evidence. Public benchmark numbers should not be edited by hand.
