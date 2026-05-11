"""Unit tests for Week 9 SFT trajectory collection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from dataforge.bench.groq_client import GroqCompletion
from dataforge.datasets.real_world import GroundTruthCell, RealWorldDataset
from dataforge.datasets.registry import DatasetMetadata
from scripts.data.collect_sft_trajectories import (
    BudgetGuard,
    RuntimeDeadline,
    TrajectoryKey,
    _build_parser,
    _resolve_collection_settings,
    collect_episode_trajectories,
    ensure_ready_for_push,
    existing_trajectory_keys,
    main,
    validate_trajectory_record,
    write_jsonl_records,
)
from scripts.data.validate_sft_readiness import SftReadinessError


def _dataset() -> RealWorldDataset:
    dirty_df = pd.DataFrame(
        {
            "Phone": ["2175550101", "not available"],
            "Score": ["5", "45"],
        }
    )
    clean_df = pd.DataFrame(
        {
            "Phone": ["2175550101", "2175550202"],
            "Score": ["5", "4.5"],
        }
    )
    return RealWorldDataset(
        metadata=DatasetMetadata(
            name="hospital",
            domain="healthcare",
            n_rows=2,
            n_columns=2,
            error_types=("missing_value", "formatting"),
            source_urls=("dirty", "clean"),
            citation="fixture citation",
        ),
        dirty_df=dirty_df,
        clean_df=clean_df,
        canonical_columns=("Phone", "Score"),
        ground_truth=(
            GroundTruthCell(
                row=1,
                column="Phone",
                dirty_value="not available",
                clean_value="2175550202",
            ),
            GroundTruthCell(row=1, column="Score", dirty_value="45", clean_value="4.5"),
        ),
    )


@dataclass
class _StubClient:
    responses: list[GroqCompletion]
    model: str = "llama-3.3-70b-versatile"

    def __post_init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> GroqCompletion:
        self.calls.append(messages)
        return self.responses.pop(0)


def test_validate_trajectory_record_requires_expert_v1_schema() -> None:
    record = {
        "schema_version": "expert_v1",
        "trajectory_id": "hospital:easy:0:1",
        "task_id": "hospital:easy",
        "dataset": "hospital",
        "difficulty": "easy",
        "seed": 0,
        "chunk_index": 1,
        "state": {"rows": []},
        "tool_calls": [],
        "diagnosis": [],
        "fix": [],
        "messages": [{"role": "user", "content": "repair"}],
        "teacher": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "metrics": {"episode_f1": 1.0, "chunk_f1": 0.0},
        "provenance": {"citation": "fixture citation"},
    }

    validated = validate_trajectory_record(record)

    assert validated["schema_version"] == "expert_v1"
    assert validated["trajectory_id"] == "hospital:easy:0:1"


def test_existing_keys_are_chunk_level(tmp_path: Path) -> None:
    output = tmp_path / "expert_v1.jsonl"
    write_jsonl_records(
        output,
        [
            validate_trajectory_record(
                {
                    "schema_version": "expert_v1",
                    "trajectory_id": "hospital:easy:7:0",
                    "task_id": "hospital:easy",
                    "dataset": "hospital",
                    "difficulty": "easy",
                    "seed": 7,
                    "chunk_index": 0,
                    "state": {"rows": []},
                    "tool_calls": [],
                    "diagnosis": [],
                    "fix": [],
                    "messages": [{"role": "user", "content": "repair"}],
                    "teacher": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
                    "metrics": {"episode_f1": 1.0, "chunk_f1": 0.0},
                    "provenance": {"citation": "fixture citation"},
                }
            )
        ],
    )

    assert existing_trajectory_keys(output) == {TrajectoryKey("hospital:easy", 7, 0)}


def test_budget_guard_blocks_over_limit() -> None:
    guard = BudgetGuard(max_total_requests=2)

    guard.consume(2)

    with pytest.raises(RuntimeError, match="request budget"):
        guard.consume(1)


def test_budget_guard_blocks_daily_limit_before_total_limit() -> None:
    guard = BudgetGuard(max_total_requests=10, daily_request_budget=2)

    guard.consume(2)

    with pytest.raises(RuntimeError, match="daily request budget"):
        guard.consume(1)


def test_smoke_preset_resolves_laptop_safe_defaults() -> None:
    args = _build_parser().parse_args(["--preset", "smoke"])

    settings = _resolve_collection_settings(args)

    assert settings.preset == "smoke"
    assert settings.datasets == ["hospital"]
    assert settings.difficulties == ["easy"]
    assert settings.max_trajectories == 32
    assert settings.max_total_requests == 256
    assert settings.max_runtime_min == 30.0
    assert settings.ready_min_records == 32


def test_explicit_timeout_and_retry_flags_override_preset_defaults() -> None:
    args = _build_parser().parse_args(
        [
            "--preset",
            "smoke",
            "--datasets",
            "beers",
            "--difficulties",
            "medium",
            "--seeds",
            "3",
            "--groq-timeout-s",
            "7",
            "--groq-max-retries",
            "4",
            "--progress-every-chunks",
            "0",
        ]
    )

    settings = _resolve_collection_settings(args)

    assert settings.datasets == ["beers"]
    assert settings.difficulties == ["medium"]
    assert settings.seeds == 3
    assert settings.groq_timeout_s == 7.0
    assert settings.groq_max_retries == 4
    assert settings.progress_every_chunks == 0


def test_deadline_stops_before_stub_client_is_called() -> None:
    client = _StubClient(
        [
            GroqCompletion(
                text='{"action":"finish"}', prompt_tokens=1, completion_tokens=1, warnings=()
            )
        ]
    )

    with pytest.raises(RuntimeError, match="runtime deadline"):
        collect_episode_trajectories(
            _dataset(),
            difficulty="easy",
            seed=0,
            client=client,
            existing_keys=set(),
            budget=BudgetGuard(max_total_requests=4),
            min_episode_f1=0.6,
            deadline=RuntimeDeadline(started_at=time.monotonic() - 10, max_runtime_s=1),
        )

    assert client.calls == []


def test_push_readiness_gate_refuses_missing_jsonl(tmp_path: Path) -> None:
    with pytest.raises(SftReadinessError, match="Missing trajectory JSONL"):
        ensure_ready_for_push(output=tmp_path / "missing.jsonl", ready_min_records=32)


def test_collect_episode_filters_low_f1() -> None:
    client = _StubClient(
        [
            GroqCompletion(
                text='{"action":"finish"}', prompt_tokens=1, completion_tokens=1, warnings=()
            ),
            GroqCompletion(
                text='{"action":"finish"}', prompt_tokens=1, completion_tokens=1, warnings=()
            ),
        ]
    )

    records = collect_episode_trajectories(
        _dataset(),
        difficulty="easy",
        seed=0,
        client=client,
        existing_keys=set(),
        budget=BudgetGuard(max_total_requests=4),
        min_episode_f1=0.6,
    )

    assert records == []
    assert len(client.calls) == 2


def test_collect_episode_emits_auditable_chunk_records_when_episode_passes() -> None:
    client = _StubClient(
        [
            GroqCompletion(
                text='{"action":"finish"}', prompt_tokens=1, completion_tokens=1, warnings=()
            ),
            GroqCompletion(
                text=(
                    '{"action":"submit_repairs","repairs":['
                    '{"row":1,"column":"Phone","new_value":"2175550202","reason":"phone"},'
                    '{"row":1,"column":"Score","new_value":"4.5","reason":"score"}]}'
                ),
                prompt_tokens=1,
                completion_tokens=1,
                warnings=(),
            ),
        ]
    )

    records = collect_episode_trajectories(
        _dataset(),
        difficulty="medium",
        seed=3,
        client=client,
        existing_keys=set(),
        budget=BudgetGuard(max_total_requests=4),
        min_episode_f1=0.6,
    )

    assert [record["chunk_index"] for record in records] == [0, 1]
    assert records[1]["fix"][0]["new_value"] == "2175550202"
    assert records[1]["metrics"]["episode_f1"] == 1.0
    assert records[1]["messages"][-1]["role"] == "assistant"


def test_main_slices_accepted_episode_to_remaining_trajectory_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeGroqClient:
        responses = [
            GroqCompletion(
                text='{"action":"finish"}', prompt_tokens=1, completion_tokens=1, warnings=()
            ),
            GroqCompletion(
                text=(
                    '{"action":"submit_repairs","repairs":['
                    '{"row":1,"column":"Phone","new_value":"2175550202","reason":"phone"},'
                    '{"row":1,"column":"Score","new_value":"4.5","reason":"score"}]}'
                ),
                prompt_tokens=1,
                completion_tokens=1,
                warnings=(),
            ),
        ]

        def __init__(self, *, model: str, **_: object) -> None:
            self.model = model

        def complete(self, messages: list[dict[str, str]]) -> GroqCompletion:
            return self.responses.pop(0)

    output = tmp_path / "expert_v1.jsonl"
    monkeypatch.setenv("DATAFORGE_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("scripts.data.collect_sft_trajectories.GroqBenchClient", _FakeGroqClient)
    monkeypatch.setattr(
        "scripts.data.collect_sft_trajectories.load_real_world_dataset",
        lambda *_args, **_kwargs: _dataset(),
    )

    result = main(
        [
            "--preset",
            "smoke",
            "--output",
            str(output),
            "--max-trajectories",
            "1",
            "--seeds",
            "1",
            "--max-total-requests",
            "4",
            "--daily-request-budget",
            "4",
            "--progress-every-chunks",
            "0",
        ]
    )

    assert result == 0
    assert len(output.read_text(encoding="utf-8").splitlines()) == 1
