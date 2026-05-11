"""Validate that Week 9 SFT artifacts are ready before launching Kaggle."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml
from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data.collect_sft_trajectories import validate_trajectory_record  # noqa: E402

DEFAULT_CONFIG = Path("training/configs/sft_05b.yaml")
DEFAULT_JSONL = Path("data/sft_traj/expert_v1.jsonl")
DEFAULT_MIN_RECORDS = 32
DEFAULT_HOLDOUT_RECORDS = 100


class SftReadinessError(RuntimeError):
    """Raised when the SFT handoff is not ready for Kaggle."""


@dataclass(frozen=True, slots=True)
class SftReadinessReport:
    """Small summary of the validated SFT handoff."""

    records: int
    train_records: int
    heldout_records: int
    datasets: tuple[str, ...]
    difficulties: tuple[str, ...]
    teacher_model: str
    package_count: int


def _as_mapping(value: object, *, name: str) -> dict[str, Any]:
    """Return a JSON/YAML object as a string-keyed mapping."""
    if not isinstance(value, dict):
        raise SftReadinessError(f"{name} must be a mapping.")
    return cast(dict[str, Any], value)


def load_config(path: Path) -> dict[str, Any]:
    """Load and minimally validate the Kaggle SFT YAML config."""
    if not path.exists():
        raise SftReadinessError(f"Missing SFT config: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = _as_mapping(payload, name=str(path))
    for section in ("environment", "repos", "model", "lora", "training", "collection"):
        if section not in config:
            raise SftReadinessError(f"Config is missing required section: {section}")

    packages = _as_mapping(config["environment"], name="environment").get("pip_packages")
    if not isinstance(packages, list) or not packages:
        raise SftReadinessError("environment.pip_packages must be a non-empty list.")
    bad_packages = [package for package in packages if not isinstance(package, str)]
    if bad_packages:
        raise SftReadinessError("environment.pip_packages must contain only strings.")
    unpinned = [package for package in packages if "==" not in package]
    if unpinned:
        raise SftReadinessError(
            "Kaggle package pins must be exact. Unpinned entries: " + ", ".join(map(str, unpinned))
        )

    training = _as_mapping(config["training"], name="training")
    if training.get("fp16") is not True or training.get("bf16") is not False:
        raise SftReadinessError("Kaggle config must use fp16=True and bf16=False.")
    return config


def load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    """Load and schema-validate trajectory JSONL records."""
    if not path.exists():
        raise SftReadinessError(
            f"Missing trajectory JSONL: {path}. Run collect_sft_trajectories.py "
            "with --push-to-hub before starting Kaggle."
        )
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw_record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SftReadinessError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
        if not isinstance(raw_record, dict):
            raise SftReadinessError(f"{path}:{line_number} must contain a JSON object.")
        records.append(validate_trajectory_record(cast(dict[str, Any], raw_record)))
    if not records:
        raise SftReadinessError(f"Trajectory JSONL is empty: {path}")
    return records


def _split_sizes(record_count: int, holdout_records: int) -> tuple[int, int]:
    """Return deterministic train/held-out sizes matching the Kaggle notebook."""
    test_size = min(holdout_records, max(1, record_count // 10))
    train_size = record_count - test_size
    if train_size < 1 or test_size < 1:
        raise SftReadinessError(
            "Need at least two trajectory records so train/held-out split is non-empty."
        )
    return train_size, test_size


def validate_records(
    records: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    min_records: int = DEFAULT_MIN_RECORDS,
    holdout_records: int = DEFAULT_HOLDOUT_RECORDS,
) -> SftReadinessReport:
    """Validate trajectory content against the YAML contract."""
    if min_records < 2:
        raise ValueError("min_records must be >= 2")
    if holdout_records < 1:
        raise ValueError("holdout_records must be >= 1")
    if len(records) < min_records:
        raise SftReadinessError(
            f"Only {len(records)} trajectory records found; need at least {min_records} "
            "before Kaggle training is worth launching."
        )

    collection = _as_mapping(config["collection"], name="collection")
    expected_schema = str(collection["schema_version"])
    expected_min_f1 = float(collection["min_episode_f1"])
    expected_teacher = str(collection["teacher_model"])

    trajectory_ids: set[str] = set()
    chunk_keys: set[tuple[str, int, int]] = set()
    datasets: set[str] = set()
    difficulties: set[str] = set()
    for index, record in enumerate(records, start=1):
        if record["schema_version"] != expected_schema:
            raise SftReadinessError(
                f"Record {index} has schema_version={record['schema_version']!r}; "
                f"expected {expected_schema!r}."
            )
        trajectory_id = str(record["trajectory_id"])
        if trajectory_id in trajectory_ids:
            raise SftReadinessError(f"Duplicate trajectory_id: {trajectory_id}")
        trajectory_ids.add(trajectory_id)

        chunk_key = (str(record["task_id"]), int(record["seed"]), int(record["chunk_index"]))
        if chunk_key in chunk_keys:
            raise SftReadinessError(
                "Duplicate chunk key: "
                f"task_id={chunk_key[0]} seed={chunk_key[1]} chunk_index={chunk_key[2]}"
            )
        chunk_keys.add(chunk_key)

        metrics = _as_mapping(record["metrics"], name=f"record {index} metrics")
        episode_f1 = float(metrics.get("episode_f1", -1.0))
        if episode_f1 < expected_min_f1:
            raise SftReadinessError(
                f"Record {index} has episode_f1={episode_f1}; expected >= {expected_min_f1}."
            )

        teacher = _as_mapping(record["teacher"], name=f"record {index} teacher")
        if str(teacher.get("model", "")) != expected_teacher:
            raise SftReadinessError(
                f"Record {index} teacher model {teacher.get('model')!r} does not match "
                f"config teacher_model={expected_teacher!r}."
            )
        if not record.get("messages"):
            raise SftReadinessError(f"Record {index} has no chat messages.")
        datasets.add(str(record["dataset"]))
        difficulties.add(str(record["difficulty"]))

    train_size, test_size = _split_sizes(len(records), holdout_records)
    packages = cast(
        list[str], _as_mapping(config["environment"], name="environment")["pip_packages"]
    )
    return SftReadinessReport(
        records=len(records),
        train_records=train_size,
        heldout_records=test_size,
        datasets=tuple(sorted(datasets)),
        difficulties=tuple(sorted(difficulties)),
        teacher_model=expected_teacher,
        package_count=len(packages),
    )


def validate_sft_readiness(
    *,
    jsonl: Path = DEFAULT_JSONL,
    config_path: Path = DEFAULT_CONFIG,
    min_records: int = DEFAULT_MIN_RECORDS,
    holdout_records: int = DEFAULT_HOLDOUT_RECORDS,
) -> SftReadinessReport:
    """Validate the local SFT handoff and return a compact report."""
    config = load_config(config_path)
    records = load_jsonl_records(jsonl)
    return validate_records(
        records,
        config=config,
        min_records=min_records,
        holdout_records=holdout_records,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--config", dest="config_path", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--min-records", type=int, default=DEFAULT_MIN_RECORDS)
    parser.add_argument("--holdout-records", type=int, default=DEFAULT_HOLDOUT_RECORDS)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the readiness validator CLI."""
    args = _build_parser().parse_args(argv)
    report = validate_sft_readiness(
        jsonl=args.jsonl,
        config_path=args.config_path,
        min_records=args.min_records,
        holdout_records=args.holdout_records,
    )
    table = Table(title="Week 9 SFT Kaggle Readiness")
    table.add_column("Check")
    table.add_column("Value")
    table.add_row("Trajectory records", str(report.records))
    table.add_row("Train records", str(report.train_records))
    table.add_row("Held-out records", str(report.heldout_records))
    table.add_row("Datasets", ", ".join(report.datasets))
    table.add_row("Difficulties", ", ".join(report.difficulties))
    table.add_row("Teacher model", report.teacher_model)
    table.add_row("Pinned packages", str(report.package_count))
    Console().print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
