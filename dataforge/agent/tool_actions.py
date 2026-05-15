"""Typed tool-use action models for the DataForge RL environment.

This module defines a discriminated union of 8 action types that an RL agent
can submit to the DataForge environment. Each action is a standalone Pydantic
model with its own validation rules, preventing cross-model field pollution.

The ``parse_action`` function is the single entry point for HTTP handlers
and tests to validate raw action dicts into typed models.

Action Types:
    INSPECT_ROWS  — View a slice of the dataset.
    SQL_QUERY     — Execute read-only SQL against the episode DataFrame.
    STAT_TEST     — Run a statistical test on a column.
    PATTERN_MATCH — Evaluate a regex pattern against column values.
    HYPOTHESIS    — Record a causal-root claim for credit.
    ROOT_CAUSE    — Analyze selected detected errors for minimal roots.
    DIAGNOSE      — Flag a suspected issue at (row, column).
    FIX           — Propose a corrected value for a diagnosed issue.

Example::

    >>> from dataforge.agent.tool_actions import parse_action
    >>> action = parse_action({"action_type": "INSPECT_ROWS", "row_indices": [0, 1]})
    >>> action.action_type
    'INSPECT_ROWS'
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "Action",
    "Diagnose",
    "Fix",
    "Hypothesis",
    "InspectRows",
    "PatternMatch",
    "RootCause",
    "SqlQuery",
    "StatTest",
    "parse_action",
]


class InspectRows(BaseModel):
    """View a slice of dataset rows.

    Args:
        action_type: Must be ``"INSPECT_ROWS"``.
        row_indices: Zero-indexed row indices to retrieve. At least 1 required.
        column_names: Optional column filter. If omitted, all columns returned.

    Example::

        >>> InspectRows(action_type="INSPECT_ROWS", row_indices=[0, 1, 2])
    """

    action_type: Literal["INSPECT_ROWS"]
    row_indices: list[int] = Field(min_length=1, description="Row indices to inspect (0-indexed).")
    column_names: list[str] | None = Field(default=None, description="Optional column filter.")

    @field_validator("row_indices")
    @classmethod
    def _validate_row_indices(cls, v: list[int]) -> list[int]:
        """Validate that all row indices are non-negative."""
        if any(i < 0 for i in v):
            raise ValueError("All row indices must be >= 0")
        return v

    model_config = {"frozen": True}


class SqlQuery(BaseModel):
    """Execute read-only SQL against the episode DataFrame via DuckDB.

    Args:
        action_type: Must be ``"SQL_QUERY"``.
        query: SQL query string. Must be read-only (SELECT only).

    Example::

        >>> SqlQuery(action_type="SQL_QUERY", query="SELECT * FROM data LIMIT 5")
    """

    action_type: Literal["SQL_QUERY"]
    query: str = Field(min_length=1, description="Read-only SQL query.")

    model_config = {"frozen": True}


class StatTest(BaseModel):
    """Run a statistical test on a dataset column.

    Args:
        action_type: Must be ``"STAT_TEST"``.
        test_type: One of ``"zscore"``, ``"iqr"``, ``"ks"``.
        column: Column name to test.
        threshold: Optional threshold override. Defaults vary by test type.

    Example::

        >>> StatTest(action_type="STAT_TEST", test_type="zscore", column="rating")
    """

    action_type: Literal["STAT_TEST"]
    test_type: Literal["zscore", "iqr", "ks"] = Field(description="Statistical test to run.")
    column: str = Field(min_length=1, description="Column name to test.")
    threshold: float | None = Field(default=None, description="Optional threshold override.")

    model_config = {"frozen": True}


class PatternMatch(BaseModel):
    """Evaluate a regex pattern against column values.

    Args:
        action_type: Must be ``"PATTERN_MATCH"``.
        pattern: Regular expression string.
        column: Column name to evaluate.
        expect_match: If True, report rows that match. If False, report non-matches.

    Example::

        >>> PatternMatch(
        ...     action_type="PATTERN_MATCH",
        ...     pattern=r"^\\d{5}$",
        ...     column="zip_code",
        ... )
    """

    action_type: Literal["PATTERN_MATCH"]
    pattern: str = Field(min_length=1, description="Regex pattern.")
    column: str = Field(min_length=1, description="Column name to evaluate.")
    expect_match: bool = Field(
        default=True,
        description="True to report matches, False to report non-matches.",
    )

    model_config = {"frozen": True}


class Hypothesis(BaseModel):
    """Record a causal-root claim for root-cause credit.

    Args:
        action_type: Must be ``"HYPOTHESIS"``.
        claim: Textual description of the hypothesized root cause.
        affected_rows: Row indices believed to be affected.
        affected_columns: Column names believed to be affected.
        root_cause_type: Detector-vocabulary root cause type
            (e.g., ``"decimal_shift"``, ``"type_mismatch"``).

    Example::

        >>> Hypothesis(
        ...     action_type="HYPOTHESIS",
        ...     claim="Column 'rating' has a decimal shift at row 5",
        ...     affected_rows=[5],
        ...     affected_columns=["rating"],
        ...     root_cause_type="decimal_shift",
        ... )
    """

    action_type: Literal["HYPOTHESIS"]
    claim: str = Field(min_length=1, description="Root-cause claim.")
    affected_rows: list[int] = Field(min_length=1, description="Affected row indices.")
    affected_columns: list[str] = Field(min_length=1, description="Affected column names.")
    root_cause_type: str = Field(min_length=1, description="Detector-vocabulary root cause type.")

    @field_validator("affected_rows")
    @classmethod
    def _validate_affected_rows(cls, v: list[int]) -> list[int]:
        """Validate that all affected row indices are non-negative."""
        if any(i < 0 for i in v):
            raise ValueError("All affected row indices must be >= 0")
        return v

    model_config = {"frozen": True}


class RootCause(BaseModel):
    """Analyze selected detected errors for minimal causal roots.

    Args:
        action_type: Must be ``"ROOT_CAUSE"``.
        error_indices: Zero-based indices into the episode's detected issue list.

    Example::

        >>> RootCause(action_type="ROOT_CAUSE", error_indices=[0, 1])
    """

    action_type: Literal["ROOT_CAUSE"]
    error_indices: list[int] = Field(min_length=1, description="Detected issue indices.")

    @field_validator("error_indices")
    @classmethod
    def _validate_error_indices(cls, v: list[int]) -> list[int]:
        """Validate that all error indices are non-negative."""
        if any(i < 0 for i in v):
            raise ValueError("All error indices must be >= 0")
        return v

    model_config = {"frozen": True}


class Diagnose(BaseModel):
    """Flag a suspected data-quality issue at a specific (row, column).

    Args:
        action_type: Must be ``"DIAGNOSE"``.
        row: Zero-indexed row number.
        column: Column name.
        issue_type: Issue type from detector vocabulary.

    Example::

        >>> Diagnose(
        ...     action_type="DIAGNOSE",
        ...     row=5, column="rating",
        ...     issue_type="decimal_shift",
        ... )
    """

    action_type: Literal["DIAGNOSE"]
    row: int = Field(ge=0, description="Zero-indexed row number.")
    column: str = Field(min_length=1, description="Column name.")
    issue_type: str = Field(min_length=1, description="Issue type classification.")

    model_config = {"frozen": True}


class Fix(BaseModel):
    """Propose a corrected value for a diagnosed issue.

    Args:
        action_type: Must be ``"FIX"``.
        row: Zero-indexed row number.
        column: Column name.
        new_value: The corrected cell value as a string.
        justification: Explanation of why this fix is correct.
        fix_type: How to fix the issue. Defaults to ``"correct_value"``.

    Example::

        >>> Fix(
        ...     action_type="FIX",
        ...     row=5, column="rating",
        ...     new_value="4.5",
        ...     justification="Decimal shift: 45.0 should be 4.5",
        ... )
    """

    action_type: Literal["FIX"]
    row: int = Field(ge=0, description="Zero-indexed row number.")
    column: str = Field(min_length=1, description="Column name.")
    new_value: str = Field(description="Corrected cell value.")
    justification: str = Field(min_length=1, description="Fix justification.")
    fix_type: Literal["correct_value", "delete_row", "impute", "standardize"] = Field(
        default="correct_value", description="Fix operation type."
    )

    model_config = {"frozen": True}


# ═══════════════════════════════════════════════════════════════════════════
# Discriminated union and parser
# ═══════════════════════════════════════════════════════════════════════════

Action = Annotated[
    InspectRows | SqlQuery | StatTest | PatternMatch | Hypothesis | RootCause | Diagnose | Fix,
    Field(discriminator="action_type"),
]
"""Discriminated union of all valid DataForge environment actions."""


def parse_action(raw: dict[str, Any]) -> Action:
    """Parse and validate a raw action dict into the appropriate typed model.

    This is the single entry point for HTTP handlers and tests to validate
    actions. The ``action_type`` field is used as the discriminator.

    Args:
        raw: Dictionary with an ``action_type`` key and action-specific fields.

    Returns:
        A validated action model instance.

    Raises:
        pydantic.ValidationError: If the action is malformed or invalid.
        KeyError: If ``action_type`` is missing.
        ValueError: If ``action_type`` is not recognized.

    Example::

        >>> action = parse_action({"action_type": "INSPECT_ROWS", "row_indices": [0]})
        >>> isinstance(action, InspectRows)
        True
    """
    from pydantic import TypeAdapter

    adapter: TypeAdapter[Action] = TypeAdapter(Action)
    return adapter.validate_python(_normalize_action(raw))


def _normalize_action(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical action dictionary from supported external aliases."""
    normalized = dict(raw)
    action_type = normalized.get("action_type")
    if action_type == "SQL_QUERY" and "sql" in normalized and "query" not in normalized:
        normalized["query"] = normalized["sql"]
    if action_type == "STAT_TEST" and "test" in normalized and "test_type" not in normalized:
        normalized["test_type"] = normalized["test"]
    if action_type == "PATTERN_MATCH":
        if "regex" in normalized and "pattern" not in normalized:
            normalized["pattern"] = normalized["regex"]
        if "expect" in normalized and "expect_match" not in normalized:
            normalized["expect_match"] = normalized["expect"] == "match"
    if action_type == "HYPOTHESIS":
        root_column = normalized.get("root_column")
        downstream = normalized.get("downstream")
        if root_column is not None and "affected_columns" not in normalized:
            downstream_columns = downstream if isinstance(downstream, list) else []
            normalized["affected_columns"] = [root_column, *downstream_columns]
        if "affected_rows" not in normalized:
            normalized["affected_rows"] = [0]
        if root_column is not None and "root_cause_type" not in normalized:
            normalized["root_cause_type"] = root_column
    if (
        action_type == "ROOT_CAUSE"
        and "indices" in normalized
        and "error_indices" not in normalized
    ):
        normalized["error_indices"] = normalized["indices"]
    if action_type == "FIX":
        if "proposed_value" in normalized and "new_value" not in normalized:
            normalized["new_value"] = normalized["proposed_value"]
        if "justification" not in normalized:
            normalized["justification"] = "Agent proposed value via FIX."
    return normalized
