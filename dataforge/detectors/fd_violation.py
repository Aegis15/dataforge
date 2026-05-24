"""Detector for functional-dependency violations in tabular data.

Given a declared functional dependency X -> Y (where X is a set of
determinant columns and Y is a dependent column), this detector groups
rows by X and flags any group where Y takes more than one distinct value.

Week 1 scope: declared FDs only (from the schema YAML).  Automatic FD
mining is deferred to a later milestone.

The detector is **pure**: no LLM calls, no I/O, no side effects.
"""

from __future__ import annotations

from dataforge.detectors.base import Issue, Schema, Severity
from dataforge.table import TableLike, cell_value, column_names, row_count


class FDViolationDetector:
    """Detects rows that violate declared functional dependencies.

    For each FD ``determinant -> dependent`` in the schema, groups the
    DataFrame by the determinant columns and checks that each group has
    exactly one unique value in the dependent column.  All rows in a
    violating group are flagged.

    Requires a ``Schema`` with ``functional_dependencies`` to do anything;
    returns an empty list if no schema or no FDs are provided.

    Example:
        >>> import pandas as pd
        >>> from dataforge.detectors.base import FunctionalDependency, Schema
        >>> detector = FDViolationDetector()
        >>> df = pd.DataFrame({
        ...     "zip": ["10001", "10001", "90210"],
        ...     "city": ["NY", "Manhattan", "LA"],
        ... })
        >>> schema = Schema(functional_dependencies=[
        ...     FunctionalDependency(determinant=["zip"], dependent="city"),
        ... ])
        >>> issues = detector.detect(df, schema)
        >>> len(issues)
        2
    """

    def detect(self, df: TableLike, schema: Schema | None = None) -> list[Issue]:
        """Detect FD-violation issues in the DataFrame.

        Args:
            df: The input DataFrame to analyze.
            schema: Schema containing declared functional dependencies.
                If None or no FDs declared, returns an empty list.

        Returns:
            A list of Issue objects for rows violating declared FDs.
        """
        if schema is None or not schema.functional_dependencies:
            return []

        issues: list[Issue] = []

        for fd in schema.functional_dependencies:
            fd_issues = self._check_fd(df, fd.determinant, fd.dependent)
            issues.extend(fd_issues)

        return issues

    def _check_fd(
        self,
        df: TableLike,
        determinant: tuple[str, ...],
        dependent: str,
    ) -> list[Issue]:
        """Check a single functional dependency X -> Y.

        Args:
            df: The DataFrame to check.
            determinant: List of determinant column names (X).
            dependent: The dependent column name (Y).

        Returns:
            Issues for all rows in groups that violate the FD.
        """
        determinant_columns = list(determinant)

        # Verify all columns exist in the DataFrame.
        all_cols = [*determinant_columns, dependent]
        available_columns = set(column_names(df))
        for col in all_cols:
            if col not in available_columns:
                return []

        groups: dict[tuple[str, ...], list[int]] = {}
        for row in range(row_count(df)):
            group_key = tuple(cell_value(df, row, column) for column in determinant_columns)
            if any(value == "" for value in group_key):
                continue
            groups.setdefault(group_key, []).append(row)

        if not groups:
            return []

        issues: list[Issue] = []
        for group_key, row_indices in groups.items():
            unique_deps: list[str] = []
            for row in row_indices:
                value = cell_value(df, row, dependent)
                if value == "" or value in unique_deps:
                    continue
                unique_deps.append(value)
            if len(unique_deps) <= 1:
                continue

            det_desc = self._format_determinant(determinant, group_key)
            unique_str = ", ".join(repr(str(v)) for v in unique_deps)

            for idx in row_indices:
                actual_val = cell_value(df, idx, dependent)
                reason = (
                    f"Functional dependency {determinant} -> {dependent} "
                    f"violated: {det_desc} maps to multiple values: "
                    f"{{{unique_str}}}"
                )
                issues.append(
                    Issue(
                        row=int(idx),
                        column=dependent,
                        issue_type="fd_violation",
                        severity=Severity.UNSAFE,
                        confidence=0.95,
                        actual=actual_val,
                        reason=reason,
                    )
                )

        return issues

    @staticmethod
    def _format_determinant(determinant: tuple[str, ...], group_key: object) -> str:
        """Format the determinant key for human-readable output.

        Args:
            determinant: List of determinant column names.
            group_key: The group key (scalar or tuple).

        Returns:
            A formatted string like ``zip_code='10001'``.
        """
        if len(determinant) == 1:
            return f"{determinant[0]}='{group_key}'"

        # Composite key: group_key is a tuple.
        if isinstance(group_key, tuple):
            parts = [f"{col}='{val}'" for col, val in zip(determinant, group_key, strict=True)]
            return ", ".join(parts)

        return f"{determinant}='{group_key}'"
