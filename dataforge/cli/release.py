"""CLI group for local release verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from dataforge.release.doctor import DEFAULT_KAGGLE_CREDENTIALS, run_doctor

release_app = typer.Typer(help="Release verification utilities.", no_args_is_help=True)


@release_app.command(name="doctor")
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
    core: Annotated[
        bool,
        typer.Option("--core", help="Run OSS core release checks."),
    ] = False,
    maintainer_deploy: Annotated[
        bool,
        typer.Option(
            "--maintainer-deploy",
            help="Run maintainer-specific deploy/auth checks.",
        ),
    ] = False,
    kaggle_credentials: Annotated[
        Path,
        typer.Option(
            "--kaggle-credentials",
            help="Path to Kaggle OAuth credentials.json. Legacy kaggle.json is never read.",
        ),
    ] = DEFAULT_KAGGLE_CREDENTIALS,
) -> None:
    """Verify local release/deploy auth without printing secrets."""
    run_core = core or not maintainer_deploy
    report = run_doctor(
        kaggle_credentials=kaggle_credentials,
        core=run_core,
        maintainer_deploy=maintainer_deploy,
    )
    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for check in report.checks:
            status = "ok" if check.ok else "fail"
            typer.echo(f"{status:4} {check.name}: {check.detail}")
    raise typer.Exit(code=0 if report.ok else 2)
