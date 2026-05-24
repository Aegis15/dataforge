"""CLI tests for ``dataforge watch``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from dataforge.cli import app

runner = CliRunner()


def _write_repairable_csv(path: Path) -> None:
    path.write_text(
        "id,amount\n1,100\n2,105\n3,98\n4,1020\n5,103\n",
        encoding="utf-8",
    )


def test_watch_once_profile_json(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_repairable_csv(csv_path)

    result = runner.invoke(app, ["watch", str(csv_path), "--once", "--json"])

    assert result.exit_code == 0
    assert '"event": "profile"' in result.output
    assert '"issues_count": 1' in result.output


def test_watch_once_repair_json_dry_run(tmp_path: Path) -> None:
    csv_path = tmp_path / "data.csv"
    _write_repairable_csv(csv_path)

    result = runner.invoke(
        app,
        ["watch", str(csv_path), "--action", "repair", "--once", "--json"],
    )

    assert result.exit_code == 0
    assert '"event": "repair"' in result.output
    assert '"fixes_count": 1' in result.output
    assert not (tmp_path / ".dataforge").exists()
