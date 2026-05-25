"""CLI and TUI tests for reviewed constraint artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

from typer.testing import CliRunner

from dataforge.cli import app
from dataforge.cli.constraints import ConstraintReviewApp
from dataforge.schema_inference import (
    ConstraintReviewArtifact,
    build_constraint_review_artifact,
    dump_constraint_review_artifact,
    infer_schema,
)
from dataforge.table import read_csv

runner = CliRunner()


def _write_fd_repairable_csv(path: Path) -> None:
    """Write a small table with one functional dependency violation."""
    path.write_text(
        "code,name\n"
        "A,Alpha\n"
        "A,Alpha\n"
        "A,Alfa\n"
        "B,Beta\n"
        "B,Beta\n"
        "C,Gamma\n"
        "C,Gamma\n"
        "D,Delta\n"
        "D,Delta\n"
        "E,Echo\n",
        encoding="utf-8",
    )


def _fd_artifact(csv_path: Path) -> ConstraintReviewArtifact:
    return build_constraint_review_artifact(
        infer_schema(read_csv(csv_path)),
        source_path=csv_path,
        source_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    )


def _fd_candidate_id(artifact: ConstraintReviewArtifact) -> str:
    for reviewed in artifact.candidates:
        candidate = reviewed.candidate
        if (
            candidate.kind == "functional_dependency"
            and candidate.columns == ("code",)
            and candidate.dependent == "name"
        ):
            return reviewed.candidate_id
    raise AssertionError("expected code -> name FD candidate")


def test_constraints_review_json_lists_candidates(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    constraints_path = tmp_path / "constraints.json"
    _write_fd_repairable_csv(csv_path)
    constraints_path.write_text(dump_constraint_review_artifact(_fd_artifact(csv_path)))

    result = runner.invoke(
        app,
        ["constraints", "review", str(constraints_path), "--no-tui", "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "constraint_review_v1"
    assert payload["candidate_count"] > 0
    assert payload["decision_counts"]["pending"] == payload["candidate_count"]
    assert any(candidate["repair_supported"] for candidate in payload["candidates"])


def test_constraints_review_noninteractive_accept_reject_note(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    constraints_path = tmp_path / "constraints.json"
    _write_fd_repairable_csv(csv_path)
    artifact = _fd_artifact(csv_path)
    fd_id = _fd_candidate_id(artifact)
    rejected_id = next(
        reviewed.candidate_id for reviewed in artifact.candidates if reviewed.candidate_id != fd_id
    )
    constraints_path.write_text(dump_constraint_review_artifact(artifact), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "constraints",
            "review",
            str(constraints_path),
            "--accept",
            fd_id,
            "--reject",
            rejected_id,
            "--note",
            f"{fd_id}=reviewed by analyst",
            "--no-tui",
            "--json",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(constraints_path.read_text(encoding="utf-8"))
    reviewed_by_id = {candidate["candidate_id"]: candidate for candidate in payload["candidates"]}
    assert reviewed_by_id[fd_id]["decision"] == "accepted"
    assert reviewed_by_id[fd_id]["review_note"] == "reviewed by analyst"
    assert reviewed_by_id[rejected_id]["decision"] == "rejected"


def test_constraints_review_dry_run_leaves_file_unchanged(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    constraints_path = tmp_path / "constraints.json"
    _write_fd_repairable_csv(csv_path)
    artifact = _fd_artifact(csv_path)
    fd_id = _fd_candidate_id(artifact)
    constraints_path.write_text(dump_constraint_review_artifact(artifact), encoding="utf-8")
    before = constraints_path.read_bytes()

    result = runner.invoke(
        app,
        [
            "constraints",
            "review",
            str(constraints_path),
            "--accept",
            fd_id,
            "--dry-run",
            "--no-tui",
            "--json",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert constraints_path.read_bytes() == before
    assert json.loads(result.output)["sha256"] is None


def test_constraints_review_output_writes_separate_artifact(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    constraints_path = tmp_path / "constraints.json"
    output_path = tmp_path / "reviewed.json"
    _write_fd_repairable_csv(csv_path)
    artifact = _fd_artifact(csv_path)
    fd_id = _fd_candidate_id(artifact)
    constraints_path.write_text(dump_constraint_review_artifact(artifact), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "constraints",
            "review",
            str(constraints_path),
            "--accept",
            fd_id,
            "--output",
            str(output_path),
            "--no-tui",
            "--json",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert '"accepted": 1' in result.output
    assert (
        json.loads(constraints_path.read_text(encoding="utf-8"))["candidates"][0]["decision"]
        == "pending"
    )


def test_constraints_review_invalid_artifact_exits_cleanly(tmp_path: Path) -> None:
    constraints_path = tmp_path / "constraints.json"
    constraints_path.write_text('{"schema_version": "wrong"}', encoding="utf-8")

    result = runner.invoke(app, ["constraints", "review", str(constraints_path), "--no-tui"])

    assert result.exit_code == 2
    assert "Constraint Review Error" in result.output


def test_constraints_review_acceptance_feeds_repair(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    constraints_path = tmp_path / "constraints.json"
    _write_fd_repairable_csv(csv_path)
    artifact = _fd_artifact(csv_path)
    fd_id = _fd_candidate_id(artifact)
    constraints_path.write_text(dump_constraint_review_artifact(artifact), encoding="utf-8")

    review_result = runner.invoke(
        app,
        ["constraints", "review", str(constraints_path), "--accept", fd_id, "--no-tui"],
        catch_exceptions=False,
    )
    repair_result = runner.invoke(
        app,
        ["repair", str(csv_path), "--constraints", str(constraints_path), "--dry-run", "--json"],
        catch_exceptions=False,
    )

    assert review_result.exit_code == 0
    assert repair_result.exit_code == 0
    payload = json.loads(repair_result.output)
    assert payload["receipt"]["accepted_constraint_ids"] == [fd_id]
    assert payload["fixes"][0]["detector_id"] == "fd_violation"


def test_constraints_review_textual_accepts_selected_candidate(tmp_path: Path) -> None:
    csv_path = tmp_path / "fd.csv"
    _write_fd_repairable_csv(csv_path)
    artifact = _fd_artifact(csv_path)
    first_id = artifact.candidates[0].candidate_id
    review_app = ConstraintReviewApp(artifact)

    async def exercise() -> None:
        async with review_app.run_test() as pilot:
            await pilot.press("a")
            await pilot.press("s")

    asyncio.run(exercise())

    reviewed = {candidate.candidate_id: candidate for candidate in review_app.artifact.candidates}
    assert review_app.saved is True
    assert reviewed[first_id].decision == "accepted"
