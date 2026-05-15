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
        "environment": {"pip_packages": ["trl==1.4.0", "transformers==5.7.0"]},
        "repos": {"trajectory_filename": "expert_v1.jsonl"},
        "model": {"base_model": "Qwen/Qwen2.5-0.5B-Instruct"},
        "lora": {"r": 16},
        "training": {
            "fp16": True,
            "bf16": False,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 16,
            "max_seq_length": 1024,
            "loss_type": "chunked_nll",
        },
        "collection": {
            "schema_version": "expert_v1",
            "min_episode_f1": 0.6,
            "teacher_model": "llama-3.3-70b-versatile",
        },
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _oracle_config(path: Path) -> Path:
    config = {
        "environment": {"pip_packages": ["trl==1.4.0", "transformers==5.7.0"]},
        "repos": {"trajectory_filename": "expert_v1.jsonl"},
        "model": {"base_model": "Qwen/Qwen2.5-0.5B-Instruct"},
        "lora": {"r": 16},
        "training": {
            "fp16": True,
            "bf16": False,
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 16,
            "max_seq_length": 1024,
            "loss_type": "chunked_nll",
        },
        "collection": {
            "schema_version": "expert_v1",
            "min_episode_f1": 0.6,
            "teacher_model": "llama-3.3-70b-versatile",
            "collection_methods": ["oracle_from_clean_diff"],
            "oracle": {"provider": "oracle", "model": "clean-diff-v1"},
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


def _oracle_record(seed: int) -> dict[str, object]:
    return {
        "schema_version": "expert_v1",
        "trajectory_id": f"flights:easy:{seed}:0",
        "task_id": "flights:easy",
        "dataset": "flights",
        "difficulty": "easy",
        "seed": seed,
        "chunk_index": 0,
        "state": {
            "split": "train",
            "target_rows": [{"_row": "0", "sched_dep_time": ""}],
            "context_rows": [{"_row": "0", "sched_dep_time": ""}],
            "normalization_candidates": [],
        },
        "tool_calls": [],
        "diagnosis": ["oracle clean diff"],
        "fix": [
            {
                "row": 0,
                "column": "sched_dep_time",
                "new_value": "7:00 p.m.",
                "reason": "oracle clean diff",
            }
        ],
        "messages": [{"role": "user", "content": "repair"}],
        "teacher": {"provider": "oracle", "model": "clean-diff-v1"},
        "metrics": {"episode_f1": 1.0, "chunk_f1": 1.0},
        "provenance": {
            "citation": "fixture citation",
            "collection_method": "oracle_from_clean_diff",
            "split": "train",
            "eval_rows": [1],
        },
    }


def _jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _split_manifest(path: Path) -> Path:
    payload = {
        "schema_version": "split_manifest_v1",
        "collection_method": "oracle_from_clean_diff",
        "split_seed": 42,
        "eval_fraction": 0.1,
        "min_eval_rows": 1,
        "datasets": [
            {
                "dataset": "flights",
                "n_rows": 2,
                "n_columns": 2,
                "train_rows": 1,
                "eval_rows": 1,
                "train": [{"row": 0, "dirty_row_sha256": "a" * 64}],
                "eval": [{"row": 1, "dirty_row_sha256": "b" * 64}],
            }
        ],
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
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
    assert report.collection_methods == ("llm_react_chunk",)


def test_readiness_accepts_configured_cerebras_teacher(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["collection"]["teacher_provider"] = "cerebras"
    config["collection"]["teacher_model"] = "llama3.1-8b"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    record_0 = _record(0)
    record_1 = _record(1)
    for record in (record_0, record_1):
        record["teacher"] = {
            "provider": "cerebras",
            "model": "llama3.1-8b",
        }
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [record_0, record_1])

    report = validate_sft_readiness(
        jsonl=jsonl,
        config_path=config_path,
        split_manifest=_split_manifest(tmp_path / "split_manifest.json"),
        min_records=2,
    )

    assert report.records == 2


def test_readiness_accepts_explicit_legacy_teacher_allowlist(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["collection"]["teacher_provider"] = "cerebras"
    config["collection"]["teacher_model"] = "llama3.1-8b"
    config["collection"]["accepted_teachers"] = [
        {"provider": "groq", "model": "llama-3.3-70b-versatile"},
        {"provider": "cerebras", "model": "llama3.1-8b"},
    ]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_record(0), _record(1)])

    report = validate_sft_readiness(
        jsonl=jsonl,
        config_path=config_path,
        min_records=2,
    )

    assert report.records == 2


def test_readiness_accepts_oracle_clean_diff_records(tmp_path: Path) -> None:
    config_path = _oracle_config(tmp_path / "sft_05b.yaml")
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_oracle_record(0), _oracle_record(1)])

    report = validate_sft_readiness(
        jsonl=jsonl,
        config_path=config_path,
        min_records=2,
    )

    assert report.collection_methods == ("oracle_from_clean_diff",)
    assert report.train_rows == 1
    assert report.heldout_rows == 1


def test_readiness_rejects_oracle_eval_row_leakage(tmp_path: Path) -> None:
    config_path = _oracle_config(tmp_path / "sft_05b.yaml")
    record = _oracle_record(0)
    state = record["state"]
    assert isinstance(state, dict)
    state["context_rows"] = [{"_row": "1", "sched_dep_time": "heldout"}]
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [record, _oracle_record(1)])

    with pytest.raises(SftReadinessError, match="leaks held-out eval row"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            split_manifest=_split_manifest(tmp_path / "split_manifest.json"),
            min_records=2,
        )


def test_readiness_rejects_oracle_clean_label_candidates(tmp_path: Path) -> None:
    config_path = _oracle_config(tmp_path / "sft_05b.yaml")
    record = _oracle_record(0)
    state = record["state"]
    assert isinstance(state, dict)
    state["normalization_candidates"] = [
        {
            "row": 0,
            "column": "sched_dep_time",
            "current_value": "",
            "suggested_value": "7:00 p.m.",
        }
    ]
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [record, _oracle_record(1)])

    with pytest.raises(SftReadinessError, match="leaks oracle clean labels"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            split_manifest=_split_manifest(tmp_path / "split_manifest.json"),
            min_records=2,
        )


def test_readiness_rejects_missing_split_manifest_when_requested(tmp_path: Path) -> None:
    config_path = _oracle_config(tmp_path / "sft_05b.yaml")
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_oracle_record(0), _oracle_record(1)])

    with pytest.raises(SftReadinessError, match="Missing split manifest"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            split_manifest=tmp_path / "missing_manifest.json",
            min_records=2,
        )


def test_readiness_rejects_split_manifest_label_leakage(tmp_path: Path) -> None:
    config_path = _oracle_config(tmp_path / "sft_05b.yaml")
    jsonl = _jsonl(tmp_path / "expert_v1.jsonl", [_oracle_record(0), _oracle_record(1)])
    manifest = json.loads(_split_manifest(tmp_path / "split_manifest.json").read_text())
    manifest["datasets"][0]["train"][0]["clean_value"] = "7:00 p.m."
    manifest_path = tmp_path / "leaky_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SftReadinessError, match="label-bearing field"):
        validate_sft_readiness(
            jsonl=jsonl,
            config_path=config_path,
            split_manifest=manifest_path,
            min_records=2,
        )


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


def test_config_rejects_stale_t4_training_settings(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["training"]["loss_type"] = "nll"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(SftReadinessError, match="stale"):
        load_config(config_path)


def test_config_rejects_old_trl_pin_for_chunked_nll(tmp_path: Path) -> None:
    config_path = _config(tmp_path / "sft_05b.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["environment"]["pip_packages"] = ["trl==1.3.0", "transformers==5.7.0"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(SftReadinessError, match="trl==1.4.0"):
        load_config(config_path)
