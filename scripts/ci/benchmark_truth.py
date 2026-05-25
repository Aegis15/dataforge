"""CI check: public benchmark surfaces are generated from checked-in artifacts."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from dataforge.bench.core import BENCHMARK_SCHEMA_VERSION
from dataforge.bench.report import load_agent_output, load_sota_output, write_benchmark_outputs

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOTA_SCHEMA_VERSION = "dataforge_sota_citation_v1"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _validate_agent_metadata(agent_json: Path) -> list[str]:
    errors: list[str] = []
    output = load_agent_output(agent_json)
    metadata = output.metadata
    if metadata.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        errors.append(
            f"{_relative(agent_json)} metadata schema_version is not {BENCHMARK_SCHEMA_VERSION!r}."
        )
    seed_list = metadata.get("seed_list")
    if not isinstance(seed_list, list) or not seed_list:
        errors.append(f"{_relative(agent_json)} metadata is missing exact seed_list.")
    dataset_evidence = metadata.get("dataset_evidence")
    if not isinstance(dataset_evidence, list) or not dataset_evidence:
        errors.append(f"{_relative(agent_json)} metadata is missing dataset_evidence.")
        return errors
    for item in dataset_evidence:
        if not isinstance(item, dict):
            errors.append(f"{_relative(agent_json)} dataset_evidence contains a non-object item.")
            continue
        name = str(item.get("name", "unknown"))
        for key in ("source_urls", "source_revision", "dirty_sha256", "clean_sha256"):
            if not item.get(key):
                errors.append(f"{_relative(agent_json)} dataset {name!r} is missing {key}.")
    return errors


def _validate_sota_payload(sota_json: Path) -> list[str]:
    errors: list[str] = []
    payload = load_sota_output(sota_json)
    if payload.get("schema_version") != SOTA_SCHEMA_VERSION:
        errors.append(f"{_relative(sota_json)} schema_version is not {SOTA_SCHEMA_VERSION!r}.")
    source = payload.get("source")
    if not isinstance(source, dict):
        errors.append(f"{_relative(sota_json)} source must be an object.")
        return errors
    for key in ("title", "url", "table", "source_sha256", "retrieved_at_utc"):
        if not source.get(key):
            errors.append(f"{_relative(sota_json)} source is missing {key}.")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        errors.append(f"{_relative(sota_json)} rows must be a non-empty list.")
        return errors
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{_relative(sota_json)} row {index} is not an object.")
            continue
        if row.get("evidence_kind") != "citation_only":
            errors.append(f"{_relative(sota_json)} row {index} is not citation_only evidence.")
    return errors


def _compare_text(*, label: str, expected: str, actual: str) -> str | None:
    if expected == actual:
        return None
    return f"{label} is stale; run scripts/bench/refresh_benchmark_truth.py and commit outputs."


def _check_generated_outputs(
    *,
    agent_json: Path,
    sota_json: Path,
    report: Path,
    readme: Path,
    homepage: Path,
) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="dataforge-benchmark-truth-") as raw_tmp:
        tmp = Path(raw_tmp)
        temp_report = tmp / "BENCHMARK_REPORT.md"
        temp_readme = tmp / "README.md"
        temp_homepage = tmp / "index.md"
        temp_readme.write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")
        temp_homepage.write_text(homepage.read_text(encoding="utf-8"), encoding="utf-8")
        write_benchmark_outputs(
            agent_json_path=agent_json,
            sota_json_path=sota_json,
            report_path=temp_report,
            readme_path=temp_readme,
            homepage_path=temp_homepage,
        )
        comparisons: dict[str, tuple[str, str]] = {
            _relative(report): (
                temp_report.read_text(encoding="utf-8"),
                report.read_text(encoding="utf-8"),
            ),
            _relative(readme): (
                temp_readme.read_text(encoding="utf-8"),
                readme.read_text(encoding="utf-8"),
            ),
            _relative(homepage): (
                temp_homepage.read_text(encoding="utf-8"),
                homepage.read_text(encoding="utf-8"),
            ),
        }
    for label, (expected, actual) in comparisons.items():
        error = _compare_text(label=label, expected=expected, actual=actual)
        if error is not None:
            errors.append(error)
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate generated outputs.")
    parser.add_argument(
        "--agent-json",
        type=Path,
        default=PROJECT_ROOT / "eval" / "results" / "agent_comparison.json",
    )
    parser.add_argument(
        "--sota-json",
        type=Path,
        default=PROJECT_ROOT / "eval" / "results" / "sota_comparison.json",
    )
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "BENCHMARK_REPORT.md")
    parser.add_argument("--readme", type=Path, default=PROJECT_ROOT / "README.md")
    parser.add_argument(
        "--homepage",
        type=Path,
        default=PROJECT_ROOT / "docs" / "docs" / "index.md",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.check:
        print("Pass --check to validate benchmark truth artifacts.", file=sys.stderr)
        return 2
    errors: list[str] = []
    agent_json = Path(args.agent_json)
    sota_json = Path(args.sota_json)
    report = Path(args.report)
    readme = Path(args.readme)
    homepage = Path(args.homepage)
    errors.extend(_validate_agent_metadata(agent_json))
    errors.extend(_validate_sota_payload(sota_json))
    errors.extend(
        _check_generated_outputs(
            agent_json=agent_json,
            sota_json=sota_json,
            report=report,
            readme=readme,
            homepage=homepage,
        )
    )
    if errors:
        print("Benchmark truth check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Benchmark truth check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
