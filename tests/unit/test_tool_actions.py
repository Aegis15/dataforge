"""Unit tests for dataforge.agent.tool_actions — action validation and parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dataforge.agent.tool_actions import (
    Diagnose,
    Fix,
    Hypothesis,
    InspectRows,
    PatternMatch,
    SqlQuery,
    StatTest,
    parse_action,
)


class TestInspectRows:
    """Tests for the INSPECT_ROWS action model."""

    def test_valid_inspect(self) -> None:
        action = InspectRows(action_type="INSPECT_ROWS", row_indices=[0, 1, 2])
        assert action.action_type == "INSPECT_ROWS"
        assert action.row_indices == [0, 1, 2]
        assert action.column_names is None

    def test_with_column_filter(self) -> None:
        action = InspectRows(
            action_type="INSPECT_ROWS", row_indices=[0], column_names=["age", "name"]
        )
        assert action.column_names == ["age", "name"]

    def test_rejects_empty_row_indices(self) -> None:
        with pytest.raises(ValidationError):
            InspectRows(action_type="INSPECT_ROWS", row_indices=[])

    def test_rejects_negative_row_index(self) -> None:
        with pytest.raises(ValidationError):
            InspectRows(action_type="INSPECT_ROWS", row_indices=[-1])


class TestSqlQuery:
    """Tests for the SQL_QUERY action model."""

    def test_valid_query(self) -> None:
        action = SqlQuery(action_type="SQL_QUERY", query="SELECT * FROM data LIMIT 5")
        assert action.query == "SELECT * FROM data LIMIT 5"

    def test_rejects_empty_query(self) -> None:
        with pytest.raises(ValidationError):
            SqlQuery(action_type="SQL_QUERY", query="")


class TestStatTest:
    """Tests for the STAT_TEST action model."""

    def test_valid_zscore(self) -> None:
        action = StatTest(action_type="STAT_TEST", test_type="zscore", column="rating")
        assert action.test_type == "zscore"

    def test_valid_iqr(self) -> None:
        action = StatTest(action_type="STAT_TEST", test_type="iqr", column="price")
        assert action.test_type == "iqr"

    def test_valid_ks(self) -> None:
        action = StatTest(action_type="STAT_TEST", test_type="ks", column="score")
        assert action.test_type == "ks"

    def test_rejects_invalid_test_type(self) -> None:
        with pytest.raises(ValidationError):
            StatTest(action_type="STAT_TEST", test_type="invalid", column="x")  # type: ignore[arg-type]

    def test_rejects_empty_column(self) -> None:
        with pytest.raises(ValidationError):
            StatTest(action_type="STAT_TEST", test_type="zscore", column="")


class TestPatternMatch:
    """Tests for the PATTERN_MATCH action model."""

    def test_valid_pattern(self) -> None:
        action = PatternMatch(
            action_type="PATTERN_MATCH", pattern=r"^\d{5}$", column="zip"
        )
        assert action.expect_match is True

    def test_expect_no_match(self) -> None:
        action = PatternMatch(
            action_type="PATTERN_MATCH", pattern=r"\d+", column="name", expect_match=False
        )
        assert action.expect_match is False


class TestHypothesis:
    """Tests for the HYPOTHESIS action model."""

    def test_valid_hypothesis(self) -> None:
        action = Hypothesis(
            action_type="HYPOTHESIS",
            claim="Decimal shift in rating",
            affected_rows=[5],
            affected_columns=["rating"],
            root_cause_type="decimal_shift",
        )
        assert action.root_cause_type == "decimal_shift"

    def test_rejects_negative_row(self) -> None:
        with pytest.raises(ValidationError):
            Hypothesis(
                action_type="HYPOTHESIS",
                claim="test", affected_rows=[-1],
                affected_columns=["x"], root_cause_type="t",
            )


class TestDiagnose:
    """Tests for the DIAGNOSE action model."""

    def test_valid_diagnose(self) -> None:
        action = Diagnose(action_type="DIAGNOSE", row=5, column="rating", issue_type="outlier")
        assert action.row == 5

    def test_rejects_negative_row(self) -> None:
        with pytest.raises(ValidationError):
            Diagnose(action_type="DIAGNOSE", row=-1, column="x", issue_type="t")


class TestFix:
    """Tests for the FIX action model."""

    def test_valid_fix(self) -> None:
        action = Fix(
            action_type="FIX", row=5, column="rating",
            new_value="4.5", justification="Corrected decimal shift.",
        )
        assert action.fix_type == "correct_value"

    def test_delete_row(self) -> None:
        action = Fix(
            action_type="FIX", row=3, column="name",
            new_value="", justification="Duplicate row.", fix_type="delete_row",
        )
        assert action.fix_type == "delete_row"

    def test_rejects_empty_justification(self) -> None:
        with pytest.raises(ValidationError):
            Fix(
                action_type="FIX", row=0, column="x",
                new_value="v", justification="",
            )


class TestParseAction:
    """Tests for the parse_action discriminated union parser."""

    def test_parse_inspect(self) -> None:
        action = parse_action({"action_type": "INSPECT_ROWS", "row_indices": [0]})
        assert isinstance(action, InspectRows)

    def test_parse_sql(self) -> None:
        action = parse_action({"action_type": "SQL_QUERY", "query": "SELECT 1"})
        assert isinstance(action, SqlQuery)

    def test_parse_sql_prompt_alias(self) -> None:
        action = parse_action({"action_type": "SQL_QUERY", "sql": "SELECT 1"})
        assert isinstance(action, SqlQuery)
        assert action.query == "SELECT 1"

    def test_parse_stat(self) -> None:
        action = parse_action({"action_type": "STAT_TEST", "test_type": "iqr", "column": "x"})
        assert isinstance(action, StatTest)

    def test_parse_stat_prompt_alias(self) -> None:
        action = parse_action({"action_type": "STAT_TEST", "test": "iqr", "column": "x"})
        assert isinstance(action, StatTest)
        assert action.test_type == "iqr"

    def test_parse_pattern(self) -> None:
        action = parse_action({"action_type": "PATTERN_MATCH", "pattern": ".", "column": "x"})
        assert isinstance(action, PatternMatch)

    def test_parse_pattern_prompt_aliases(self) -> None:
        action = parse_action({
            "action_type": "PATTERN_MATCH",
            "regex": ".",
            "column": "x",
            "expect": "no_match",
        })
        assert isinstance(action, PatternMatch)
        assert action.pattern == "."
        assert action.expect_match is False

    def test_parse_hypothesis(self) -> None:
        action = parse_action({
            "action_type": "HYPOTHESIS", "claim": "c",
            "affected_rows": [0], "affected_columns": ["x"],
            "root_cause_type": "t",
        })
        assert isinstance(action, Hypothesis)

    def test_parse_hypothesis_prompt_shape(self) -> None:
        action = parse_action({
            "action_type": "HYPOTHESIS",
            "claim": "c",
            "root_column": "x",
            "downstream": ["y"],
        })
        assert isinstance(action, Hypothesis)
        assert action.affected_columns == ["x", "y"]
        assert action.root_cause_type == "x"

    def test_parse_diagnose(self) -> None:
        action = parse_action({
            "action_type": "DIAGNOSE", "row": 0, "column": "x", "issue_type": "t",
        })
        assert isinstance(action, Diagnose)

    def test_parse_fix(self) -> None:
        action = parse_action({
            "action_type": "FIX", "row": 0, "column": "x",
            "new_value": "v", "justification": "j",
        })
        assert isinstance(action, Fix)

    def test_parse_fix_prompt_alias(self) -> None:
        action = parse_action({
            "action_type": "FIX", "row": 0, "column": "x",
            "proposed_value": "v",
        })
        assert isinstance(action, Fix)
        assert action.new_value == "v"
        assert action.justification == "Agent proposed value via FIX."

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises((ValidationError, ValueError, KeyError)):
            parse_action({"action_type": "UNKNOWN"})

    def test_rejects_missing_type(self) -> None:
        with pytest.raises((ValidationError, KeyError)):
            parse_action({"row_indices": [0]})
