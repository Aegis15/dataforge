"""Reviewable schema and constraint inference for DataForge profiles."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dataforge.table import TableLike, column_names, column_values, row_count
from dataforge.verifier.schema import DomainBound, FunctionalDependency, Schema

ConstraintKind = Literal[
    "column_type",
    "domain_bound",
    "regex",
    "unique",
    "functional_dependency",
]

_INT_RE = re.compile(r"^[+-]?\d+$")
_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGITS_RE = re.compile(r"^\d+$")
_UPPER_CODE_RE = re.compile(r"^[A-Z0-9_-]+$")


class ConstraintCandidate(BaseModel):
    """One inferred constraint candidate that must be reviewed before adoption."""

    kind: ConstraintKind
    columns: tuple[str, ...] = Field(min_length=1)
    dependent: str | None = None
    inferred_type: str | None = None
    pattern: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1)
    provenance: str = "profile_inference_v1"

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SchemaInferenceResult(BaseModel):
    """Reviewable schema inference result emitted by profile and benchmarks."""

    columns: dict[str, str] = Field(default_factory=dict)
    candidates: list[ConstraintCandidate] = Field(default_factory=list)
    row_count: int = Field(ge=0)

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    def to_schema(self, *, include_inferred_constraints: bool = False) -> Schema:
        """Convert reviewed inference output into a verifier Schema."""
        if not include_inferred_constraints:
            return Schema(columns=dict(self.columns))

        fds: list[FunctionalDependency] = []
        bounds: list[DomainBound] = []
        for candidate in self.candidates:
            if (
                candidate.kind == "functional_dependency"
                and candidate.dependent is not None
                and candidate.confidence >= 0.9
            ):
                fds.append(
                    FunctionalDependency(
                        determinant=candidate.columns,
                        dependent=candidate.dependent,
                    )
                )
            elif candidate.kind == "domain_bound" and candidate.confidence >= 0.95:
                bounds.append(
                    DomainBound(
                        column=candidate.columns[0],
                        min_value=candidate.min_value,
                        max_value=candidate.max_value,
                    )
                )
        return Schema(
            columns=dict(self.columns),
            functional_dependencies=tuple(fds),
            domain_bounds=tuple(bounds),
        )


def _non_empty(values: list[object]) -> list[str]:
    """Return non-empty string values."""
    return [str(value).strip() for value in values if str(value).strip()]


def _try_float(value: str) -> float | None:
    """Parse a finite float or return None."""
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _infer_column_type(values: list[str]) -> tuple[str, float, str]:
    """Infer a conservative verifier-compatible column type."""
    if not values:
        return "str", 0.0, "No non-empty values were available."

    int_count = sum(1 for value in values if _INT_RE.fullmatch(value))
    float_count = sum(1 for value in values if _FLOAT_RE.fullmatch(value))
    date_count = sum(1 for value in values if _ISO_DATE_RE.fullmatch(value))
    total = len(values)

    if int_count / total >= 0.95:
        return "int", round(int_count / total, 4), f"{int_count}/{total} values parse as integers."
    if float_count / total >= 0.9:
        return (
            "float",
            round(float_count / total, 4),
            f"{float_count}/{total} values parse as floats.",
        )
    if date_count / total >= 0.9:
        return (
            "str",
            round(date_count / total, 4),
            f"{date_count}/{total} values look like ISO dates.",
        )
    return "str", 1.0, "Column is treated as string unless reviewed otherwise."


def _regex_candidate(column: str, values: list[str]) -> ConstraintCandidate | None:
    """Infer a simple regex candidate for consistent identifier-like columns."""
    if not values:
        return None
    if all(_DIGITS_RE.fullmatch(value) for value in values):
        lengths = sorted({len(value) for value in values})
        pattern = rf"^\d{{{lengths[0]}}}$" if len(lengths) == 1 else r"^\d+$"
    elif all(_UPPER_CODE_RE.fullmatch(value) for value in values):
        pattern = r"^[A-Z0-9_-]+$"
    else:
        return None
    return ConstraintCandidate(
        kind="regex",
        columns=(column,),
        pattern=pattern,
        confidence=1.0,
        evidence=f"{len(values)} non-empty values matched {pattern}.",
    )


def _domain_candidate(column: str, values: list[str]) -> ConstraintCandidate | None:
    """Infer a numeric min/max domain candidate."""
    numeric = [_try_float(value) for value in values]
    parsed = [value for value in numeric if value is not None]
    if len(parsed) < 3 or len(parsed) != len(values):
        return None
    return ConstraintCandidate(
        kind="domain_bound",
        columns=(column,),
        min_value=min(parsed),
        max_value=max(parsed),
        confidence=1.0,
        evidence=f"{len(parsed)} values define the observed numeric range.",
    )


def _unique_candidate(column: str, values: list[str]) -> ConstraintCandidate | None:
    """Infer a uniqueness candidate when every non-empty value is distinct."""
    if len(values) < 3 or len(set(values)) != len(values):
        return None
    return ConstraintCandidate(
        kind="unique",
        columns=(column,),
        confidence=1.0,
        evidence=f"{len(values)} non-empty values are distinct.",
    )


def _fd_candidates(table: TableLike, columns: list[str]) -> list[ConstraintCandidate]:
    """Infer single-column functional dependencies with violation tolerance."""
    total_rows = row_count(table)
    if total_rows < 5:
        return []

    values_by_column = {column: _non_empty(column_values(table, column)) for column in columns}
    candidates: list[ConstraintCandidate] = []
    for determinant in columns:
        determinant_values = values_by_column[determinant]
        if len(determinant_values) != total_rows:
            continue
        determinant_unique = len(set(determinant_values))
        if determinant_unique < 2 or determinant_unique == total_rows:
            continue

        for dependent in columns:
            if dependent == determinant:
                continue
            dependent_values = values_by_column[dependent]
            if len(dependent_values) != total_rows:
                continue
            groups: dict[str, list[str]] = defaultdict(list)
            for det_value, dep_value in zip(determinant_values, dependent_values, strict=True):
                groups[det_value].append(dep_value)

            violations = 0
            for group_values in groups.values():
                most_common = Counter(group_values).most_common(1)[0][1]
                violations += len(group_values) - most_common
            confidence = round(1.0 - (violations / total_rows), 4)
            if confidence < 0.9:
                continue
            candidates.append(
                ConstraintCandidate(
                    kind="functional_dependency",
                    columns=(determinant,),
                    dependent=dependent,
                    confidence=confidence,
                    evidence=(
                        f"{determinant} determined {dependent} in "
                        f"{total_rows - violations}/{total_rows} rows."
                    ),
                )
            )
    return candidates


def infer_schema(table: TableLike) -> SchemaInferenceResult:
    """Infer reviewable schema candidates from a table-like object."""
    columns = column_names(table)
    inferred_columns: dict[str, str] = {}
    candidates: list[ConstraintCandidate] = []

    for column in columns:
        values = _non_empty(column_values(table, column))
        inferred_type, confidence, evidence = _infer_column_type(values)
        inferred_columns[column] = inferred_type
        candidates.append(
            ConstraintCandidate(
                kind="column_type",
                columns=(column,),
                inferred_type=inferred_type,
                confidence=confidence,
                evidence=evidence,
            )
        )
        regex_candidate = _regex_candidate(column, values)
        if regex_candidate is not None:
            candidates.append(regex_candidate)
        domain_candidate = _domain_candidate(column, values)
        if domain_candidate is not None:
            candidates.append(domain_candidate)
        unique_candidate = _unique_candidate(column, values)
        if unique_candidate is not None:
            candidates.append(unique_candidate)

    candidates.extend(_fd_candidates(table, columns))
    return SchemaInferenceResult(
        columns=inferred_columns,
        candidates=candidates,
        row_count=row_count(table),
    )
