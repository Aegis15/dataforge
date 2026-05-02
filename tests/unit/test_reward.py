"""Unit tests for dataforge.env.reward — reward formula parity with REWARD_DESIGN.md."""

from __future__ import annotations

from dataforge.env.reward import (
    DETECTION_WEIGHT,
    FALSE_POS_PENALTY_RATE,
    FIX_WEIGHT,
    LATE_STEP_THRESHOLD,
    P_FALSE_POS,
    P_INVALID,
    P_LATE_STEP,
    P_REINSPECT,
    P_WRONG_FIX,
    R_DIAGNOSE,
    R_EXPLORE,
    R_FIX,
    R_FIX_PARTIAL,
    R_JUSTIFY_BONUS,
    R_TYPE_BONUS,
    SPAM_THRESHOLD,
    EpisodeMetrics,
    RewardEngine,
)


class TestRewardConstants:
    """Verify all constants match REWARD_DESIGN.md exactly."""

    def test_r_diagnose(self) -> None:
        assert R_DIAGNOSE == 0.10

    def test_r_type_bonus(self) -> None:
        assert R_TYPE_BONUS == 0.05

    def test_r_fix(self) -> None:
        assert R_FIX == 0.15

    def test_r_fix_partial(self) -> None:
        assert R_FIX_PARTIAL == 0.075

    def test_r_justify_bonus(self) -> None:
        assert R_JUSTIFY_BONUS == 0.05

    def test_r_explore(self) -> None:
        assert R_EXPLORE == 0.01

    def test_p_false_pos(self) -> None:
        assert P_FALSE_POS == -0.05

    def test_p_wrong_fix(self) -> None:
        assert P_WRONG_FIX == -0.08

    def test_p_late_step(self) -> None:
        assert P_LATE_STEP == -0.02

    def test_p_invalid(self) -> None:
        assert P_INVALID == -0.01

    def test_p_reinspect(self) -> None:
        assert P_REINSPECT == -0.01

    def test_late_step_threshold(self) -> None:
        assert LATE_STEP_THRESHOLD == 0.80

    def test_detection_weight(self) -> None:
        assert DETECTION_WEIGHT == 0.40

    def test_fix_weight(self) -> None:
        assert FIX_WEIGHT == 0.60

    def test_false_pos_penalty_rate(self) -> None:
        assert FALSE_POS_PENALTY_RATE == 0.05

    def test_spam_threshold(self) -> None:
        assert SPAM_THRESHOLD == 2.0


class TestTerminalScore:
    """Verify terminal score formula matches REWARD_DESIGN.md."""

    def setup_method(self) -> None:
        self.engine = RewardEngine()

    def test_perfect_episode(self) -> None:
        metrics = EpisodeMetrics(
            found_issues=5,
            total_issues=5,
            fixed_issues=3,
            fixable_issues=3,
            false_positives=0,
        )
        score = self.engine.compute_terminal_score(metrics)
        # (5/5)*0.40 + (3/3)*0.60 - 0 = 0.40 + 0.60 = 1.0
        assert score == 1.0

    def test_no_issues(self) -> None:
        metrics = EpisodeMetrics(total_issues=0)
        assert self.engine.compute_terminal_score(metrics) == 0.0

    def test_partial_detection_and_fix(self) -> None:
        metrics = EpisodeMetrics(
            found_issues=3,
            total_issues=5,
            fixed_issues=2,
            fixable_issues=3,
            false_positives=1,
        )
        # (3/5)*0.40 + (2/3)*0.60 - 1*0.05
        # = 0.24 + 0.40 - 0.05 = 0.59
        score = self.engine.compute_terminal_score(metrics)
        assert score == 0.59

    def test_spam_doubles_penalty(self) -> None:
        metrics = EpisodeMetrics(
            found_issues=3,
            total_issues=5,
            fixed_issues=0,
            fixable_issues=3,
            false_positives=8,
        )
        # total_diagnoses = 3 + 8 = 11 > 2.0 * 5 = 10 → fp_rate doubles
        # (3/5)*0.40 + 0 - 8*0.10 = 0.24 - 0.80 → clamped to 0.0
        score = self.engine.compute_terminal_score(metrics)
        assert score == 0.0

    def test_score_clamped_to_unit(self) -> None:
        metrics = EpisodeMetrics(
            found_issues=5,
            total_issues=5,
            fixed_issues=5,
            fixable_issues=5,
            false_positives=0,
        )
        assert 0.0 <= self.engine.compute_terminal_score(metrics) <= 1.0


class TestLatePenalty:
    """Verify late-step penalty logic."""

    def setup_method(self) -> None:
        self.engine = RewardEngine()

    def test_no_penalty_before_threshold(self) -> None:
        assert self.engine.compute_late_penalty(step=20, max_steps=30) == 0.0

    def test_penalty_after_threshold(self) -> None:
        # 80% of 30 = 24; step 25 is past threshold
        assert self.engine.compute_late_penalty(step=25, max_steps=30) == P_LATE_STEP

    def test_at_threshold_no_penalty(self) -> None:
        assert self.engine.compute_late_penalty(step=24, max_steps=30) == 0.0


class TestExplorationBonus:
    """Verify exploration bonus computation."""

    def setup_method(self) -> None:
        self.engine = RewardEngine()

    def test_reinspect_penalty(self) -> None:
        bonus = self.engine.compute_exploration_bonus(
            new_row_indices=set(),
            inspected_rows={0, 1},
            total_rows=10,
            ground_truth_rows={3},
            found_issue_rows=set(),
        )
        assert bonus == P_REINSPECT

    def test_bonus_for_new_rows_with_issues(self) -> None:
        bonus = self.engine.compute_exploration_bonus(
            new_row_indices={3, 4},
            inspected_rows={0, 1},
            total_rows=10,
            ground_truth_rows={3},
            found_issue_rows=set(),
        )
        assert bonus > 0


class TestDiagnoseReward:
    """Verify diagnose reward computation."""

    def setup_method(self) -> None:
        self.engine = RewardEngine()

    def test_correct_diagnosis_no_type_match(self) -> None:
        assert self.engine.diagnose_reward(type_match=False) == R_DIAGNOSE

    def test_correct_diagnosis_with_type_match(self) -> None:
        assert self.engine.diagnose_reward(type_match=True) == R_DIAGNOSE + R_TYPE_BONUS


class TestFixReward:
    """Verify fix reward computation."""

    def setup_method(self) -> None:
        self.engine = RewardEngine()

    def test_exact_fix_no_justification(self) -> None:
        assert self.engine.fix_reward(exact=True, has_justification=False) == R_FIX

    def test_exact_fix_with_justification(self) -> None:
        assert self.engine.fix_reward(exact=True, has_justification=True) == R_FIX + R_JUSTIFY_BONUS

    def test_partial_fix(self) -> None:
        assert self.engine.fix_reward(exact=False, has_justification=False) == R_FIX_PARTIAL
