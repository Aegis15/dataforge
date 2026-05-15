"""Summarize paired dataforge-evals reports into an honest rerun gate."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from rich.console import Console
from rich.table import Table


@dataclass(frozen=True, slots=True)
class EvalReportSummary:
    """Compact summary for one dataforge-evals JSON report."""

    path: str
    macro_f1: float
    parse_success_rate: float
    per_dataset_f1: dict[str, float | None]
    failure_taxonomy: dict[str, int]


@dataclass(frozen=True, slots=True)
class PairedEvalSummary:
    """Decision summary for a base-vs-SFT report pair."""

    base: EvalReportSummary
    sft: EvalReportSummary
    f1_delta: float
    parse_gate_passed: bool
    quality_gate_passed: bool
    regression_gate_passed: bool
    release_decision: str


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return cast(dict[str, Any], payload)


def _macro_f1(per_dataset_f1: dict[str, float | None]) -> float:
    values = [value for value in per_dataset_f1.values() if value is not None]
    return round(sum(values) / len(values), 4) if values else 0.0


def summarize_report(path: Path) -> EvalReportSummary:
    """Summarize one dataforge-evals report by dataset and failure class."""
    payload = _load_json(path)
    aggregates = payload.get("aggregates")
    if not isinstance(aggregates, list) or not aggregates:
        raise ValueError(f"{path} contains no aggregate results.")

    per_dataset_f1: dict[str, float | None] = {}
    failures: Counter[str] = Counter()
    trials_requested = 0
    trials_completed = 0
    for raw_aggregate in aggregates:
        aggregate = cast(dict[str, Any], raw_aggregate)
        dataset = str(aggregate.get("dataset", "unknown"))
        per_dataset_f1[dataset] = cast(float | None, aggregate.get("f1_mean"))
        trials_requested += int(aggregate.get("trials_requested", 0) or 0)
        trials_completed += int(aggregate.get("trials_completed", 0) or 0)
        raw_failures = aggregate.get("failure_taxonomy", {})
        if isinstance(raw_failures, dict):
            failures.update({str(kind): int(count) for kind, count in raw_failures.items()})

    parse_failures = failures.get("parse_failure", 0) + failures.get("truncated_json", 0)
    parse_success_rate = (
        round(max(0, trials_requested - parse_failures) / trials_requested, 4)
        if trials_requested
        else 0.0
    )
    if trials_completed == 0 and not failures:
        failures["parse_failure"] += trials_requested
        parse_success_rate = 0.0
    return EvalReportSummary(
        path=str(path),
        macro_f1=_macro_f1(per_dataset_f1),
        parse_success_rate=parse_success_rate,
        per_dataset_f1=dict(sorted(per_dataset_f1.items())),
        failure_taxonomy={kind: failures[kind] for kind in sorted(failures)},
    )


def compare_reports(
    *,
    base_report: Path,
    sft_report: Path,
    min_parse_success_rate: float = 0.95,
    max_dataset_regression: float = 0.0,
) -> PairedEvalSummary:
    """Compare base and SFT reports using the project quality gates."""
    base = summarize_report(base_report)
    sft = summarize_report(sft_report)
    f1_delta = round(sft.macro_f1 - base.macro_f1, 4)
    parse_gate_passed = sft.parse_success_rate >= min_parse_success_rate
    quality_gate_passed = f1_delta > 0.0
    regression_gate_passed = True
    for dataset, base_f1 in base.per_dataset_f1.items():
        sft_f1 = sft.per_dataset_f1.get(dataset)
        if base_f1 is None or sft_f1 is None:
            continue
        if (base_f1 - sft_f1) > max_dataset_regression:
            regression_gate_passed = False
            break
    release_decision = (
        "quality_milestone"
        if parse_gate_passed and quality_gate_passed and regression_gate_passed
        else "pipeline_or_diagnostic_only"
    )
    return PairedEvalSummary(
        base=base,
        sft=sft,
        f1_delta=f1_delta,
        parse_gate_passed=parse_gate_passed,
        quality_gate_passed=quality_gate_passed,
        regression_gate_passed=regression_gate_passed,
        release_decision=release_decision,
    )


def write_summary(summary: PairedEvalSummary, output: Path) -> None:
    """Write a stable JSON summary."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(summary), indent=2, sort_keys=True), encoding="utf-8")


def _print_summary(summary: PairedEvalSummary) -> None:
    table = Table(title="DataForge Paired Eval Gate")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("Base macro F1", f"{summary.base.macro_f1:.4f}")
    table.add_row("SFT macro F1", f"{summary.sft.macro_f1:.4f}")
    table.add_row("F1 delta", f"{summary.f1_delta:.4f}")
    table.add_row("SFT parse success", f"{summary.sft.parse_success_rate:.4f}")
    table.add_row("Parse gate", str(summary.parse_gate_passed))
    table.add_row("Quality gate", str(summary.quality_gate_passed))
    table.add_row("Regression gate", str(summary.regression_gate_passed))
    table.add_row("Decision", summary.release_decision)
    Console().print(table)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--sft-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-parse-success-rate", type=float, default=0.95)
    parser.add_argument("--max-dataset-regression", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    summary = compare_reports(
        base_report=args.base_report,
        sft_report=args.sft_report,
        min_parse_success_rate=args.min_parse_success_rate,
        max_dataset_regression=args.max_dataset_regression,
    )
    write_summary(summary, args.output)
    _print_summary(summary)
    Console().print(f"Wrote paired eval summary to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
