"""Unit tests for dataforge.env.observation — observation model validation."""

from __future__ import annotations

from dataforge.env.observation import DataForgeObservation, ToolResult


class TestToolResult:
    """Tests for the ToolResult model."""

    def test_success_result(self) -> None:
        r = ToolResult(action_type="INSPECT_ROWS", success=True, data=[{"a": 1}])
        assert r.success is True
        assert r.error is None

    def test_error_result(self) -> None:
        r = ToolResult(
            action_type="SQL_QUERY",
            success=False,
            error={"verdict": "error", "reason": "syntax error", "location": "line 1"},
        )
        assert r.success is False
        assert r.error is not None
        assert r.error["verdict"] == "error"


class TestDataForgeObservation:
    """Tests for the DataForgeObservation model."""

    def test_default_observation(self) -> None:
        obs = DataForgeObservation(step_budget_remaining=30)
        assert obs.done is False
        assert obs.reward == 0.0
        assert obs.visible_rows is None
        assert obs.scratchpad_summary == ""
        assert obs.tool_usage_history == []

    def test_observation_with_rows(self) -> None:
        obs = DataForgeObservation(
            visible_rows=[{"col_a": "val1"}, {"col_a": "val2"}],
            step_budget_remaining=28,
        )
        assert obs.visible_rows is not None
        assert len(obs.visible_rows) == 2

    def test_observation_with_tool_history(self) -> None:
        results = [ToolResult(action_type=f"ACTION_{i}", success=True) for i in range(5)]
        obs = DataForgeObservation(
            step_budget_remaining=25,
            tool_usage_history=results,
            latest_result=results[-1],
        )
        assert len(obs.tool_usage_history) == 5
        assert obs.latest_result is not None

    def test_observation_with_detector_hints(self) -> None:
        obs = DataForgeObservation(
            step_budget_remaining=30,
            detector_hints=["Column 'rating' has suspicious outlier at row 5"],
        )
        assert obs.detector_hints is not None
        assert len(obs.detector_hints) == 1

    def test_done_observation(self) -> None:
        obs = DataForgeObservation(
            step_budget_remaining=0,
            done=True,
            reward=0.75,
            cumulative_reward=0.85,
        )
        assert obs.done is True
        assert obs.reward == 0.75
