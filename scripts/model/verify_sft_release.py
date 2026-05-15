"""Verify the published DataForge SFT model and trajectory dataset on Hugging Face."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

DEFAULT_MODEL_REPO = "Praneshrajan15/DataForge-0.5B-SFT"
DEFAULT_DATASET_REPO = "Praneshrajan15/dataforge-sft-trajectories"
DEFAULT_MIN_DATASET_RECORDS = 32

REQUIRED_MODEL_FILES = frozenset(
    {
        "README.md",
        "config.json",
        "model.safetensors",
        "tokenizer.json",
        "tokenizer_config.json",
        "training_metrics.json",
    }
)
REQUIRED_DATASET_FILES = frozenset(
    {
        "README.md",
        "expert_v1.jsonl",
        "split_manifest.json",
        "sft_05b.yaml",
        "MODEL_CARD_TEMPLATE.md",
    }
)
REQUIRED_METRIC_FIELDS = frozenset(
    {
        "model_name",
        "model_license",
        "base_model",
        "teacher_model",
        "dataset_repo",
        "training_examples",
        "kaggle_hours",
        "base_f1",
        "sft_f1",
        "repo_id",
    }
)
PLACEHOLDER_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}|<you>|TBD|pending", re.IGNORECASE)


class HubSibling(Protocol):
    """Minimal Hugging Face sibling shape used by the verifier."""

    rfilename: str


class HubRepoInfo(Protocol):
    """Minimal Hugging Face repo-info shape used by the verifier."""

    siblings: list[HubSibling]
    sha: str | None


class HubApi(Protocol):
    """Protocol for the subset of HfApi used by this verifier."""

    def repo_info(
        self,
        repo_id: str,
        *,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> HubRepoInfo:
        """Return repository metadata."""


class DownloadFile(Protocol):
    """Callable shape for downloading one file from a Hub repo."""

    def __call__(
        self,
        repo_id: str,
        *,
        filename: str,
        repo_type: str | None = None,
        token: str | None = None,
    ) -> str:
        """Download a repo file and return a local path."""


class ReleaseVerificationError(RuntimeError):
    """Raised when a published SFT release is incomplete or dishonest."""


@dataclass(frozen=True, slots=True)
class RepoEvidence:
    """Verified evidence for one Hub repository."""

    repo_id: str
    repo_type: str
    sha: str
    files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    """Serializable verification report for a DataForge SFT release."""

    model: RepoEvidence
    dataset: RepoEvidence
    metrics: dict[str, Any]
    dataset_records: int
    quality_milestone: bool
    release_status: str
    dataset_sha_metric_checked: bool
    model_readme_checked: bool
    dataset_readme_checked: bool


def _repo_files(info: HubRepoInfo) -> tuple[str, ...]:
    """Return sorted repository file paths from Hugging Face metadata."""
    return tuple(sorted(sibling.rfilename for sibling in info.siblings))


def _missing(required: frozenset[str], files: tuple[str, ...]) -> list[str]:
    """Return required files missing from a repository file manifest."""
    file_set = set(files)
    return sorted(required - file_set)


def _download_text(
    repo_id: str,
    *,
    filename: str,
    repo_type: str,
    token: str | None,
    downloader: DownloadFile,
) -> str:
    """Download and read one UTF-8 Hub file."""
    path = Path(downloader(repo_id, filename=filename, repo_type=repo_type, token=token))
    return path.read_text(encoding="utf-8")


def _load_json(
    repo_id: str,
    *,
    filename: str,
    repo_type: str,
    token: str | None,
    downloader: DownloadFile,
) -> dict[str, Any]:
    """Download and parse a JSON object."""
    payload = json.loads(
        _download_text(
            repo_id,
            filename=filename,
            repo_type=repo_type,
            token=token,
            downloader=downloader,
        )
    )
    if not isinstance(payload, dict):
        raise ReleaseVerificationError(f"{repo_id}/{filename} must contain a JSON object.")
    return payload


def _assert_no_placeholders(text: str, *, repo_id: str, filename: str) -> None:
    """Reject model or dataset cards with obvious unresolved placeholders."""
    match = PLACEHOLDER_RE.search(text)
    if match:
        raise ReleaseVerificationError(
            f"{repo_id}/{filename} contains unresolved placeholder text: {match.group(0)!r}"
        )


def _assert_split_manifest_contract(text: str, *, repo_id: str) -> None:
    """Reject split manifests that are missing or leak label-bearing fields."""
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ReleaseVerificationError(f"{repo_id}/split_manifest.json must be a JSON object.")
    if payload.get("schema_version") != "split_manifest_v1":
        raise ReleaseVerificationError(
            f"{repo_id}/split_manifest.json schema_version must be split_manifest_v1."
        )
    forbidden = {
        "clean",
        "clean_value",
        "ground_truth",
        "new_value",
        "normalization_candidates",
        "repairs",
        "suggested_value",
    }

    def walk(value: object, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                if key_text in forbidden:
                    raise ReleaseVerificationError(
                        f"{repo_id}/split_manifest.json leaks label-bearing field {path}.{key_text}."
                    )
                walk(child, f"{path}.{key_text}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "manifest")


def _validate_metrics(metrics: dict[str, Any], *, model_repo: str, dataset_repo: str) -> None:
    """Validate model-card metrics and repo linkage."""
    missing = sorted(REQUIRED_METRIC_FIELDS - set(metrics))
    if missing:
        raise ReleaseVerificationError(
            "training_metrics.json missing required fields: " + ", ".join(missing)
        )
    if metrics["repo_id"] != model_repo:
        raise ReleaseVerificationError(
            f"training_metrics repo_id={metrics['repo_id']!r} does not match {model_repo!r}."
        )
    if metrics["dataset_repo"] != dataset_repo:
        raise ReleaseVerificationError(
            "training_metrics dataset_repo="
            f"{metrics['dataset_repo']!r} does not match {dataset_repo!r}."
        )
    if str(metrics["model_license"]).lower() != "apache-2.0":
        raise ReleaseVerificationError("model_license must be apache-2.0.")
    for field in ("training_examples", "kaggle_hours", "base_f1", "sft_f1"):
        if not isinstance(metrics[field], int | float):
            raise ReleaseVerificationError(f"training_metrics field {field} must be numeric.")
    for field in ("base_f1", "sft_f1"):
        value = float(metrics[field])
        if value < 0.0 or value > 1.0:
            raise ReleaseVerificationError(f"{field} must be in [0, 1], got {value}.")


def _validate_dataset_sha_metric(
    metrics: dict[str, Any],
    *,
    dataset_sha: str,
    require_sha_metrics: bool,
) -> bool:
    """Check optional training-time dataset SHA linkage."""
    recorded_sha = metrics.get("dataset_sha")
    if recorded_sha is None:
        if require_sha_metrics:
            raise ReleaseVerificationError(
                "training_metrics.json must include dataset_sha for a contract-v2 release."
            )
        return False
    if str(recorded_sha) != dataset_sha:
        raise ReleaseVerificationError(
            f"training_metrics dataset_sha={recorded_sha!r} does not match current "
            f"dataset repo SHA {dataset_sha!r}."
        )
    return True


def _release_status(metrics: dict[str, Any]) -> tuple[bool, str]:
    """Classify the release without overstating model quality."""
    base_f1 = float(metrics["base_f1"])
    sft_f1 = float(metrics["sft_f1"])
    if sft_f1 > base_f1:
        return True, "quality_improved"
    return False, "pipeline_complete_no_heldout_gain"


def _count_jsonl_records(
    repo_id: str,
    *,
    token: str | None,
    downloader: DownloadFile,
) -> int:
    """Count non-empty trajectory JSONL rows."""
    text = _download_text(
        repo_id,
        filename="expert_v1.jsonl",
        repo_type="dataset",
        token=token,
        downloader=downloader,
    )
    records = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ReleaseVerificationError(
                f"{repo_id}/expert_v1.jsonl:{line_number} must contain a JSON object."
            )
        records += 1
    return records


def verify_sft_release(
    *,
    model_repo: str = DEFAULT_MODEL_REPO,
    dataset_repo: str = DEFAULT_DATASET_REPO,
    min_dataset_records: int = DEFAULT_MIN_DATASET_RECORDS,
    api: HubApi | None = None,
    downloader: DownloadFile | None = None,
    token: str | None = None,
    require_sha_metrics: bool = False,
) -> ReleaseEvidence:
    """Verify model and dataset release artifacts on Hugging Face."""
    resolved_api: HubApi
    if api is None:
        from huggingface_hub import HfApi

        resolved_api = cast(HubApi, HfApi(token=token))
    else:
        resolved_api = api
    if downloader is None:
        from huggingface_hub import hf_hub_download

        downloader = hf_hub_download

    model_info = resolved_api.repo_info(model_repo, repo_type="model", token=token)
    dataset_info = resolved_api.repo_info(dataset_repo, repo_type="dataset", token=token)
    model_files = _repo_files(model_info)
    dataset_files = _repo_files(dataset_info)

    missing_model = _missing(REQUIRED_MODEL_FILES, model_files)
    if missing_model:
        raise ReleaseVerificationError(
            f"{model_repo} missing required files: {', '.join(missing_model)}"
        )
    missing_dataset = _missing(REQUIRED_DATASET_FILES, dataset_files)
    if missing_dataset:
        raise ReleaseVerificationError(
            f"{dataset_repo} missing required files: {', '.join(missing_dataset)}"
        )

    metrics = _load_json(
        model_repo,
        filename="training_metrics.json",
        repo_type="model",
        token=token,
        downloader=downloader,
    )
    _validate_metrics(metrics, model_repo=model_repo, dataset_repo=dataset_repo)
    dataset_sha_metric_checked = _validate_dataset_sha_metric(
        metrics,
        dataset_sha=dataset_info.sha or "unknown",
        require_sha_metrics=require_sha_metrics,
    )
    quality_milestone, release_status = _release_status(metrics)

    model_readme = _download_text(
        model_repo,
        filename="README.md",
        repo_type="model",
        token=token,
        downloader=downloader,
    )
    dataset_readme = _download_text(
        dataset_repo,
        filename="README.md",
        repo_type="dataset",
        token=token,
        downloader=downloader,
    )
    split_manifest_text = _download_text(
        dataset_repo,
        filename="split_manifest.json",
        repo_type="dataset",
        token=token,
        downloader=downloader,
    )
    _assert_no_placeholders(model_readme, repo_id=model_repo, filename="README.md")
    _assert_no_placeholders(dataset_readme, repo_id=dataset_repo, filename="README.md")
    _assert_split_manifest_contract(split_manifest_text, repo_id=dataset_repo)

    dataset_records = _count_jsonl_records(dataset_repo, token=token, downloader=downloader)
    if dataset_records < min_dataset_records:
        raise ReleaseVerificationError(
            f"{dataset_repo}/expert_v1.jsonl has {dataset_records} records; "
            f"need at least {min_dataset_records}."
        )
    if int(metrics["training_examples"]) > dataset_records:
        raise ReleaseVerificationError(
            "training_examples cannot exceed available dataset records "
            f"({metrics['training_examples']}>{dataset_records})."
        )

    return ReleaseEvidence(
        model=RepoEvidence(
            repo_id=model_repo,
            repo_type="model",
            sha=model_info.sha or "unknown",
            files=model_files,
        ),
        dataset=RepoEvidence(
            repo_id=dataset_repo,
            repo_type="dataset",
            sha=dataset_info.sha or "unknown",
            files=dataset_files,
        ),
        metrics=metrics,
        dataset_records=dataset_records,
        quality_milestone=quality_milestone,
        release_status=release_status,
        dataset_sha_metric_checked=dataset_sha_metric_checked,
        model_readme_checked=True,
        dataset_readme_checked=True,
    )


def write_report(evidence: ReleaseEvidence, output: Path) -> None:
    """Write release verification evidence as stable JSON."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(evidence), indent=2, sort_keys=True), encoding="utf-8")


def _print_summary(evidence: ReleaseEvidence) -> None:
    """Render a compact terminal summary."""
    table = Table(title="DataForge SFT Release Verification")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("Model repo", evidence.model.repo_id)
    table.add_row("Model SHA", evidence.model.sha)
    table.add_row("Dataset repo", evidence.dataset.repo_id)
    table.add_row("Dataset SHA", evidence.dataset.sha)
    table.add_row("Dataset records", str(evidence.dataset_records))
    table.add_row("Training examples", str(evidence.metrics["training_examples"]))
    table.add_row("Base F1", str(evidence.metrics["base_f1"]))
    table.add_row("SFT F1", str(evidence.metrics["sft_f1"]))
    table.add_row("Release status", evidence.release_status)
    Console().print(table)


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-repo", default=DEFAULT_MODEL_REPO)
    parser.add_argument("--dataset-repo", default=DEFAULT_DATASET_REPO)
    parser.add_argument("--min-dataset-records", type=int, default=DEFAULT_MIN_DATASET_RECORDS)
    parser.add_argument("--require-sha-metrics", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the release verifier CLI."""
    load_dotenv()
    args = _build_parser().parse_args(argv)
    token = (os.environ.get("HF_TOKEN") or "").strip() or None
    if token is None:
        try:
            from huggingface_hub import get_token

            token = get_token()
        except ImportError:
            token = None
    try:
        evidence = verify_sft_release(
            model_repo=args.model_repo,
            dataset_repo=args.dataset_repo,
            min_dataset_records=args.min_dataset_records,
            token=token,
            require_sha_metrics=args.require_sha_metrics,
        )
    except ReleaseVerificationError as exc:
        print(f"SFT release verification failed: {exc}", file=sys.stderr)
        return 2
    _print_summary(evidence)
    if args.output is not None:
        write_report(evidence, args.output)
        Console().print(f"Wrote verification report to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
