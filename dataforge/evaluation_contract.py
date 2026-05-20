"""Public evaluation evidence models for DataForge repair releases."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

InferabilityLabel = Literal[
    "deterministic_normalization",
    "context_derivable",
    "external_reference_required",
    "not_inferable_from_prompt",
]
PROMOTION_SLICE: InferabilityLabel = "deterministic_normalization"
ABSTENTION_SLICES = frozenset({"external_reference_required", "not_inferable_from_prompt"})
AUXILIARY_SLICES = frozenset({"context_derivable"})
PromotionStatus = Literal[
    "diagnostic_only",
    "diagnostic_promoted",
    "quality_improved_verified",
    "public_quality_milestone",
    "rejected",
]


class EvaluationTaskV2(BaseModel):
    """One auditable, source-stable model grading task.

    Ground truth is retained for local grading but excluded from normal JSON
    serialization so prompts and public reports cannot accidentally leak labels.
    """

    schema_version: Literal["evaluation_task_v2"] = "evaluation_task_v2"
    task_id: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=64, max_length=64)
    dataset_sha: str = Field(min_length=1)
    split_id: str = Field(min_length=1)
    inferability: InferabilityLabel
    prompt: dict[str, Any]
    allowed_columns: list[str] = Field(min_length=1)
    valid_rows: list[int] = Field(min_length=1)
    provenance: dict[str, Any]
    hidden_ground_truth: list[dict[str, Any]] = Field(default_factory=list, exclude=True)

    model_config = {"frozen": True}


class ReleaseEvidenceV2(BaseModel):
    """Serializable release-gate evidence for model and benchmark promotion."""

    schema_version: Literal["release_evidence_v2"] = "release_evidence_v2"
    model_repo: str = Field(min_length=1)
    model_sha: str = Field(min_length=1)
    dataset_repo: str = Field(min_length=1)
    dataset_sha: str = Field(min_length=1)
    strict_macro_f1: float = Field(ge=0.0, le=1.0)
    canonicalized_macro_f1: float = Field(ge=0.0, le=1.0)
    parse_success_rate: float = Field(ge=0.0, le=1.0)
    schema_case_error_count: int = Field(ge=0)
    promotion_slice: InferabilityLabel = PROMOTION_SLICE
    slice_scores: dict[InferabilityLabel, dict[str, float | int]] = Field(default_factory=dict)
    inferability_slice_scores: dict[InferabilityLabel, float] = Field(default_factory=dict)
    package_versions: dict[str, str] = Field(default_factory=dict)
    promotion_status: PromotionStatus
    gate_failures: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


def prompt_sha256(prompt: dict[str, Any]) -> str:
    """Hash a prompt payload with stable JSON serialization."""
    encoded = json.dumps(prompt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
