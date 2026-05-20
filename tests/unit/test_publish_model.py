"""Unit tests for the Week 9 Hugging Face publishing helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.publish_model import ModelCardError, publish_model, render_model_card, resolve_repo_id


class _FakeHfApi:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.uploaded: list[tuple[str, str]] = []

    def whoami(self, token: str | None = None) -> dict[str, str]:
        return {"name": "tester"}

    def create_repo(
        self,
        *,
        repo_id: str,
        repo_type: str,
        exist_ok: bool,
        token: str | None = None,
    ) -> object:
        self.created.append((repo_id, repo_type))
        return object()

    def upload_folder(
        self,
        *,
        folder_path: str,
        repo_id: str,
        repo_type: str,
        token: str | None = None,
        commit_message: str,
    ) -> object:
        self.uploaded.append((repo_id, Path(folder_path).name))
        return object()


def test_resolve_repo_id_uses_hf_whoami_for_auto() -> None:
    assert resolve_repo_id("auto", api=_FakeHfApi(), token=None) == "tester/DataForge-0.5B-SFT"


def test_render_model_card_refuses_missing_required_fields() -> None:
    with pytest.raises(ModelCardError, match="model_license"):
        render_model_card("# {model_name}\nLicense: {model_license}\n", {"model_name": "demo"})


def test_publish_model_renders_card_and_uploads_folder(tmp_path: Path) -> None:
    model_dir = tmp_path / "merged"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    metrics = {
        "model_name": "DataForge-0.5B-SFT",
        "model_license": "apache-2.0",
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "teacher_model": "llama-3.3-70b-versatile",
        "dataset_repo": "tester/dataforge-sft-trajectories",
        "training_examples": 12,
        "kaggle_hours": 1.25,
        "base_f1": 0.12,
        "sft_f1": 0.18,
    }
    (model_dir / "training_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    template = tmp_path / "MODEL_CARD_TEMPLATE.md"
    template.write_text(
        "# {model_name}\n"
        "License: {model_license}\n"
        "Base: {base_model}\n"
        "Training Data: {trajectory_filename}\n"
        "F1: {sft_f1}\n",
        encoding="utf-8",
    )
    api = _FakeHfApi()

    repo_id = publish_model(
        model_dir=model_dir,
        card_template=template,
        repo_id="auto",
        api=api,
        token=None,
    )

    assert repo_id == "tester/DataForge-0.5B-SFT"
    assert api.created == [("tester/DataForge-0.5B-SFT", "model")]
    assert api.uploaded == [("tester/DataForge-0.5B-SFT", "merged")]
    card = (model_dir / "README.md").read_text(encoding="utf-8")
    assert card.startswith("# DataForge")
    assert "Training Data: expert_v3.jsonl" in card
