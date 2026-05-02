"""Property tests for reward bounds — ensures rewards stay in valid range."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from dataforge.env.reward import EpisodeMetrics, RewardEngine


@settings(max_examples=200, deadline=2000)
@given(
    found=st.integers(min_value=0, max_value=50),
    total=st.integers(min_value=1, max_value=50),
    fixed=st.integers(min_value=0, max_value=50),
    fixable=st.integers(min_value=0, max_value=50),
    fp=st.integers(min_value=0, max_value=50),
)
def test_terminal_score_in_unit_interval(
    found: int, total: int, fixed: int, fixable: int, fp: int
) -> None:
    """Terminal score must always be in [0, 1]."""
    # Ensure found <= total and fixed <= fixable
    found = min(found, total)
    fixed = min(fixed, max(fixable, 1))
    fixable = max(fixable, 1)

    engine = RewardEngine()
    metrics = EpisodeMetrics(
        found_issues=found,
        total_issues=total,
        fixed_issues=fixed,
        fixable_issues=fixable,
        false_positives=fp,
    )
    score = engine.compute_terminal_score(metrics)
    assert 0.0 <= score <= 1.0, f"Score {score} out of [0, 1] bounds"
