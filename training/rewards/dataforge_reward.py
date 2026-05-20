"""Stateless GRPO reward function for DataForge repair completions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from dataforge.env.reward import EpisodeMetrics, RewardEngine
from dataforge.repair_contract import (
    RepairFix,
    RepairParseResult,
    parse_repair_action,
    repair_failure_taxonomy,
    score_repair_fixes,
    score_repair_fixes_canonicalized,
)


@dataclass(frozen=True, slots=True)
class _TruthCell:
    """Minimal exact-repair ground-truth cell."""

    row: int
    column: str
    clean_value: str


def _completion_text(completion: object) -> str:
    """Return text from TRL string or chat-message completion shapes."""
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list):
        for item in reversed(completion):
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                return str(item["content"])
    return str(completion)


def _batch_item(value: object, index: int, default: object) -> object:
    """Return a per-example item from a scalar-or-batch kwarg."""
    if value is None:
        return default
    if isinstance(value, list) and index < len(value):
        return value[index]
    return value


def _truth_cells(raw_truth: object) -> list[_TruthCell]:
    """Normalize supported ground-truth shapes into ``_TruthCell`` rows."""
    if raw_truth is None:
        return []
    if not isinstance(raw_truth, list):
        raise ValueError("ground_truth entries must be lists.")
    cells: list[_TruthCell] = []
    for raw_cell in raw_truth:
        if isinstance(raw_cell, dict):
            clean_value = raw_cell.get(
                "clean_value", raw_cell.get("expected", raw_cell.get("new_value"))
            )
            cells.append(
                _TruthCell(
                    row=int(raw_cell["row"]),
                    column=str(raw_cell["column"]),
                    clean_value=str(clean_value),
                )
            )
            continue
        cell_obj = cast(Any, raw_cell)
        row = cell_obj.row
        column = cell_obj.column
        clean_value = (
            cell_obj.clean_value if hasattr(cell_obj, "clean_value") else cell_obj.expected
        )
        cells.append(_TruthCell(row=int(row), column=str(column), clean_value=str(clean_value)))
    return cells


def _repairs(parse_result: RepairParseResult) -> list[RepairFix]:
    """Return parsed repairs, or an empty list for invalid/finish completions."""
    if not parse_result.ok or parse_result.action is None:
        return []
    return parse_result.action.repairs


def _valid_rows(raw_rows: object, truth: list[_TruthCell], repairs: list[RepairFix]) -> list[int]:
    """Return valid row ids for failure diagnostics."""
    if isinstance(raw_rows, list):
        return [int(row) for row in raw_rows]
    rows = {cell.row for cell in truth}
    rows.update(repair.row for repair in repairs)
    return sorted(rows)


def _allowed_columns(
    raw_columns: object, truth: list[_TruthCell], repairs: list[RepairFix]
) -> list[str]:
    """Return allowed columns for failure diagnostics."""
    if isinstance(raw_columns, list):
        return [str(column) for column in raw_columns]
    columns = {cell.column for cell in truth}
    columns.update(repair.column for repair in repairs)
    return sorted(columns)


def _score_completion(
    completion: object,
    *,
    raw_truth: object,
    raw_allowed_columns: object,
    raw_valid_rows: object,
) -> tuple[float, dict[str, Any]]:
    """Score one completion and return reward plus diagnostics."""
    text = _completion_text(completion)
    parse_result = parse_repair_action(text)
    if not parse_result.ok:
        return 0.0, {
            "parse_ok": False,
            "error_kind": parse_result.error_kind,
            "error_message": parse_result.error_message,
            "failure_taxonomy": {},
        }

    truth = _truth_cells(raw_truth)
    repairs = _repairs(parse_result)
    if not truth and not repairs:
        return 1.0, {
            "parse_ok": True,
            "action": parse_result.action.action if parse_result.action else None,
            "score": {"tp": 0, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0},
            "failure_taxonomy": {},
        }

    score = score_repair_fixes(truth, repairs)
    canonicalized_score = score_repair_fixes_canonicalized(truth, repairs)
    valid_rows = _valid_rows(raw_valid_rows, truth, repairs)
    allowed_columns = _allowed_columns(raw_allowed_columns, truth, repairs)
    taxonomy = repair_failure_taxonomy(
        ground_truth=truth,
        fixes=repairs,
        allowed_columns=allowed_columns,
        valid_rows=valid_rows,
    )
    metrics = EpisodeMetrics(
        found_issues=score.tp,
        total_issues=len(truth),
        fixed_issues=score.tp,
        fixable_issues=len(truth),
        false_positives=score.fp,
    )
    reward = RewardEngine().compute_terminal_score(metrics)
    diagnostics = {
        "parse_ok": True,
        "action": parse_result.action.action if parse_result.action else None,
        "score": score.model_dump(mode="json"),
        "canonicalized_score": canonicalized_score.model_dump(mode="json"),
        "failure_taxonomy": taxonomy,
    }
    return max(0.0, min(1.0, float(reward))), diagnostics


def dataforge_reward(completions: list[Any], **kwargs: Any) -> list[float]:
    """Return one exact-repair reward per GRPO completion.

    Expected optional batch kwargs are ``ground_truth``, ``allowed_columns``, and
    ``valid_rows``. The function is intentionally local and stateless: it parses
    JSON completions and scores exact cell repairs without calling an OpenEnv
    HTTP endpoint or any external provider.
    """
    raw_truth_batch = kwargs.get("ground_truth", kwargs.get("ground_truth_cells"))
    raw_columns_batch = kwargs.get("allowed_columns")
    raw_rows_batch = kwargs.get("valid_rows")
    rewards: list[float] = []
    diagnostics: list[dict[str, Any]] = []
    for index, completion in enumerate(completions):
        reward, diagnostic = _score_completion(
            completion,
            raw_truth=_batch_item(raw_truth_batch, index, []),
            raw_allowed_columns=_batch_item(raw_columns_batch, index, []),
            raw_valid_rows=_batch_item(raw_rows_batch, index, []),
        )
        rewards.append(reward)
        diagnostics.append(diagnostic)
    setattr(dataforge_reward, "last_diagnostics", diagnostics)
    return rewards


setattr(dataforge_reward, "last_diagnostics", [])
