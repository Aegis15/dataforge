"""Observation builder for the DataForge RL environment.

Constructs agent-visible observations containing partial data views,
scratchpad summaries, tool results, and step budget information.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = ["DataForgeObservation", "ToolResult"]


class ToolResult(BaseModel):
    """Result of a single tool-use action.

    Args:
        action_type: The action type that produced this result.
        success: Whether the action succeeded.
        data: Action-specific result data (rows, stats, matches, etc.).
        error: Structured error information if the action failed.
    """

    action_type: str
    success: bool = True
    data: Any = None
    error: dict[str, Any] | None = None

    model_config = {"frozen": True}


class DataForgeObservation(BaseModel):
    """Agent-visible observation returned after each environment step.

    Args:
        visible_rows: Dataset rows returned by INSPECT_ROWS or reset.
        detector_hints: Optional hints from detectors (partial ground truth).
        scratchpad_summary: Compact summary of the agent's scratchpad.
        step_budget_remaining: Steps left before auto-finalize.
        tool_usage_history: Last 5 tool results for context.
        latest_result: Result of the most recent action.
        done: Whether the episode has ended.
        reward: Step reward.
        cumulative_reward: Running total reward for the episode.
        metadata: Additional key-value metadata.
    """

    visible_rows: list[dict[str, Any]] | None = None
    detector_hints: list[str] | None = None
    scratchpad_summary: str = ""
    step_budget_remaining: int = 0
    tool_usage_history: list[ToolResult] = Field(default_factory=list)
    latest_result: ToolResult | None = None
    done: bool = False
    reward: float = 0.0
    cumulative_reward: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}
