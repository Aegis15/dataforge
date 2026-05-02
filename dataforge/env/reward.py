"""Reward engine for the DataForge RL environment.

All constants and formulas are derived bit-for-bit from REWARD_DESIGN.md.

Terminal score: detection_rate * 0.40 + fix_rate * 0.60 - false_positives * fp_rate
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DETECTION_WEIGHT",
    "FALSE_POS_PENALTY_RATE",
    "FIX_WEIGHT",
    "LATE_STEP_THRESHOLD",
    "P_FALSE_POS",
    "P_INVALID",
    "P_LATE_STEP",
    "P_REINSPECT",
    "P_WRONG_FIX",
    "R_DIAGNOSE",
    "R_EXPLORE",
    "R_FIX",
    "R_FIX_PARTIAL",
    "R_JUSTIFY_BONUS",
    "R_TYPE_BONUS",
    "SPAM_THRESHOLD",
    "EpisodeMetrics",
    "RewardEngine",
]

# Positive rewards
R_DIAGNOSE: float = 0.10
R_TYPE_BONUS: float = 0.05
R_FIX: float = 0.15
R_FIX_PARTIAL: float = 0.075
R_JUSTIFY_BONUS: float = 0.05
R_EXPLORE: float = 0.01

# Negative penalties
P_FALSE_POS: float = -0.05
P_WRONG_FIX: float = -0.08
P_LATE_STEP: float = -0.02
P_INVALID: float = -0.01
P_REINSPECT: float = -0.01

# Thresholds
LATE_STEP_THRESHOLD: float = 0.80
DETECTION_WEIGHT: float = 0.40
FIX_WEIGHT: float = 0.60
FALSE_POS_PENALTY_RATE: float = 0.05
SPAM_THRESHOLD: float = 2.0


@dataclass
class EpisodeMetrics:
    """Accumulated metrics for terminal score computation."""

    found_issues: int = 0
    total_issues: int = 0
    fixed_issues: int = 0
    fixable_issues: int = 0
    false_positives: int = 0

    @property
    def total_diagnoses(self) -> int:
        """Total diagnosis attempts (correct + incorrect)."""
        return self.found_issues + self.false_positives


class RewardEngine:
    """Computes dense per-step and terminal rewards."""

    def compute_terminal_score(self, metrics: EpisodeMetrics) -> float:
        """Compute terminal score per REWARD_DESIGN.md formula."""
        if metrics.total_issues == 0:
            return 0.0
        detection_rate = metrics.found_issues / metrics.total_issues
        fix_rate = (
            metrics.fixed_issues / metrics.fixable_issues if metrics.fixable_issues > 0 else 0.0
        )
        fp_rate = FALSE_POS_PENALTY_RATE
        if (
            metrics.total_issues > 0
            and metrics.total_diagnoses > SPAM_THRESHOLD * metrics.total_issues
        ):
            fp_rate *= 2.0
        penalty = metrics.false_positives * fp_rate
        raw = detection_rate * DETECTION_WEIGHT + fix_rate * FIX_WEIGHT - penalty
        return round(max(0.0, min(1.0, raw)), 4)

    def compute_late_penalty(self, step: int, max_steps: int) -> float:
        """Return P_LATE_STEP if past 80% budget, else 0.0."""
        threshold = int(max_steps * LATE_STEP_THRESHOLD)
        return P_LATE_STEP if step > threshold else 0.0

    def compute_exploration_bonus(
        self,
        new_row_indices: set[int],
        inspected_rows: set[int],
        total_rows: int,
        ground_truth_rows: set[int],
        found_issue_rows: set[int],
    ) -> float:
        """Compute exploration bonus for newly-inspected rows."""
        if not new_row_indices:
            return P_REINSPECT
        undiscovered = sum(
            1 for r in new_row_indices if r in ground_truth_rows and r not in found_issue_rows
        )
        bonus = undiscovered * R_EXPLORE
        if total_rows > 0:
            all_inspected = inspected_rows | new_row_indices
            coverage_ratio = len(all_inspected) / total_rows
            bonus += len(new_row_indices) * R_EXPLORE * 0.5 * (1.0 - coverage_ratio)
        return bonus

    def diagnose_reward(self, type_match: bool) -> float:
        """Reward for correct diagnosis."""
        return R_DIAGNOSE + (R_TYPE_BONUS if type_match else 0.0)

    def fix_reward(self, exact: bool, has_justification: bool) -> float:
        """Reward for correct fix."""
        reward = R_FIX if exact else R_FIX_PARTIAL
        return reward + (R_JUSTIFY_BONUS if has_justification else 0.0)
