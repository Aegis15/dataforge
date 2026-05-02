"""Reward design parity guard — ensure constants match REWARD_DESIGN.md."""

from __future__ import annotations

from dataforge.env import reward as reward_mod


# Canonical values from REWARD_DESIGN.md (legacy environment parity).
_CANONICAL = {
    "R_DIAGNOSE": 0.10,
    "R_TYPE_BONUS": 0.05,
    "R_FIX": 0.15,
    "R_FIX_PARTIAL": 0.075,
    "R_JUSTIFY_BONUS": 0.05,
    "R_EXPLORE": 0.01,
    "P_FALSE_POS": -0.05,
    "P_WRONG_FIX": -0.08,
    "P_LATE_STEP": -0.02,
    "P_INVALID": -0.01,
    "P_REINSPECT": -0.01,
    "LATE_STEP_THRESHOLD": 0.80,
    "DETECTION_WEIGHT": 0.40,
    "FIX_WEIGHT": 0.60,
    "FALSE_POS_PENALTY_RATE": 0.05,
    "SPAM_THRESHOLD": 2.0,
}


def test_all_constants_match_canonical() -> None:
    """Assert every constant in reward.py matches the REWARD_DESIGN.md values."""
    for name, expected in _CANONICAL.items():
        actual = getattr(reward_mod, name)
        assert actual == expected, (
            f"Parity violation: {name} = {actual}, expected {expected} from REWARD_DESIGN.md"
        )


def test_terminal_formula_matches_legacy() -> None:
    """Assert the terminal score formula produces the same result as the legacy env.

    Known test vector from legacy env:
      3/5 detected, 2/3 fixed, 1 false positive
      → (3/5)*0.40 + (2/3)*0.60 - 1*0.05 = 0.59
    """
    from dataforge.env.reward import EpisodeMetrics, RewardEngine

    engine = RewardEngine()
    metrics = EpisodeMetrics(
        found_issues=3, total_issues=5,
        fixed_issues=2, fixable_issues=3,
        false_positives=1,
    )
    assert engine.compute_terminal_score(metrics) == 0.59
