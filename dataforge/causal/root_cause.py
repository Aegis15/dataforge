"""Minimal root-cause selection over detected errors and a causal DAG."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from dataforge.causal.dag import CausalDAG

__all__ = [
    "CausalRootCauseAnalyzer",
    "ErrorEvidence",
    "RootCauseResult",
    "evidence_from_issue",
    "minimal_root_set",
]


class _IssueLike(Protocol):
    """Protocol for objects with row/column issue fields."""

    row: int
    column: str
    issue_type: str


class ErrorEvidence(BaseModel):
    """Column-mapped detected error used for causal root-cause analysis.

    Args:
        index: Zero-based error index in the caller's selected issue list.
        row: Row index where the error was detected.
        column: Column where the error was detected.
        issue_type: Machine-readable issue type.
    """

    index: int = Field(ge=0)
    row: int = Field(ge=0)
    column: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)

    model_config = {"frozen": True}


class RootCauseResult(BaseModel):
    """Structured result returned by the root-cause analyzer.

    Args:
        root_indices: Minimal selected error indices.
        root_columns: Root columns corresponding to root_indices.
        covered_indices: Selected error indices covered by the root set.
        confidence: Mean path confidence from roots to covered errors.
        explanation: Human-readable explanation of the selected roots.
    """

    root_indices: list[int]
    root_columns: list[str]
    covered_indices: list[int]
    confidence: float
    explanation: str

    model_config = {"frozen": True}


class CausalRootCauseAnalyzer:
    """Compute minimal root causes for selected detected errors.

    Args:
        dag: Column-level causal DAG.

    Example:
        >>> dag = CausalDAG(["discount_pct", "order_total"])
        >>> dag.add_edge("discount_pct", "order_total", confidence=0.9, provenance="formula")
        >>> errors = [
        ...     ErrorEvidence(index=0, row=1, column="discount_pct", issue_type="bad"),
        ...     ErrorEvidence(index=1, row=1, column="order_total", issue_type="bad"),
        ... ]
        >>> CausalRootCauseAnalyzer(dag).analyze(errors).root_indices
        [0]
    """

    def __init__(self, dag: CausalDAG) -> None:
        self._dag = dag

    def analyze(self, errors: list[ErrorEvidence] | tuple[ErrorEvidence, ...]) -> RootCauseResult:
        """Return the minimal root set for the selected errors.

        Args:
            errors: Selected detected errors.

        Returns:
            RootCauseResult with roots, coverage, confidence, and explanation.
        """
        if not errors:
            return RootCauseResult(
                root_indices=[],
                root_columns=[],
                covered_indices=[],
                confidence=0.0,
                explanation="No errors were supplied.",
            )

        roots: list[ErrorEvidence] = []
        for candidate in errors:
            if not self._has_upstream_selected_error(candidate, errors):
                roots.append(candidate)

        covered: list[int] = []
        path_confidences: list[float] = []
        for error in errors:
            for root in roots:
                if root.column == error.column or self._dag.is_reachable(root.column, error.column):
                    covered.append(error.index)
                    path_confidences.append(self._dag.path_confidence(root.column, error.column))
                    break

        confidence = (
            round(sum(path_confidences) / len(path_confidences), 4) if path_confidences else 0.0
        )
        root_columns = [root.column for root in roots]
        return RootCauseResult(
            root_indices=[root.index for root in roots],
            root_columns=root_columns,
            covered_indices=covered,
            confidence=confidence,
            explanation=self._explain(root_columns, len(covered), len(errors)),
        )

    def _has_upstream_selected_error(
        self,
        candidate: ErrorEvidence,
        errors: list[ErrorEvidence] | tuple[ErrorEvidence, ...],
    ) -> bool:
        """Return whether another selected error causally precedes candidate."""
        for other in errors:
            if other.index == candidate.index:
                continue
            if other.column == candidate.column and other.index < candidate.index:
                return True
            if other.column != candidate.column and self._dag.is_reachable(
                other.column, candidate.column
            ):
                return True
        return False

    @staticmethod
    def _explain(root_columns: list[str], covered_count: int, total_count: int) -> str:
        """Build a compact result explanation."""
        if not root_columns:
            return "No minimal roots were found."
        joined = ", ".join(root_columns)
        return f"Selected {joined} as minimal roots covering {covered_count}/{total_count} errors."


def minimal_root_set(
    errors: list[ErrorEvidence] | tuple[ErrorEvidence, ...], dag: CausalDAG
) -> RootCauseResult:
    """Convenience wrapper for CausalRootCauseAnalyzer.

    Args:
        errors: Selected detected errors.
        dag: Column-level causal DAG.

    Returns:
        Minimal root-cause result.
    """
    return CausalRootCauseAnalyzer(dag).analyze(errors)


def evidence_from_issue(index: int, issue: _IssueLike | dict[str, Any]) -> ErrorEvidence:
    """Build ErrorEvidence from an Issue-like object or dictionary.

    Args:
        index: Error index to assign.
        issue: Object or dictionary with row/column/type fields.

    Returns:
        ErrorEvidence instance.
    """
    if isinstance(issue, dict):
        return ErrorEvidence(
            index=index,
            row=int(issue.get("row", 0)),
            column=str(issue.get("column", "")),
            issue_type=str(issue.get("type", issue.get("issue_type", "unknown"))),
        )
    return ErrorEvidence(
        index=index,
        row=int(issue.row),
        column=str(issue.column),
        issue_type=str(issue.issue_type),
    )
