"""Tests for release-truth checks."""

from __future__ import annotations

from pathlib import Path

from scripts.ci import readme_truth


def test_design_partner_gate_is_explicitly_not_met() -> None:
    """The current release should not imply design-partner evidence exists."""
    assert readme_truth.design_partner_gate_not_met() is True
    assert readme_truth.check_design_partner_claims(readme_truth.DESIGN_PARTNER_TRUTH_DOCS) == []


def test_unqualified_design_partner_claim_fails_when_gate_not_met(tmp_path: Path) -> None:
    """Customer validation prose must be qualified while the evidence gate is unmet."""
    claim_path = tmp_path / "claim.md"
    claim_path.write_text("DataForge15 has design partners and pilot users.\n", encoding="utf-8")

    errors = readme_truth.check_design_partner_claims([claim_path])

    assert errors
    assert "unqualified" in errors[0]


def test_explicitly_unmet_design_partner_claim_is_allowed(tmp_path: Path) -> None:
    """Honest not-met wording should not fail the truth checker."""
    claim_path = tmp_path / "claim.md"
    claim_path.write_text(
        "DataForge15 does not claim design-partner or customer validation evidence yet.\n",
        encoding="utf-8",
    )

    assert readme_truth.check_design_partner_claims([claim_path]) == []
