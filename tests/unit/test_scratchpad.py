"""Unit tests for dataforge.agent.scratchpad."""

from __future__ import annotations

from dataforge.agent.scratchpad import Scratchpad


class TestScratchpad:
    """Tests for the in-episode scratchpad tracker."""

    def test_empty_summary(self) -> None:
        pad = Scratchpad()
        assert pad.summary() == "Hypotheses: 0 (0 pending). Confirmed: 0. Dead ends: 0."

    def test_add_hypothesis(self) -> None:
        pad = Scratchpad()
        h = pad.add_hypothesis("Decimal shift", [5], ["rating"], "decimal_shift")
        assert len(pad.hypotheses) == 1
        assert h.confirmed is False

    def test_confirm_hypothesis(self) -> None:
        pad = Scratchpad()
        pad.add_hypothesis("test", [0], ["x"], "t")
        pad.confirm_hypothesis(0)
        assert pad.hypotheses[0].confirmed is True

    def test_confirm_issue(self) -> None:
        pad = Scratchpad()
        pad.confirm_issue(5, "rating", "decimal_shift")
        assert len(pad.confirmed_issues) == 1
        assert pad.confirmed_issues[0].row == 5

    def test_add_dead_end(self) -> None:
        pad = Scratchpad()
        pad.add_dead_end("Tried zscore on name column", step_number=3)
        assert len(pad.dead_ends) == 1

    def test_reset_clears_all(self) -> None:
        pad = Scratchpad()
        pad.add_hypothesis("h", [0], ["x"], "t")
        pad.confirm_issue(0, "x", "t")
        pad.add_dead_end("d", step_number=1)
        pad.reset()
        assert len(pad.hypotheses) == 0
        assert len(pad.confirmed_issues) == 0
        assert len(pad.dead_ends) == 0

    def test_summary_counts(self) -> None:
        pad = Scratchpad()
        pad.add_hypothesis("h1", [0], ["x"], "t")
        pad.add_hypothesis("h2", [1], ["y"], "t")
        pad.confirm_hypothesis(0)
        pad.confirm_issue(0, "x", "t")
        pad.add_dead_end("d", step_number=1)
        assert pad.summary() == "Hypotheses: 2 (1 pending). Confirmed: 1. Dead ends: 1."
