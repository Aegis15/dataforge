"""Unit tests for SQL_QUERY action handling in the DataForge environment."""

from __future__ import annotations

import pandas as pd
import pytest

# These tests will import from the environment module once it exists.
# For now they validate the DuckDB query execution logic directly.


def _execute_query(df: pd.DataFrame, query: str, max_rows: int = 20) -> dict:
    """Execute a read-only SQL query against a DataFrame via DuckDB.

    This is the standalone helper tested here; the environment wraps it.
    """
    import duckdb
    import sqlglot

    # Validate read-only
    try:
        parsed = sqlglot.parse(query)
    except sqlglot.errors.ParseError as exc:
        return {"success": False, "error": {"verdict": "error", "reason": str(exc)}}

    for stmt in parsed:
        if stmt is not None and stmt.key not in ("select",):
            return {
                "success": False,
                "error": {
                    "verdict": "rejected",
                    "reason": f"Only SELECT queries allowed, got {stmt.key.upper()}",
                },
            }

    try:
        conn = duckdb.connect(":memory:")
        conn.register("data", df)
        result = conn.execute(query).fetchdf()
        rows = result.head(max_rows).to_dict(orient="records")
        conn.close()
        return {"success": True, "data": rows, "row_count": len(rows)}
    except duckdb.Error as exc:
        return {
            "success": False,
            "error": {"verdict": "error", "reason": str(exc)},
        }


@pytest.fixture()
def sample_df() -> pd.DataFrame:
    """Small test DataFrame."""
    return pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "age": [25, 30, 35, 40, 45],
        "score": [88.5, 92.1, 75.0, 95.3, 81.7],
    })


class TestSqlQueryExecution:
    """Tests for DuckDB query execution."""

    def test_valid_select(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELECT * FROM data LIMIT 3")
        assert result["success"] is True
        assert len(result["data"]) == 3

    def test_select_with_where(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELECT name FROM data WHERE age > 30")
        assert result["success"] is True
        assert len(result["data"]) == 3

    def test_max_rows_cap(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELECT * FROM data", max_rows=2)
        assert result["success"] is True
        assert len(result["data"]) <= 2

    def test_syntax_error(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELEC * FORM data")
        assert result["success"] is False
        assert result["error"]["verdict"] in ("error", "rejected")

    def test_drop_rejected(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "DROP TABLE data")
        assert result["success"] is False
        assert "rejected" in result["error"]["verdict"]

    def test_insert_rejected(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "INSERT INTO data VALUES ('F', 50, 99.0)")
        assert result["success"] is False

    def test_invalid_column(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELECT nonexistent FROM data")
        assert result["success"] is False
        assert result["error"]["verdict"] == "error"

    def test_aggregate_query(self, sample_df: pd.DataFrame) -> None:
        result = _execute_query(sample_df, "SELECT AVG(age) as avg_age FROM data")
        assert result["success"] is True
        assert len(result["data"]) == 1
