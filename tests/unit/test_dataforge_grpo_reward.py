"""Unit tests for the stateless DataForge GRPO reward function."""

from __future__ import annotations

import json

from training.rewards.dataforge_reward import dataforge_reward


def _completion(repairs: list[dict[str, object]], *, action: str = "submit_repairs") -> str:
    return json.dumps({"action": action, "repairs": repairs}, sort_keys=True)


def test_grpo_reward_scores_exact_repair_as_one() -> None:
    rewards = dataforge_reward(
        [_completion([{"row": 0, "column": "Name", "new_value": "Alice", "reason": "fix"}])],
        ground_truth=[[{"row": 0, "column": "Name", "clean_value": "Alice"}]],
        allowed_columns=[["Name"]],
        valid_rows=[[0]],
    )

    assert rewards == [1.0]
    assert dataforge_reward.last_diagnostics[0]["score"]["tp"] == 1


def test_grpo_reward_scores_finish_on_clean_chunk_as_one() -> None:
    rewards = dataforge_reward(
        [_completion([], action="finish")],
        ground_truth=[[]],
        allowed_columns=[["Name"]],
        valid_rows=[[0]],
    )

    assert rewards == [1.0]
    assert dataforge_reward.last_diagnostics[0]["failure_taxonomy"] == {}


def test_grpo_reward_penalizes_wrong_value_and_schema_case_errors() -> None:
    rewards = dataforge_reward(
        [_completion([{"row": 0, "column": "name", "new_value": "Bob", "reason": "fix"}])],
        ground_truth=[[{"row": 0, "column": "Name", "clean_value": "Alice"}]],
        allowed_columns=[["Name"]],
        valid_rows=[[0]],
    )

    assert rewards == [0.0]
    assert dataforge_reward.last_diagnostics[0]["failure_taxonomy"]["schema_case_error"] == 1


def test_grpo_reward_handles_malformed_json_without_raising() -> None:
    rewards = dataforge_reward(
        ["not json"], ground_truth=[[{"row": 0, "column": "A", "clean_value": "x"}]]
    )

    assert rewards == [0.0]
    assert dataforge_reward.last_diagnostics[0]["parse_ok"] is False
    assert dataforge_reward.last_diagnostics[0]["error_kind"] == "parse_failure"


def test_grpo_reward_uses_last_write_wins_for_duplicate_repairs() -> None:
    rewards = dataforge_reward(
        [
            _completion(
                [
                    {"row": 0, "column": "A", "new_value": "wrong", "reason": "first"},
                    {"row": 0, "column": "A", "new_value": "right", "reason": "second"},
                ]
            )
        ],
        ground_truth=[[{"row": 0, "column": "A", "clean_value": "right"}]],
    )

    assert rewards == [1.0]


def test_grpo_reward_accepts_chat_style_completion_and_preserves_batch_order() -> None:
    rewards = dataforge_reward(
        [
            [
                {
                    "role": "assistant",
                    "content": _completion(
                        [{"row": 0, "column": "A", "new_value": "x", "reason": "fix"}]
                    ),
                }
            ],
            _completion([{"row": 0, "column": "A", "new_value": "wrong", "reason": "fix"}]),
            _completion([], action="finish"),
        ],
        ground_truth=[
            [{"row": 0, "column": "A", "clean_value": "x"}],
            [{"row": 0, "column": "A", "clean_value": "x"}],
            [],
        ],
    )

    assert rewards == [1.0, 0.0, 1.0]
