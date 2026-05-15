"""Unit tests for the Hugging Face SFT release verifier."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

import scripts.model.publish_dataset_readme as dataset_readme_publisher
from scripts.model.publish_dataset_readme import publish_dataset_readme
from scripts.model.verify_sft_release import (
    DEFAULT_DATASET_REPO,
    DEFAULT_MODEL_REPO,
    ReleaseVerificationError,
    verify_sft_release,
)


@dataclass(frozen=True)
class _Sibling:
    rfilename: str


@dataclass(frozen=True)
class _RepoInfo:
    sha: str
    siblings: list[_Sibling]


class _FakeApi:
    def __init__(self, *, model_files: set[str], dataset_files: set[str]) -> None:
        self.model_files = model_files
        self.dataset_files = dataset_files

    def repo_info(
        self,
        repo_id: str,
        *,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> _RepoInfo:
        files = self.model_files if repo_type == "model" else self.dataset_files
        return _RepoInfo(sha=f"{repo_type}-sha", siblings=[_Sibling(name) for name in files])


def _files(
    tmp_path: Path, *, metrics: dict[str, object] | None = None
) -> dict[tuple[str, str], Path]:
    metrics_payload = metrics or {
        "model_name": "DataForge-0.5B-SFT",
        "model_license": "apache-2.0",
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "teacher_model": "llama-3.3-70b-versatile",
        "dataset_repo": DEFAULT_DATASET_REPO,
        "training_examples": 29,
        "kaggle_hours": 0.906,
        "base_f1": 0.0,
        "sft_f1": 0.0,
        "repo_id": DEFAULT_MODEL_REPO,
    }
    model_metrics = tmp_path / "training_metrics.json"
    model_metrics.write_text(json.dumps(metrics_payload), encoding="utf-8")
    model_readme = tmp_path / "model_README.md"
    model_readme.write_text("# DataForge-0.5B-SFT\n\nHeld-out F1: 0.0\n", encoding="utf-8")
    dataset_readme = tmp_path / "dataset_README.md"
    dataset_readme.write_text(
        "# DataForge SFT Trajectories\n\nSchema: expert_v1.\n",
        encoding="utf-8",
    )
    jsonl = tmp_path / "expert_v1.jsonl"
    jsonl.write_text(
        "".join(json.dumps({"schema_version": "expert_v1", "i": i}) + "\n" for i in range(32)),
        encoding="utf-8",
    )
    split_manifest = tmp_path / "split_manifest.json"
    split_manifest.write_text(
        json.dumps({"schema_version": "split_manifest_v1", "datasets": []}),
        encoding="utf-8",
    )
    return {
        ("model", "training_metrics.json"): model_metrics,
        ("model", "README.md"): model_readme,
        ("dataset", "README.md"): dataset_readme,
        ("dataset", "expert_v1.jsonl"): jsonl,
        ("dataset", "split_manifest.json"): split_manifest,
    }


def test_release_verifier_accepts_complete_smoke_release(tmp_path: Path) -> None:
    files = _files(tmp_path)

    def downloader(
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        return str(files[(str(repo_type), filename)])

    evidence = verify_sft_release(
        api=_FakeApi(
            model_files={
                "README.md",
                "config.json",
                "model.safetensors",
                "tokenizer.json",
                "tokenizer_config.json",
                "training_metrics.json",
            },
            dataset_files={
                "README.md",
                "expert_v1.jsonl",
                "split_manifest.json",
                "sft_05b.yaml",
                "MODEL_CARD_TEMPLATE.md",
            },
        ),
        downloader=downloader,
    )

    assert evidence.model.sha == "model-sha"
    assert evidence.dataset.sha == "dataset-sha"
    assert evidence.dataset_records == 32
    assert evidence.metrics["sft_f1"] == 0.0
    assert evidence.quality_milestone is False
    assert evidence.release_status == "pipeline_complete_no_heldout_gain"


def test_release_verifier_rejects_missing_dataset_readme(tmp_path: Path) -> None:
    files = _files(tmp_path)

    def downloader(
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        return str(files[(str(repo_type), filename)])

    with pytest.raises(ReleaseVerificationError, match="README.md"):
        verify_sft_release(
            api=_FakeApi(
                model_files={
                    "README.md",
                    "config.json",
                    "model.safetensors",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "training_metrics.json",
                },
                dataset_files={"expert_v1.jsonl", "sft_05b.yaml", "MODEL_CARD_TEMPLATE.md"},
            ),
            downloader=downloader,
        )


def test_release_verifier_rejects_unresolved_readme_placeholder(tmp_path: Path) -> None:
    files = _files(tmp_path)
    files[("model", "README.md")].write_text("# {model_name}\n", encoding="utf-8")

    def downloader(
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        return str(files[(str(repo_type), filename)])

    with pytest.raises(ReleaseVerificationError, match="placeholder"):
        verify_sft_release(
            api=_FakeApi(
                model_files={
                    "README.md",
                    "config.json",
                    "model.safetensors",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "training_metrics.json",
                },
                dataset_files={
                    "README.md",
                    "expert_v1.jsonl",
                    "split_manifest.json",
                    "sft_05b.yaml",
                    "MODEL_CARD_TEMPLATE.md",
                },
            ),
            downloader=downloader,
        )


def test_release_verifier_rejects_invalid_metric_range(tmp_path: Path) -> None:
    metrics = {
        "model_name": "DataForge-0.5B-SFT",
        "model_license": "apache-2.0",
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "teacher_model": "llama-3.3-70b-versatile",
        "dataset_repo": DEFAULT_DATASET_REPO,
        "training_examples": 29,
        "kaggle_hours": 0.906,
        "base_f1": 2.0,
        "sft_f1": 0.0,
        "repo_id": DEFAULT_MODEL_REPO,
    }
    files = _files(tmp_path, metrics=metrics)

    def downloader(
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        return str(files[(str(repo_type), filename)])

    with pytest.raises(ReleaseVerificationError, match="base_f1"):
        verify_sft_release(
            api=_FakeApi(
                model_files={
                    "README.md",
                    "config.json",
                    "model.safetensors",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "training_metrics.json",
                },
                dataset_files={
                    "README.md",
                    "expert_v1.jsonl",
                    "split_manifest.json",
                    "sft_05b.yaml",
                    "MODEL_CARD_TEMPLATE.md",
                },
            ),
            downloader=downloader,
        )


def test_release_verifier_checks_dataset_sha_when_required(tmp_path: Path) -> None:
    metrics = {
        "model_name": "DataForge-0.5B-SFT",
        "model_license": "apache-2.0",
        "base_model": "Qwen/Qwen2.5-0.5B-Instruct",
        "teacher_model": "llama-3.3-70b-versatile",
        "dataset_repo": DEFAULT_DATASET_REPO,
        "training_examples": 29,
        "kaggle_hours": 0.906,
        "base_f1": 0.0,
        "sft_f1": 0.1,
        "repo_id": DEFAULT_MODEL_REPO,
        "dataset_sha": "dataset-sha",
    }
    files = _files(tmp_path, metrics=metrics)

    def downloader(
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        return str(files[(str(repo_type), filename)])

    evidence = verify_sft_release(
        api=_FakeApi(
            model_files={
                "README.md",
                "config.json",
                "model.safetensors",
                "tokenizer.json",
                "tokenizer_config.json",
                "training_metrics.json",
            },
            dataset_files={
                "README.md",
                "expert_v1.jsonl",
                "split_manifest.json",
                "sft_05b.yaml",
                "MODEL_CARD_TEMPLATE.md",
            },
        ),
        downloader=downloader,
        require_sha_metrics=True,
    )

    assert evidence.dataset_sha_metric_checked is True
    assert evidence.quality_milestone is True
    assert evidence.release_status == "quality_improved"


def test_publish_dataset_readme_uploads_readme(tmp_path: Path) -> None:
    class _FakeDatasetCardApi:
        def __init__(self) -> None:
            self.uploaded: list[tuple[str, str]] = []

        def upload_file(
            self,
            *,
            path_or_fileobj: str,
            path_in_repo: str,
            repo_id: str,
            repo_type: str,
            token: str | None = None,
            commit_message: str,
        ) -> object:
            self.uploaded.append((repo_id, path_in_repo))
            return object()

    readme = tmp_path / "README.md"
    readme.write_text("# Dataset\n", encoding="utf-8")
    api = _FakeDatasetCardApi()

    repo_id = publish_dataset_readme(
        repo_id="tester/dataforge-sft-trajectories",
        readme=readme,
        token=None,
        api=api,
    )

    assert repo_id == "tester/dataforge-sft-trajectories"
    assert api.uploaded == [("tester/dataforge-sft-trajectories", "README.md")]


def test_publish_dataset_readme_cli_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(dataset_readme_publisher, "load_dotenv", lambda: False)
    monkeypatch.setattr(dataset_readme_publisher, "_resolve_hf_token", lambda: None)

    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        dataset_readme_publisher.main([])
