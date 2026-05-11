"""Collect Week 9 chunk-level SFT trajectories from the Groq ReAct benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from rich.console import Console

from dataforge.bench.core import BenchmarkRepair, RepairScore, score_repairs
from dataforge.bench.groq_client import GroqBenchClient, GroqCompletion
from dataforge.bench.methods import (
    _chunk_records,
    _column_stats,
    _extract_json_object,
    _repairs_from_payload,
    chunk_row_indices,
)
from dataforge.datasets.real_world import GroundTruthCell, RealWorldDataset, load_real_world_dataset

Difficulty = Literal["easy", "medium"]
Preset = Literal["smoke", "full"]

SCHEMA_VERSION = "expert_v1"
DEFAULT_DATASETS: tuple[str, ...] = ("hospital", "flights", "beers")
DEFAULT_DIFFICULTIES: tuple[Difficulty, ...] = ("easy", "medium")
DEFAULT_OUTPUT = Path("data/sft_traj/expert_v1.jsonl")
DEFAULT_DATASET_REPO_NAME = "dataforge-sft-trajectories"
LIGHT_WINDOW_SIZES: dict[str, int] = {"easy": 48, "medium": 96}


@dataclass(frozen=True, slots=True)
class PresetDefaults:
    """Resolved defaults for one collection preset."""

    datasets: tuple[str, ...]
    difficulties: tuple[Difficulty, ...]
    seeds: int
    max_trajectories: int
    max_total_requests: int
    daily_request_budget: int
    min_interval_s: float
    groq_timeout_s: float
    groq_max_retries: int
    max_runtime_min: float | None
    progress_every_chunks: int
    ready_min_records: int


@dataclass(frozen=True, slots=True)
class CollectionSettings:
    """Collector settings after applying preset defaults and explicit CLI overrides."""

    preset: Preset
    datasets: list[str]
    difficulties: list[Difficulty]
    seeds: int
    max_trajectories: int
    min_episode_f1: float
    max_total_requests: int
    daily_request_budget: int
    groq_model: str
    groq_max_tokens: int
    min_interval_s: float
    groq_timeout_s: float
    groq_max_retries: int
    max_runtime_min: float | None
    progress_every_chunks: int
    ready_min_records: int


SMOKE_DEFAULTS = PresetDefaults(
    datasets=("hospital",),
    difficulties=("easy",),
    seeds=8,
    max_trajectories=32,
    max_total_requests=256,
    daily_request_budget=256,
    min_interval_s=1.0,
    groq_timeout_s=30.0,
    groq_max_retries=2,
    max_runtime_min=30.0,
    progress_every_chunks=1,
    ready_min_records=32,
)

FULL_DEFAULTS = PresetDefaults(
    datasets=DEFAULT_DATASETS,
    difficulties=DEFAULT_DIFFICULTIES,
    seeds=24,
    max_trajectories=2000,
    max_total_requests=2800,
    daily_request_budget=900,
    min_interval_s=2.0,
    groq_timeout_s=60.0,
    groq_max_retries=5,
    max_runtime_min=None,
    progress_every_chunks=20,
    ready_min_records=32,
)


class CompletionClient(Protocol):
    """Minimal protocol shared by GroqBenchClient and tests."""

    @property
    def model(self) -> str:
        """Return the teacher model identifier."""

    def complete(self, messages: list[dict[str, str]]) -> GroqCompletion:
        """Return a chat completion for the supplied messages."""


@dataclass(frozen=True, slots=True)
class TrajectoryKey:
    """Idempotency key for one chunk-level SFT example."""

    task_id: str
    seed: int
    chunk_index: int


@dataclass(slots=True)
class BudgetGuard:
    """Small request counter that fails before exceeding the configured budget."""

    max_total_requests: int
    daily_request_budget: int | None = None
    used_requests: int = 0

    def consume(self, requests: int = 1) -> None:
        """Consume request budget or raise before an over-budget API call."""
        if requests < 1:
            raise ValueError("requests must be positive")
        if self.used_requests + requests > self.max_total_requests:
            raise RuntimeError(
                "Groq request budget exhausted before collection completed "
                f"({self.used_requests + requests}>{self.max_total_requests})."
            )
        if (
            self.daily_request_budget is not None
            and self.used_requests + requests > self.daily_request_budget
        ):
            raise RuntimeError(
                "Groq daily request budget exhausted before collection completed "
                f"({self.used_requests + requests}>{self.daily_request_budget})."
            )
        self.used_requests += requests


@dataclass(frozen=True, slots=True)
class RuntimeDeadline:
    """Wall-clock guard for laptop-safe collection runs."""

    started_at: float
    max_runtime_s: float | None

    def elapsed_s(self) -> float:
        """Return elapsed wall-clock seconds."""
        return time.monotonic() - self.started_at

    def raise_if_expired(self) -> None:
        """Raise when the configured runtime deadline has been reached."""
        if self.max_runtime_s is None:
            return
        if self.elapsed_s() >= self.max_runtime_s:
            minutes = self.max_runtime_s / 60
            raise RuntimeError(f"Groq runtime deadline reached after {minutes:.1f} minutes.")


@dataclass(slots=True)
class ProgressReporter:
    """Small console progress reporter for long-running Groq collection."""

    console: Console
    deadline: RuntimeDeadline
    every_chunks: int
    accepted_records: int = 0
    chunks_seen: int = 0
    _log_current_chunk: bool = False

    def update_accepted(self, accepted_records: int) -> None:
        """Update the accepted trajectory count shown in later progress lines."""
        self.accepted_records = accepted_records

    def _enabled(self) -> bool:
        return self.every_chunks > 0

    def _elapsed(self) -> str:
        return f"{self.deadline.elapsed_s():.1f}s"

    def chunk_start(
        self,
        *,
        dataset: str,
        difficulty: Difficulty,
        seed: int,
        chunk_index: int,
        total_chunks: int,
        budget: BudgetGuard,
    ) -> None:
        """Print the start of a chunk when progress output is enabled for it."""
        self.chunks_seen += 1
        self._log_current_chunk = self._enabled() and (
            self.chunks_seen == 1 or self.chunks_seen % self.every_chunks == 0
        )
        if not self._log_current_chunk:
            return
        self.console.print(
            "[sft] chunk start "
            f"dataset={dataset} difficulty={difficulty} seed={seed} "
            f"chunk={chunk_index + 1}/{total_chunks} "
            f"requests={budget.used_requests}/{budget.max_total_requests} "
            f"accepted={self.accepted_records} elapsed={self._elapsed()}"
        )

    def api_start(
        self,
        *,
        label: str,
        dataset: str,
        difficulty: Difficulty,
        seed: int,
        chunk_index: int,
        budget: BudgetGuard,
    ) -> None:
        """Print before one Groq request."""
        if not self._log_current_chunk:
            return
        self.console.print(
            "[sft] api start   "
            f"phase={label} dataset={dataset} difficulty={difficulty} seed={seed} "
            f"chunk={chunk_index + 1} next_request={budget.used_requests + 1} "
            f"accepted={self.accepted_records} elapsed={self._elapsed()}"
        )

    def api_done(
        self,
        *,
        label: str,
        dataset: str,
        difficulty: Difficulty,
        seed: int,
        chunk_index: int,
        budget: BudgetGuard,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Print after one Groq request."""
        if not self._log_current_chunk:
            return
        self.console.print(
            "[sft] api done    "
            f"phase={label} dataset={dataset} difficulty={difficulty} seed={seed} "
            f"chunk={chunk_index + 1} requests={budget.used_requests}/{budget.max_total_requests} "
            f"tokens={prompt_tokens}+{completion_tokens} "
            f"accepted={self.accepted_records} elapsed={self._elapsed()}"
        )

    def chunk_done(
        self,
        *,
        dataset: str,
        difficulty: Difficulty,
        seed: int,
        chunk_index: int,
        repairs: int,
        llm_calls: int,
    ) -> None:
        """Print the end of a chunk when progress output is enabled for it."""
        if not self._log_current_chunk:
            return
        self.console.print(
            "[sft] chunk done  "
            f"dataset={dataset} difficulty={difficulty} seed={seed} "
            f"chunk={chunk_index + 1} repairs={repairs} llm_calls={llm_calls} "
            f"accepted={self.accepted_records} elapsed={self._elapsed()}"
        )


class TrajectoryRecord(BaseModel):
    """Validated on-disk JSONL schema for one SFT trajectory chunk."""

    schema_version: Literal["expert_v1"]
    trajectory_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    difficulty: Difficulty
    seed: int = Field(ge=0)
    chunk_index: int = Field(ge=0)
    state: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    diagnosis: list[Any]
    fix: list[dict[str, Any]]
    messages: list[dict[str, str]]
    teacher: dict[str, Any]
    metrics: dict[str, Any]
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChunkCollection:
    """Internal result for one ReAct chunk before episode-level filtering."""

    record: dict[str, Any]
    repairs: list[BenchmarkRepair]


def validate_trajectory_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a trajectory record for JSONL serialization."""
    return TrajectoryRecord.model_validate(record).model_dump(mode="json")


def existing_trajectory_keys(path: Path) -> set[TrajectoryKey]:
    """Load chunk-level idempotency keys from an existing JSONL file."""
    if not path.exists():
        return set()

    keys: set[TrajectoryKey] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = validate_trajectory_record(cast(dict[str, Any], json.loads(line)))
        keys.add(
            TrajectoryKey(
                task_id=str(record["task_id"]),
                seed=int(record["seed"]),
                chunk_index=int(record["chunk_index"]),
            )
        )
    return keys


def write_jsonl_records(path: Path, records: list[dict[str, Any]]) -> None:
    """Append validated trajectory records to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        return
    needs_leading_newline = (
        path.exists()
        and path.stat().st_size > 0
        and not path.read_text(encoding="utf-8").endswith("\n")
    )
    with path.open("a", encoding="utf-8") as handle:
        if needs_leading_newline:
            handle.write("\n")
        for record in records:
            validated = validate_trajectory_record(record)
            handle.write(json.dumps(validated, sort_keys=True) + "\n")


def _stable_offset(*, dataset_name: str, difficulty: Difficulty, seed: int, limit: int) -> int:
    """Return a deterministic offset in `[0, limit)` without Python hash randomization."""
    digest = hashlib.sha256(f"{dataset_name}:{difficulty}:{seed}".encode()).hexdigest()
    return int(digest[:12], 16) % limit


def build_light_dataset(
    dataset: RealWorldDataset,
    *,
    difficulty: Difficulty,
    seed: int,
) -> RealWorldDataset:
    """Build a deterministic DataForge-Bench-light window for one dataset/seed."""
    window_size = min(LIGHT_WINDOW_SIZES[difficulty], len(dataset.dirty_df.index))
    if window_size == len(dataset.dirty_df.index):
        return dataset

    error_rows = sorted({cell.row for cell in dataset.ground_truth})
    if error_rows:
        anchor = error_rows[
            _stable_offset(
                dataset_name=dataset.metadata.name,
                difficulty=difficulty,
                seed=seed,
                limit=len(error_rows),
            )
        ]
    else:
        anchor = _stable_offset(
            dataset_name=dataset.metadata.name,
            difficulty=difficulty,
            seed=seed,
            limit=len(dataset.dirty_df.index),
        )
    max_start = len(dataset.dirty_df.index) - window_size
    start = min(max(anchor - window_size // 2, 0), max_start)
    stop = start + window_size

    dirty_df = dataset.dirty_df.iloc[start:stop].reset_index(drop=True)
    clean_df = dataset.clean_df.iloc[start:stop].reset_index(drop=True)
    ground_truth: list[GroundTruthCell] = []
    for cell in dataset.ground_truth:
        if start <= cell.row < stop:
            ground_truth.append(
                GroundTruthCell(
                    row=cell.row - start,
                    column=cell.column,
                    dirty_value=cell.dirty_value,
                    clean_value=cell.clean_value,
                )
            )

    metadata = dataset.metadata.model_copy(update={"n_rows": len(dirty_df.index)})
    return RealWorldDataset(
        metadata=metadata,
        dirty_df=dirty_df,
        clean_df=clean_df,
        canonical_columns=dataset.canonical_columns,
        ground_truth=tuple(ground_truth),
    )


def _score_for_rows(
    ground_truth: tuple[GroundTruthCell, ...],
    repairs: list[BenchmarkRepair],
    row_indices: tuple[int, ...],
) -> RepairScore:
    """Score repairs against only the cells in one chunk."""
    chunk_truth = [cell for cell in ground_truth if cell.row in row_indices]
    return score_repairs(chunk_truth, repairs)


def _repairs_for_rows(
    repairs: list[BenchmarkRepair], row_indices: tuple[int, ...]
) -> list[BenchmarkRepair]:
    """Keep only repairs that target the active chunk rows."""
    allowed_rows = set(row_indices)
    return [repair for repair in repairs if repair.row in allowed_rows]


def _diagnosis_from_payloads(payloads: list[dict[str, Any]]) -> list[Any]:
    """Extract lightweight diagnostic text from ReAct payloads."""
    diagnosis: list[Any] = []
    for payload in payloads:
        raw = payload.get("diagnosis")
        if isinstance(raw, list):
            diagnosis.extend(raw)
        elif isinstance(raw, str):
            diagnosis.append(raw)
        for repair in (
            payload.get("repairs", []) if isinstance(payload.get("repairs"), list) else []
        ):
            if isinstance(repair, dict) and isinstance(repair.get("reason"), str):
                diagnosis.append(repair["reason"])
    return diagnosis


def _completion_payload(completion: GroqCompletion) -> dict[str, Any] | None:
    """Parse a Groq completion as a JSON object."""
    parsed = _extract_json_object(completion.text)
    if parsed is None:
        return None
    return cast(dict[str, Any], parsed)


def _collect_chunk(
    dataset: RealWorldDataset,
    *,
    difficulty: Difficulty,
    seed: int,
    chunk_index: int,
    row_indices: tuple[int, ...],
    client: CompletionClient,
    budget: BudgetGuard,
    deadline: RuntimeDeadline | None = None,
    progress: ProgressReporter | None = None,
) -> ChunkCollection:
    """Run the constrained ReAct loop for one chunk and return an auditable record."""
    task_id = f"{dataset.metadata.name}:{difficulty}"
    chunk_payload = _chunk_records(dataset, row_indices)
    context_payload = _chunk_records(dataset, tuple(range(len(dataset.dirty_df.index))))
    schema_summary = {
        "dataset": dataset.metadata.name,
        "columns": list(dataset.canonical_columns),
        "chunk_rows": len(row_indices),
        "target_row_indices": list(row_indices),
        "difficulty": difficulty,
        "seed": seed,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are benchmarking tabular data cleaning with a constrained tool loop. "
                "Use the full context rows to infer local patterns, but submit repairs only "
                "for the target row indices. Look for misspellings, placeholder values, and "
                "numeric scale errors such as a score written as 45 when neighboring scores "
                "use a 0-5 scale; repair that kind of value by inserting the missing decimal "
                "point, not by rounding to a neighboring integer. For placeholder phone or ID "
                "values, infer the replacement from same-group local sequences only when the "
                "pattern is clear. If any target cell is visibly wrong, prefer submit_repairs "
                "over finish. Return only one JSON action object with no prose, markdown, or "
                "comments. Allowed actions: "
                "inspect_rows, column_stats, submit_repairs, finish. submit_repairs must use "
                '{"action":"submit_repairs","repairs":[{"row":0,"column":"Column",'
                '"new_value":"value","reason":"why"}]}.'
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "schema_summary": schema_summary,
                    "target_rows": chunk_payload,
                    "context_rows": context_payload,
                },
                sort_keys=True,
            ),
        },
    ]

    llm_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    warnings: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []

    if deadline is not None:
        deadline.raise_if_expired()
    if progress is not None:
        progress.api_start(
            label="first",
            dataset=dataset.metadata.name,
            difficulty=difficulty,
            seed=seed,
            chunk_index=chunk_index,
            budget=budget,
        )
    budget.consume()
    first = client.complete(messages)
    llm_calls += 1
    prompt_tokens += first.prompt_tokens
    completion_tokens += first.completion_tokens
    warnings.extend(first.warnings)
    if progress is not None:
        progress.api_done(
            label="first",
            dataset=dataset.metadata.name,
            difficulty=difficulty,
            seed=seed,
            chunk_index=chunk_index,
            budget=budget,
            prompt_tokens=first.prompt_tokens,
            completion_tokens=first.completion_tokens,
        )
    messages.append({"role": "assistant", "content": first.text})
    first_payload = _completion_payload(first)
    repairs: list[BenchmarkRepair] = []

    if first_payload is not None:
        payloads.append(first_payload)
        action = first_payload.get("action")
        if action == "submit_repairs":
            repairs.extend(_repairs_from_payload(first_payload))
        elif action not in {"finish", None}:
            tool_result: dict[str, Any] | None = None
            if action == "inspect_rows":
                requested_rows = first_payload.get("row_indices", [])
                safe_rows = (
                    [
                        row
                        for row in requested_rows
                        if isinstance(row, int) and 0 <= row < len(dataset.dirty_df.index)
                    ]
                    if isinstance(requested_rows, list)
                    else []
                )
                tool_result = {"rows": _chunk_records(dataset, tuple(safe_rows))}
                tool_calls.append(
                    {
                        "name": "inspect_rows",
                        "arguments": {"row_indices": safe_rows},
                        "result": tool_result,
                    }
                )
            elif action == "column_stats":
                requested_columns = first_payload.get("columns", [])
                safe_columns = (
                    [
                        column
                        for column in requested_columns
                        if isinstance(column, str) and column in dataset.canonical_columns
                    ]
                    if isinstance(requested_columns, list)
                    else []
                )
                tool_result = {"column_stats": _column_stats(dataset, safe_columns)}
                tool_calls.append(
                    {
                        "name": "column_stats",
                        "arguments": {"columns": safe_columns},
                        "result": tool_result,
                    }
                )

            if tool_result is not None:
                messages.append(
                    {"role": "user", "content": json.dumps(tool_result, sort_keys=True)}
                )
                if deadline is not None:
                    deadline.raise_if_expired()
                if progress is not None:
                    progress.api_start(
                        label="second",
                        dataset=dataset.metadata.name,
                        difficulty=difficulty,
                        seed=seed,
                        chunk_index=chunk_index,
                        budget=budget,
                    )
                budget.consume()
                second = client.complete(messages)
                llm_calls += 1
                prompt_tokens += second.prompt_tokens
                completion_tokens += second.completion_tokens
                warnings.extend(second.warnings)
                if progress is not None:
                    progress.api_done(
                        label="second",
                        dataset=dataset.metadata.name,
                        difficulty=difficulty,
                        seed=seed,
                        chunk_index=chunk_index,
                        budget=budget,
                        prompt_tokens=second.prompt_tokens,
                        completion_tokens=second.completion_tokens,
                    )
                messages.append({"role": "assistant", "content": second.text})
                second_payload = _completion_payload(second)
                if second_payload is not None:
                    payloads.append(second_payload)
                    if second_payload.get("action") == "submit_repairs":
                        repairs.extend(_repairs_from_payload(second_payload))

    repairs = _repairs_for_rows(repairs, row_indices)
    chunk_score = _score_for_rows(dataset.ground_truth, repairs, row_indices)
    record = {
        "schema_version": SCHEMA_VERSION,
        "trajectory_id": f"{task_id}:{seed}:{chunk_index}",
        "task_id": task_id,
        "dataset": dataset.metadata.name,
        "difficulty": difficulty,
        "seed": seed,
        "chunk_index": chunk_index,
        "state": {
            "schema_summary": schema_summary,
            "target_rows": chunk_payload,
            "context_rows": context_payload,
        },
        "tool_calls": tool_calls,
        "diagnosis": _diagnosis_from_payloads(payloads),
        "fix": [repair.model_dump(mode="json") for repair in repairs],
        "messages": messages,
        "teacher": {"provider": "groq", "model": client.model},
        "metrics": {
            "chunk_precision": chunk_score.precision,
            "chunk_recall": chunk_score.recall,
            "chunk_f1": chunk_score.f1,
            "llm_calls": llm_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "warnings": warnings,
        },
        "provenance": {
            "citation": dataset.metadata.citation,
            "source_urls": list(dataset.metadata.source_urls),
            "collection_method": "llm_react_chunk",
        },
    }
    if progress is not None:
        progress.chunk_done(
            dataset=dataset.metadata.name,
            difficulty=difficulty,
            seed=seed,
            chunk_index=chunk_index,
            repairs=len(repairs),
            llm_calls=llm_calls,
        )
    return ChunkCollection(record=record, repairs=repairs)


def collect_episode_trajectories(
    dataset: RealWorldDataset,
    *,
    difficulty: Difficulty,
    seed: int,
    client: CompletionClient,
    existing_keys: set[TrajectoryKey],
    budget: BudgetGuard,
    min_episode_f1: float,
    deadline: RuntimeDeadline | None = None,
    progress: ProgressReporter | None = None,
) -> list[dict[str, Any]]:
    """Collect chunk-level records for one episode, keeping only passing episodes."""
    task_id = f"{dataset.metadata.name}:{difficulty}"
    chunks = chunk_row_indices(len(dataset.dirty_df.index))
    collections: list[ChunkCollection] = []
    all_repairs: list[BenchmarkRepair] = []

    for chunk_index, row_indices in enumerate(chunks):
        if TrajectoryKey(task_id, seed, chunk_index) in existing_keys:
            continue
        if deadline is not None:
            deadline.raise_if_expired()
        if progress is not None:
            progress.chunk_start(
                dataset=dataset.metadata.name,
                difficulty=difficulty,
                seed=seed,
                chunk_index=chunk_index,
                total_chunks=len(chunks),
                budget=budget,
            )
        collection = _collect_chunk(
            dataset,
            difficulty=difficulty,
            seed=seed,
            chunk_index=chunk_index,
            row_indices=row_indices,
            client=client,
            budget=budget,
            deadline=deadline,
            progress=progress,
        )
        collections.append(collection)
        all_repairs.extend(collection.repairs)

    if not collections:
        return []

    episode_score = score_repairs(dataset.ground_truth, all_repairs)
    if episode_score.f1 < min_episode_f1:
        return []

    records: list[dict[str, Any]] = []
    for collection in collections:
        metrics = dict(collection.record["metrics"])
        metrics.update(
            {
                "episode_precision": episode_score.precision,
                "episode_recall": episode_score.recall,
                "episode_f1": episode_score.f1,
                "episode_tp": episode_score.tp,
                "episode_fp": episode_score.fp,
                "episode_fn": episode_score.fn,
            }
        )
        collection.record["metrics"] = metrics
        records.append(validate_trajectory_record(collection.record))
    return records


def _parse_csv(value: str) -> list[str]:
    """Parse a comma-separated CLI value."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _preset_defaults(preset: Preset) -> PresetDefaults:
    """Return defaults for one named collection preset."""
    return SMOKE_DEFAULTS if preset == "smoke" else FULL_DEFAULTS


def _resolve_collection_settings(args: argparse.Namespace) -> CollectionSettings:
    """Apply preset defaults while allowing explicit CLI flags to override them."""
    preset = cast(Preset, args.preset)
    defaults = _preset_defaults(preset)
    datasets = (
        _parse_csv(cast(str, args.datasets))
        if args.datasets is not None
        else list(defaults.datasets)
    )
    raw_difficulties = (
        _parse_csv(cast(str, args.difficulties))
        if args.difficulties is not None
        else list(defaults.difficulties)
    )
    difficulties = cast(list[Difficulty], raw_difficulties)
    settings = CollectionSettings(
        preset=preset,
        datasets=datasets,
        difficulties=difficulties,
        seeds=defaults.seeds if args.seeds is None else cast(int, args.seeds),
        max_trajectories=defaults.max_trajectories
        if args.max_trajectories is None
        else cast(int, args.max_trajectories),
        min_episode_f1=0.6 if args.min_episode_f1 is None else cast(float, args.min_episode_f1),
        max_total_requests=defaults.max_total_requests
        if args.max_total_requests is None
        else cast(int, args.max_total_requests),
        daily_request_budget=defaults.daily_request_budget
        if args.daily_request_budget is None
        else cast(int, args.daily_request_budget),
        groq_model="llama-3.3-70b-versatile"
        if args.groq_model is None
        else cast(str, args.groq_model),
        groq_max_tokens=512 if args.groq_max_tokens is None else cast(int, args.groq_max_tokens),
        min_interval_s=defaults.min_interval_s
        if args.min_interval_s is None
        else cast(float, args.min_interval_s),
        groq_timeout_s=defaults.groq_timeout_s
        if args.groq_timeout_s is None
        else cast(float, args.groq_timeout_s),
        groq_max_retries=defaults.groq_max_retries
        if args.groq_max_retries is None
        else cast(int, args.groq_max_retries),
        max_runtime_min=defaults.max_runtime_min
        if args.max_runtime_min is None
        else cast(float, args.max_runtime_min),
        progress_every_chunks=defaults.progress_every_chunks
        if args.progress_every_chunks is None
        else cast(int, args.progress_every_chunks),
        ready_min_records=defaults.ready_min_records
        if args.ready_min_records is None
        else cast(int, args.ready_min_records),
    )
    _validate_collection_settings(settings)
    return settings


def _validate_collection_settings(settings: CollectionSettings) -> None:
    """Validate resolved collection settings before any API work starts."""
    if not settings.datasets:
        raise ValueError("At least one dataset must be selected.")
    unknown_difficulties = sorted(set(settings.difficulties) - set(DEFAULT_DIFFICULTIES))
    if unknown_difficulties:
        raise ValueError(f"Unknown difficulties: {unknown_difficulties}")
    if settings.seeds < 1:
        raise ValueError("--seeds must be >= 1.")
    if settings.max_trajectories < 1:
        raise ValueError("--max-trajectories must be >= 1.")
    if settings.max_total_requests < 1:
        raise ValueError("--max-total-requests must be >= 1.")
    if settings.daily_request_budget < 1:
        raise ValueError("--daily-request-budget must be >= 1.")
    if settings.groq_max_tokens < 1:
        raise ValueError("--groq-max-tokens must be >= 1.")
    if settings.groq_timeout_s <= 0:
        raise ValueError("--groq-timeout-s must be > 0.")
    if settings.groq_max_retries < 1:
        raise ValueError("--groq-max-retries must be >= 1.")
    if settings.min_interval_s < 0:
        raise ValueError("--min-interval-s must be >= 0.")
    if settings.max_runtime_min is not None and settings.max_runtime_min <= 0:
        raise ValueError("--max-runtime-min must be > 0 when provided.")
    if settings.progress_every_chunks < 0:
        raise ValueError("--progress-every-chunks must be >= 0.")
    if settings.ready_min_records < 2:
        raise ValueError("--ready-min-records must be >= 2.")


def _resolve_hf_user(*, api: Any, token: str | None) -> str:
    """Resolve the authenticated Hugging Face username."""
    whoami = api.whoami(token=token)
    if not isinstance(whoami, dict) or not isinstance(whoami.get("name"), str):
        raise RuntimeError("Could not resolve Hugging Face username from HF_TOKEN.")
    return str(whoami["name"])


def resolve_dataset_repo_id(repo_id: str, *, api: Any, token: str | None) -> str:
    """Resolve `auto` to the current user's Week 9 trajectory dataset repo."""
    if repo_id != "auto":
        return repo_id
    return f"{_resolve_hf_user(api=api, token=token)}/{DEFAULT_DATASET_REPO_NAME}"


def push_trajectory_dataset(
    *,
    output: Path,
    repo_id: str,
    token: str | None,
    api: Any | None = None,
) -> str:
    """Push the generated JSONL, config, and model-card template to an HF dataset repo."""
    if api is None:
        from huggingface_hub import HfApi

        api = HfApi(token=token)

    resolved_repo = resolve_dataset_repo_id(repo_id, api=api, token=token)
    api.create_repo(repo_id=resolved_repo, repo_type="dataset", exist_ok=True, token=token)
    api.upload_file(
        path_or_fileobj=str(output),
        path_in_repo="expert_v1.jsonl",
        repo_id=resolved_repo,
        repo_type="dataset",
        token=token,
        commit_message="Upload Week 9 expert trajectories",
    )
    for path, path_in_repo in (
        (Path("training/configs/sft_05b.yaml"), "sft_05b.yaml"),
        (Path("training/MODEL_CARD_TEMPLATE.md"), "MODEL_CARD_TEMPLATE.md"),
    ):
        if path.exists():
            api.upload_file(
                path_or_fileobj=str(path),
                path_in_repo=path_in_repo,
                repo_id=resolved_repo,
                repo_type="dataset",
                token=token,
                commit_message=f"Upload {path_in_repo}",
            )
    return resolved_repo


def ensure_ready_for_push(*, output: Path, ready_min_records: int) -> None:
    """Refuse to push partial or invalid trajectory datasets to Hugging Face."""
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from scripts.data.validate_sft_readiness import validate_sft_readiness

    validate_sft_readiness(jsonl=output, min_records=ready_min_records)


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset",
        choices=("smoke", "full"),
        default="smoke",
        help="Collection preset. 'smoke' is laptop-safe; 'full' restores the original large run.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--datasets", default=None)
    parser.add_argument("--difficulties", default=None)
    parser.add_argument("--seeds", type=int, default=None)
    parser.add_argument("--max-trajectories", type=int, default=None)
    parser.add_argument("--min-episode-f1", type=float, default=None)
    parser.add_argument("--max-total-requests", type=int, default=None)
    parser.add_argument("--daily-request-budget", type=int, default=None)
    parser.add_argument("--cache-root", type=Path, default=None)
    parser.add_argument("--push-to-hub", action="store_true")
    parser.add_argument("--hf-dataset-repo", default="auto")
    parser.add_argument("--groq-model", default=None)
    parser.add_argument("--groq-max-tokens", type=int, default=None)
    parser.add_argument("--min-interval-s", type=float, default=None)
    parser.add_argument("--groq-timeout-s", type=float, default=None)
    parser.add_argument("--groq-max-retries", type=int, default=None)
    parser.add_argument("--max-runtime-min", type=float, default=None)
    parser.add_argument(
        "--progress-every-chunks",
        type=int,
        default=None,
        help="Print chunk/API progress every N chunks. Use 0 to disable.",
    )
    parser.add_argument("--ready-min-records", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Week 9 trajectory collection CLI."""
    load_dotenv()
    args = _build_parser().parse_args(argv)
    settings = _resolve_collection_settings(args)
    console = Console()

    if os.environ.get("DATAFORGE_LLM_PROVIDER") != "groq":
        raise RuntimeError("DATAFORGE_LLM_PROVIDER must be set to groq.")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for trajectory collection.")

    existing_keys = existing_trajectory_keys(args.output)
    budget = BudgetGuard(
        max_total_requests=settings.max_total_requests,
        daily_request_budget=settings.daily_request_budget,
    )
    client = GroqBenchClient(
        api_key=api_key,
        model=settings.groq_model,
        min_interval_s=settings.min_interval_s,
        max_tokens=settings.groq_max_tokens,
        max_retries=settings.groq_max_retries,
        timeout_s=settings.groq_timeout_s,
    )
    deadline = RuntimeDeadline(
        started_at=time.monotonic(),
        max_runtime_s=(
            settings.max_runtime_min * 60 if settings.max_runtime_min is not None else None
        ),
    )
    progress = ProgressReporter(
        console=console,
        deadline=deadline,
        every_chunks=settings.progress_every_chunks,
        accepted_records=len(existing_keys),
    )

    existing_count = len(existing_keys)
    target_new = max(settings.max_trajectories - existing_count, 0)
    collected = 0
    stop_collection = target_new == 0
    console.print(
        "[sft] starting collection "
        f"preset={settings.preset} datasets={','.join(settings.datasets)} "
        f"difficulties={','.join(settings.difficulties)} seeds={settings.seeds} "
        f"target={settings.max_trajectories} existing={existing_count} "
        f"request_budget={settings.max_total_requests} timeout_s={settings.groq_timeout_s} "
        f"deadline_min={settings.max_runtime_min}"
    )
    for seed in range(settings.seeds):
        if stop_collection:
            break
        for dataset_name in settings.datasets:
            if stop_collection:
                break
            full_dataset = load_real_world_dataset(dataset_name, cache_root=args.cache_root)
            for difficulty in settings.difficulties:
                if stop_collection:
                    break
                light_dataset = build_light_dataset(full_dataset, difficulty=difficulty, seed=seed)
                try:
                    deadline.raise_if_expired()
                    records = collect_episode_trajectories(
                        light_dataset,
                        difficulty=difficulty,
                        seed=seed,
                        client=client,
                        existing_keys=existing_keys,
                        budget=budget,
                        min_episode_f1=settings.min_episode_f1,
                        deadline=deadline,
                        progress=progress,
                    )
                except RuntimeError as exc:
                    message = str(exc)
                    if "request budget" not in message and "runtime deadline" not in message:
                        raise
                    console.print(f"[sft] stopping cleanly: {exc}")
                    stop_collection = True
                    break
                if not records:
                    console.print(
                        "[sft] episode rejected "
                        f"dataset={dataset_name} difficulty={difficulty} seed={seed} "
                        f"accepted={existing_count + collected} elapsed={deadline.elapsed_s():.1f}s"
                    )
                    continue
                remaining = target_new - collected
                if remaining <= 0:
                    stop_collection = True
                    break
                records_to_write = records[:remaining]
                write_jsonl_records(args.output, records_to_write)
                for record in records_to_write:
                    existing_keys.add(
                        TrajectoryKey(
                            task_id=str(record["task_id"]),
                            seed=int(record["seed"]),
                            chunk_index=int(record["chunk_index"]),
                        )
                    )
                collected += len(records_to_write)
                progress.update_accepted(existing_count + collected)
                console.print(
                    "[sft] episode accepted "
                    f"dataset={dataset_name} difficulty={difficulty} seed={seed} "
                    f"wrote={len(records_to_write)} accepted={existing_count + collected} "
                    f"elapsed={deadline.elapsed_s():.1f}s"
                )
                if len(records_to_write) < len(records) or collected >= target_new:
                    stop_collection = True
                    break

    console.print(
        f"Collected {collected} new trajectories to {args.output} "
        f"({existing_count + collected}/{settings.max_trajectories} total cap) "
        f"using {budget.used_requests}/{budget.max_total_requests} Groq requests "
        f"(daily planning budget: {settings.daily_request_budget})."
    )
    if args.push_to_hub:
        ensure_ready_for_push(output=args.output, ready_min_records=settings.ready_min_records)
        token = os.environ.get("HF_TOKEN")
        repo_id = push_trajectory_dataset(
            output=args.output,
            repo_id=args.hf_dataset_repo,
            token=token,
        )
        console.print(f"Pushed trajectory dataset to {repo_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
