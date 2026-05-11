"""Unit tests for the Week 9 SFT Kaggle readiness gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.data.validate_sft_readiness import (
    SftReadinessError,
    load_config,
    validate_sft_readiness,
)


def _config(path: Path) -> Path:
    config = {
        "environment": {"pip_packages": ["trl==1.3.0", "transformers==5.7.0"]},
        "repos": {"trajectory_filename": "expert_v1.jsonl"},
        "model": {"base_model": "Qwen/Qwen2.5-0.5B-Instruct"},
        "lora": {"r": 16},
        "training": {"fp16": True, "bf16": False},
        "collection": {
            "schema_version": "expert_v1",
            "min_episode_f1": 0.6,
            "teacher_model": "llama-3.3-70b-versatile",
        },
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _record(seed: int) -> dict[str, object]:
    return {
        "schema_version": "expert_v1",
        "trajectory_id": f"hospital:easy:{seed}:0",
        "task_id": "hospital:easy",
        "dataset": "hospital",
        "difficulty": "easy",
        "seed": seed,
        "chunk_index": 0,
        "state": {"rows": []},
        "tool_calls": [],
        "diagnosis": [],
        "fix": [],
        "messages": [{"role": "user", "content": "repair"}],
        "teacher": {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        "metrics": {"episode_f1": 0.75, "chunk_f1": 0.0},
        "provenance": {"citation": "fixture citation"},
    }


def _jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def test_readiness_accepts_valid_handoff(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_record(0), _record(1), _record(2)])

    report = validate_sft_readiness(
        jsonl=jsonl,
        config_path=config_path,
        min_records=2,
        holdout_records=1,
    )

    assert report.records == 3
    assert report.train_records == 2
    assert report.heldout_records == 1
    assert report.datasets == ("hospital",)


def test_readiness_fails_when_jsonl_missing(tmp_path: Path) -> None:
    with pytest.raises(SftReadinessError, match="Missing trajectory JSONL"):
        validate_sft_readiness(
            jsonl=tmp_path / "missing.jsonl",
            config_path=_config(tmp_path / "sft_05b.yaml"),
            min_records=2,
        )


def test_readiness_rejects_duplicate_chunk_keys(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    duplicate = _record(0)
    duplicate["trajectory_id"] = "different-id"
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_record(0), duplicate])

    with pytest.raises(SftReadinessError, match="Duplicate chunk key"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            min_records=2,
        )


def test_readiness_rejects_low_episode_f1(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    low_f1 = _record(1)
    low_f1["metrics"] = {"episode_f1": 0.2, "chunk_f1": 0.0}
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_record(0), low_f1])

    with pytest.raises(SftReadinessError, match="episode_f1"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            min_records=2,
        )


def test_config_rejects_unpinned_kaggle_package(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["environment"]["pip_packages"] = ["trl>=1.3.0"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(SftReadinessError, match="exact"):
        load_config(config_path)
