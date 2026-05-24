"""Tests for reviewable schema inference artifacts."""

from __future__ import annotations

from dataforge.schema_inference import (
    build_constraint_review_artifact,
    dump_constraint_review_artifact,
    infer_schema,
)
from dataforge.table import Table


def test_infer_schema_reports_types_bounds_and_reviewable_fds() -> None:
    """Inference emits candidates without directly mutating repair behavior."""
    table = Table(
        ["city", "state", "amount"],
        [
            {"city": "Boston", "state": "MA", "amount": "10.0"},
            {"city": "Boston", "state": "MA", "amount": "11.0"},
            {"city": "Seattle", "state": "WA", "amount": "12.5"},
            {"city": "Seattle", "state": "WA", "amount": "13.0"},
            {"city": "Austin", "state": "TX", "amount": "9.5"},
        ],
    )

    result = infer_schema(table)
    schema = result.to_schema(include_inferred_constraints=True)

    assert result.columns["amount"] == "float"
    assert any(candidate.kind == "domain_bound" for candidate in result.candidates)
    assert any(
        candidate.kind == "functional_dependency"
        and candidate.columns == ("city",)
        and candidate.dependent == "state"
        for candidate in result.candidates
    )
    assert schema.column_type("amount") == "float"
    assert schema.functional_dependencies


def test_infer_schema_default_schema_excludes_constraints_until_reviewed() -> None:
    """Default conversion preserves inferred types but not review-required constraints."""
    table = Table(
        ["city", "state"],
        [
            {"city": "Boston", "state": "MA"},
            {"city": "Boston", "state": "MA"},
            {"city": "Seattle", "state": "WA"},
            {"city": "Seattle", "state": "WA"},
            {"city": "Austin", "state": "TX"},
        ],
    )

    schema = infer_schema(table).to_schema()

    assert schema.columns == {"city": "str", "state": "str"}
    assert schema.functional_dependencies == ()


def test_constraint_review_artifact_is_pending_stable_and_strict() -> None:
    """Profile inference can be serialized into a deterministic review artifact."""
    table = Table(
        ["code", "name"],
        [
            {"code": "A", "name": "Alpha"},
            {"code": "A", "name": "Alpha"},
            {"code": "B", "name": "Beta"},
            {"code": "B", "name": "Beta"},
            {"code": "C", "name": "Gamma"},
        ],
    )
    inference = infer_schema(table)

    artifact = build_constraint_review_artifact(
        inference,
        source_path=__file__,
        source_sha256="0" * 64,
    )
    repeated = build_constraint_review_artifact(
        inference,
        source_path=__file__,
        source_sha256="0" * 64,
    )

    assert artifact.schema_version == "constraint_review_v1"
    assert {candidate.decision for candidate in artifact.candidates} == {"pending"}
    assert len({candidate.candidate_id for candidate in artifact.candidates}) == len(
        artifact.candidates
    )
    assert dump_constraint_review_artifact(artifact) == dump_constraint_review_artifact(repeated)
