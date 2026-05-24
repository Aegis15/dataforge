"""OpenEnv-core adapter smoke tests."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_openenv_core_adapter_reset_step_close() -> None:
    """Verify DataForge implements OpenEnv core Environment semantics."""
    openenv_core = pytest.importorskip("openenv.core.env_server")
    del openenv_core

    from dataforge.env.openenv_core import DataForgeOpenEnv, DataForgeOpenEnvAction

    env = DataForgeOpenEnv()
    observation = env.reset(seed=42)
    assert observation.done is False
    assert observation.step_budget_remaining > 0

    stepped = env.step(
        DataForgeOpenEnvAction(action_type="INSPECT_ROWS", row_indices=[0], metadata={})
    )
    assert stepped.latest_result is not None
    assert stepped.latest_result["success"] is True

    env.close()
