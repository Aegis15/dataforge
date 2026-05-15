"""Tests for paired SFT eval-report gate summaries."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.model.summarize_eval_reports import compare_reports, summarize_report


def _report(path: Path, *, f1: float | None, failures: dict[str, int] | None = None) -> Path:
    path.write_text(
        json.dumps(
            {
                "records": [],
                "aggregates": [
                    {
                        "agent": "hf-local",
                        "dataset": "hospital",
                        "trials_requested": 1,
                        "trials_completed": 1 if f1 is not None else 0,
                        "f1_mean": f1,
                        "failure_taxonomy": failures or {},
                    }
                ],
                "reproducibility": {"seeds": [10000]},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_summarize_report_captures_macro_f1_parse_rate_and_failures(tmp_path: Path) -> None:
    report = _report(
        tmp_path / "failed.json",
        f1=None,
        failures={"parse_failure": 1, "truncated_json": 1},
    )

    summary = summarize_report(report)

    assert summary.macro_f1 == 0.0
    assert summary.parse_success_rate == 0.0
    assert summary.failure_taxonomy == {"parse_failure": 1, "truncated_json": 1}


def test_compare_reports_accepts_only_real_quality_gain(tmp_path: Path) -> None:
    base = _report(tmp_path / "base.json", f1=0.2)
    sft = _report(tmp_path / "sft.json", f1=0.3)

    summary = compare_reports(base_report=base, sft_report=sft)

    assert summary.f1_delta == 0.1
    assert summary.parse_gate_passed is True
    assert summary.quality_gate_passed is True
    assert summary.regression_gate_passed is True
    assert summary.release_decision == "quality_milestone"


def test_compare_reports_rejects_no_gain_even_when_pipeline_runs(tmp_path: Path) -> None:
    base = _report(tmp_path / "base.json", f1=0.0)
    sft = _report(tmp_path / "sft.json", f1=0.0)

    summary = compare_reports(base_report=base, sft_report=sft)

    assert summary.release_decision == "pipeline_or_diagnostic_only"
    assert summary.quality_gate_passed is False
