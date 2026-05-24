"""Tests for Week 12 benchmark refresh helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataforge.bench.core import BenchmarkRunOutput
from scripts.bench.refresh_benchmark_table import (
    load_grpo_release_evidence,
    load_trained_model_output,
    merge_benchmark_outputs,
)


def _output(method: str, *, gpu_hours: float = 0.0) -> BenchmarkRunOutput:
    return BenchmarkRunOutput.model_validate(
        {
            "metadata": {
                "methods": [method],
                "datasets": ["hospital"],
                "seeds": 3,
                "reproduction_command": f"dataforge bench --methods {method} --datasets hospital --seeds 3",
            },
            "records": [
                {
                    "method": method,
                    "dataset": "hospital",
                    "seed": 0,
                    "status": "ok",
                    "precision": 1.0,
                    "recall": 1.0,
                    "f1": 1.0,
                    "tp": 1,
                    "fp": 0,
                    "fn": 0,
                    "avg_steps": 1.0,
                    "quota_units": 0.0,
                    "gpu_hours": gpu_hours,
                    "runtime_s": 1.0,
                    "provider": "local" if gpu_hours == 0 else "hf",
                    "model": method,
                    "reproduction_command": "fixture",
                }
            ],
            "aggregates": [
                {
                    "method": method,
                    "dataset": "hospital",
                    "status": "ok",
                    "seeds_requested": 3,
                    "seeds_completed": 3,
                    "precision_mean": 1.0,
                    "precision_std": 0.0,
                    "recall_mean": 1.0,
                    "recall_std": 0.0,
                    "f1_mean": 1.0,
                    "f1_std": 0.0,
                    "avg_steps_mean": 1.0,
                    "avg_steps_std": 0.0,
                    "quota_units_mean": 0.0,
                    "quota_units_std": 0.0,
                    "gpu_hours_mean": gpu_hours,
                    "gpu_hours_std": 0.0,
                    "runtime_s_mean": 1.0,
                    "runtime_s_std": 0.0,
                    "provider": "local" if gpu_hours == 0 else "hf",
                    "model": method,
                    "reproduction_command": "fixture",
                }
            ],
        }
    )


def test_merge_benchmark_outputs_combines_agent_and_trained_rows() -> None:
    merged = merge_benchmark_outputs(
        agent_output=_output("heuristic"),
        trained_output=_output("DataForge-0.5B-GRPO", gpu_hours=5.75),
    )

    assert merged.metadata["methods"] == ["heuristic", "DataForge-0.5B-GRPO"]
    assert [row.method for row in merged.records] == ["heuristic", "DataForge-0.5B-GRPO"]
    assert merged.aggregates[1].gpu_hours_mean == 5.75


def test_load_trained_model_output_fails_loudly_when_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="trained model benchmark"):
        load_trained_model_output(tmp_path / "missing.json")


def test_load_trained_model_output_accepts_benchmark_run_json(tmp_path: Path) -> None:
    path = tmp_path / "trained.json"
    path.write_text(
        _output("DataForge-0.5B-GRPO", gpu_hours=5.75).model_dump_json(), encoding="utf-8"
    )

    loaded = load_trained_model_output(path)

    assert loaded.aggregates[0].method == "DataForge-0.5B-GRPO"
    assert loaded.aggregates[0].gpu_hours_mean == 5.75


def test_load_grpo_release_evidence_requires_acceptance_gate(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text('{"metrics":{"acceptance_gate_passed":false}}', encoding="utf-8")

    with pytest.raises(ValueError, match="acceptance_gate_passed"):
        load_grpo_release_evidence(path)

    path.write_text('{"metrics":{"acceptance_gate_passed":true}}', encoding="utf-8")
    assert load_grpo_release_evidence(path)["metrics"] == {"acceptance_gate_passed": True}
