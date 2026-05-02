"""In-episode hypothesis and issue tracker for the DataForge RL agent.

The scratchpad is a mutable, episode-scoped data structure that the agent
uses to record hypotheses, confirmed issues, and dead ends. The environment
exposes a compact summary of the scratchpad in each observation, enabling
the agent to reason about its investigation history without direct access
to the underlying data structure.

Example::

    >>> from dataforge.agent.scratchpad import Scratchpad
    >>> pad = Scratchpad()
    >>> pad.add_hypothesis("Rating column has decimal shift", [5], ["rating"], "decimal_shift")
    >>> pad.confirm_issue(5, "rating", "decimal_shift")
    >>> pad.summary()
    'Hypotheses: 1 (0 pending). Confirmed: 1. Dead ends: 0.'
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ConfirmedIssue",
    "DeadEnd",
    "HypothesisRecord",
    "Scratchpad",
]


@dataclass(frozen=True)
class HypothesisRecord:
    """A recorded hypothesis about a data-quality root cause.

    Args:
        claim: Textual description of the hypothesis.
        affected_rows: Row indices the hypothesis covers.
        affected_columns: Column names the hypothesis covers.
        root_cause_type: Detector-vocabulary root cause type.
        confirmed: Whether the hypothesis was confirmed by ground truth.
    """

    claim: str
    affected_rows: tuple[int, ...]
    affected_columns: tuple[str, ...]
    root_cause_type: str
    confirmed: bool = False


@dataclass(frozen=True)
class ConfirmedIssue:
    """A confirmed data-quality issue at a specific location.

    Args:
        row: Zero-indexed row number.
        column: Column name.
        issue_type: Issue type classification.
    """

    row: int
    column: str
    issue_type: str


@dataclass(frozen=True)
class DeadEnd:
    """A recorded dead end — an investigation path that yielded nothing.

    Args:
        description: What was tried and why it failed.
        step_number: Step at which the dead end was recorded.
    """

    description: str
    step_number: int


@dataclass
class Scratchpad:
    """Mutable in-episode tracker for hypotheses, confirmed issues, and dead ends.

    Reset at the start of each episode. The ``summary()`` method produces a
    compact string for inclusion in agent observations.

    Example::

        >>> pad = Scratchpad()
        >>> pad.add_hypothesis("Decimal shift in rating", [5], ["rating"], "decimal_shift")
        >>> len(pad.hypotheses)
        1
    """

    hypotheses: list[HypothesisRecord] = field(default_factory=list)
    confirmed_issues: list[ConfirmedIssue] = field(default_factory=list)
    dead_ends: list[DeadEnd] = field(default_factory=list)

    def add_hypothesis(
        self,
        claim: str,
        affected_rows: list[int],
        affected_columns: list[str],
        root_cause_type: str,
    ) -> HypothesisRecord:
        """Record a new hypothesis.

        Args:
            claim: Textual description of the hypothesis.
            affected_rows: Row indices the hypothesis covers.
            affected_columns: Column names the hypothesis covers.
            root_cause_type: Detector-vocabulary root cause type.

        Returns:
            The recorded hypothesis.
        """
        record = HypothesisRecord(
            claim=claim,
            affected_rows=tuple(affected_rows),
            affected_columns=tuple(affected_columns),
            root_cause_type=root_cause_type,
        )
        self.hypotheses.append(record)
        return record

    def confirm_hypothesis(self, index: int) -> None:
        """Mark a hypothesis as confirmed.

        Args:
            index: Index into the ``hypotheses`` list.

        Raises:
            IndexError: If the index is out of range.
        """
        old = self.hypotheses[index]
        self.hypotheses[index] = HypothesisRecord(
            claim=old.claim,
            affected_rows=old.affected_rows,
            affected_columns=old.affected_columns,
            root_cause_type=old.root_cause_type,
            confirmed=True,
        )

    def confirm_issue(self, row: int, column: str, issue_type: str) -> None:
        """Record a confirmed issue.

        Args:
            row: Zero-indexed row number.
            column: Column name.
            issue_type: Issue type classification.
        """
        self.confirmed_issues.append(ConfirmedIssue(row=row, column=column, issue_type=issue_type))

    def add_dead_end(self, description: str, step_number: int) -> None:
        """Record a dead end.

        Args:
            description: What was tried and why it failed.
            step_number: Step at which the dead end was recorded.
        """
        self.dead_ends.append(DeadEnd(description=description, step_number=step_number))

    def reset(self) -> None:
        """Clear all tracked state for a new episode."""
        self.hypotheses.clear()
        self.confirmed_issues.clear()
        self.dead_ends.clear()

    def summary(self) -> str:
        """Produce a compact summary string for observation embedding.

        Returns:
            A one-line summary of scratchpad state.

        Example::

            >>> Scratchpad().summary()
            'Hypotheses: 0 (0 pending). Confirmed: 0. Dead ends: 0.'
        """
        pending = sum(1 for h in self.hypotheses if not h.confirmed)
        return (
            f"Hypotheses: {len(self.hypotheses)} ({pending} pending). "
            f"Confirmed: {len(self.confirmed_issues)}. "
            f"Dead ends: {len(self.dead_ends)}."
        )
