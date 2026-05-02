"""Integration tests for the DataForge OpenEnv environment spec."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dataforge.agent.tool_actions import (
    Diagnose,
    Fix,
    Hypothesis,
    InspectRows,
    PatternMatch,
    SqlQuery,
    StatTest,
)
from dataforge.env import environment as environment_mod
from dataforge.env.environment import DataForgeEnv
from dataforge.env.server import app


@pytest.fixture()
def env() -> DataForgeEnv:
    """Create a fresh environment for each test."""
    return DataForgeEnv(max_steps=30)


class TestReset:
    """Tests for environment reset."""

    def test_reset_returns_valid_observation(self, env: DataForgeEnv) -> None:
        result = env.reset(seed=42)
        assert result.observation.done is False
        assert result.observation.step_budget_remaining > 0
        assert result.observation.visible_rows is not None
        assert len(result.observation.visible_rows) > 0

    def test_reset_includes_metadata(self, env: DataForgeEnv) -> None:
        result = env.reset(seed=42)
        assert "episode_id" in result.info
        assert "total_rows" in result.observation.metadata

    def test_reset_generates_ground_truth(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        state = env.state()
        assert state.total_issues >= 0


class TestInspectRows:
    """Tests for INSPECT_ROWS action."""

    def test_inspect_returns_rows(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = InspectRows(action_type="INSPECT_ROWS", row_indices=[0, 1, 2])
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is True

    def test_inspect_out_of_bounds(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = InspectRows(action_type="INSPECT_ROWS", row_indices=[9999])
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False


class TestSqlQuery:
    """Tests for SQL_QUERY action."""

    def test_valid_select(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = SqlQuery(action_type="SQL_QUERY", query="SELECT * FROM data LIMIT 3")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is True

    def test_write_rejected(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = SqlQuery(action_type="SQL_QUERY", query="DROP TABLE data")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False
        assert result.observation.latest_result.error is not None


class TestStatTest:
    """Tests for STAT_TEST action."""

    def test_zscore_on_numeric_column(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = StatTest(action_type="STAT_TEST", test_type="zscore", column="rating")
        result = env.step(action)
        lr = result.observation.latest_result
        assert lr is not None
        assert lr.success is True

    def test_invalid_column(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = StatTest(action_type="STAT_TEST", test_type="zscore", column="nonexistent")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False
        assert result.done is False  # episode NOT terminated by error


class TestPatternMatch:
    """Tests for PATTERN_MATCH action."""

    def test_valid_regex(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = PatternMatch(action_type="PATTERN_MATCH", pattern=r"^\d{5}$", column="zip_code")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is True

    def test_invalid_regex(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = PatternMatch(action_type="PATTERN_MATCH", pattern="[invalid", column="zip_code")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False
        assert result.done is False


class TestHypothesis:
    """Tests for HYPOTHESIS action."""

    def test_records_hypothesis(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = Hypothesis(
            action_type="HYPOTHESIS", claim="Decimal shift in rating",
            affected_rows=[5], affected_columns=["rating"],
            root_cause_type="decimal_shift",
        )
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is True
        assert "Hypotheses: 1" in result.observation.scratchpad_summary


class TestDiagnose:
    """Tests for DIAGNOSE action."""

    def test_diagnose_out_of_bounds(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = Diagnose(action_type="DIAGNOSE", row=9999, column="rating", issue_type="outlier")
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False


class TestFix:
    """Tests for FIX action."""

    def test_fix_out_of_bounds(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        action = Fix(
            action_type="FIX", row=9999, column="rating",
            new_value="4.5", justification="test",
        )
        result = env.step(action)
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False

    def test_fix_fails_closed_when_safety_pipeline_errors(
        self,
        env: DataForgeEnv,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env.reset(seed=42)

        def boom(self: DataForgeEnv, action: Fix) -> tuple[bool, str]:
            raise RuntimeError("simulated verifier failure")

        monkeypatch.setattr(environment_mod.DataForgeEnv, "_check_safety", boom)
        action = Fix(
            action_type="FIX", row=0, column="rating",
            new_value="4.5", justification="test",
        )
        result = env.step(action)
        latest = result.observation.latest_result
        assert latest is not None
        assert latest.success is False
        assert latest.error is not None
        assert latest.error["verdict"] == "rejected"
        assert "simulated verifier failure" in latest.error["reason"]


class TestStepBudgetTermination:
    """Tests for auto-finalize at step budget exhaustion."""

    def test_auto_finalize(self) -> None:
        env = DataForgeEnv(max_steps=3)
        env.reset(seed=42)
        for i in range(3):
            result = env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[i]))
        assert result.done is True

    def test_step_after_done(self) -> None:
        env = DataForgeEnv(max_steps=1)
        env.reset(seed=42)
        env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[0]))
        result = env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[1]))
        assert result.done is True


class TestRawDictAction:
    """Tests for stepping with raw dicts instead of typed models."""

    def test_dict_inspect(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        result = env.step({"action_type": "INSPECT_ROWS", "row_indices": [0, 1]})
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is True

    def test_invalid_dict(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        result = env.step({"action_type": "UNKNOWN"})
        assert result.observation.latest_result is not None
        assert result.observation.latest_result.success is False


class TestState:
    """Tests for environment state snapshots."""

    def test_state_after_reset(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        state = env.state()
        assert state.step_count == 0
        assert state.is_done is False

    def test_state_after_step(self, env: DataForgeEnv) -> None:
        env.reset(seed=42)
        env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[0]))
        state = env.state()
        assert state.step_count == 1


class TestServerState:
    """Tests for OpenEnv HTTP state endpoint."""

    def test_state_endpoint_returns_snapshot(self) -> None:
        client = TestClient(app)
        client.post("/reset", params={"seed": 42})
        response = client.get("/state")
        assert response.status_code == 200
        body = response.json()
        assert body["step_count"] == 0
        assert body["is_done"] is False


class TestToolHistory:
    """Tests for tool usage history tracking."""

    def test_history_limited_to_5(self) -> None:
        env = DataForgeEnv(max_steps=10)
        env.reset(seed=42)
        for i in range(7):
            env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[i % 9]))
        state_obs = env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[0]))
        assert len(state_obs.observation.tool_usage_history) <= 5
