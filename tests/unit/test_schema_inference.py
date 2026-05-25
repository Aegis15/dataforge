"""Tests for reviewable schema inference artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataforge.schema_inference import (
    ConstraintReviewError,
    build_constraint_review_artifact,
    dump_constraint_review_artifact,
    infer_schema,
    load_constraint_review_artifact,
    update_constraint_review_artifact,
    validate_constraint_review_artifact,
    write_constraint_review_artifact_atomic,
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


def test_constraint_review_updates_decisions_notes_and_keeps_order() -> None:
    """Review updates are explicit and preserve deterministic artifact order."""
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
    artifact = build_constraint_review_artifact(
        infer_schema(table),
        source_path=__file__,
        source_sha256="0" * 64,
    )
    first_id = artifact.candidates[0].candidate_id
    second_id = artifact.candidates[1].candidate_id

    updated = update_constraint_review_artifact(
        artifact,
        accept_ids=(first_id,),
        reject_ids=(second_id,),
        notes={first_id: "reviewed"},
    )

    assert [candidate.candidate_id for candidate in updated.candidates] == [
        candidate.candidate_id for candidate in artifact.candidates
    ]
    assert updated.candidates[0].decision == "accepted"
    assert updated.candidates[0].review_note == "reviewed"
    assert updated.candidates[1].decision == "rejected"
    assert artifact.candidates[0].decision == "pending"


def test_constraint_review_rejects_unknown_and_conflicting_candidate_ids() -> None:
    """Unknown ids and conflicting decisions fail closed."""
    table = Table(
        ["id", "amount"],
        [{"id": "1", "amount": "10"}, {"id": "2", "amount": "11"}],
    )
    artifact = build_constraint_review_artifact(
        infer_schema(table),
        source_path=__file__,
        source_sha256="0" * 64,
    )
    candidate_id = artifact.candidates[0].candidate_id

    with pytest.raises(ConstraintReviewError, match="Unknown candidate ids"):
        update_constraint_review_artifact(artifact, accept_ids=("cnd-0000000000000000",))

    with pytest.raises(ConstraintReviewError, match="conflicting review decisions"):
        update_constraint_review_artifact(
            artifact,
            accept_ids=(candidate_id,),
            reject_ids=(candidate_id,),
        )


def test_constraint_review_rejects_duplicate_and_tampered_ids() -> None:
    """Artifact integrity checks catch duplicate ids and payload/id drift."""
    table = Table(
        ["id", "amount"],
        [{"id": "1", "amount": "10"}, {"id": "2", "amount": "11"}],
    )
    artifact = build_constraint_review_artifact(
        infer_schema(table),
        source_path=__file__,
        source_sha256="0" * 64,
    )

    duplicate = artifact.model_copy(
        update={"candidates": [artifact.candidates[0], artifact.candidates[0]]}
    )
    with pytest.raises(ConstraintReviewError, match="duplicate candidate ids"):
        validate_constraint_review_artifact(duplicate)

    tampered = artifact.model_copy(
        update={
            "candidates": [
                artifact.candidates[0].model_copy(update={"candidate_id": "cnd-0000000000000000"})
            ]
        }
    )
    with pytest.raises(ConstraintReviewError, match="candidate id payload mismatch"):
        validate_constraint_review_artifact(tampered)


def test_constraint_review_atomic_write_round_trips(tmp_path: Path) -> None:
    """Atomic writes produce deterministic bytes that strict loading accepts."""
    table = Table(
        ["id", "amount"],
        [{"id": "1", "amount": "10"}, {"id": "2", "amount": "11"}],
    )
    artifact = build_constraint_review_artifact(
        infer_schema(table),
        source_path=__file__,
        source_sha256="0" * 64,
    )
    path = tmp_path / "constraints.json"

    written_sha256 = write_constraint_review_artifact_atomic(path, artifact)
    loaded, loaded_sha256 = load_constraint_review_artifact(path)

    assert loaded == artifact
    assert loaded_sha256 == written_sha256
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "constraint_review_v1"
