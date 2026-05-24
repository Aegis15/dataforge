"""CLI subcommand: ``dataforge watch``."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console
from rich.panel import Panel

from dataforge.cli.common import load_schema, read_csv, resolve_cli_path
from dataforge.detectors import run_all_detectors
from dataforge.detectors.base import Schema
from dataforge.ui.profile_view import render_profile_table
from dataforge.ui.repair_diff import render_repair_diff

_console = Console(stderr=True)

WatchAction = Literal["profile", "repair"]


def _load_optional_schema(schema_path: Path | None) -> Schema | None:
    if schema_path is None:
        return None
    resolved_schema = resolve_cli_path(schema_path)
    if not resolved_schema.exists():
        raise typer.BadParameter(f"Schema file '{schema_path}' does not exist.")
    return load_schema(resolved_schema)


def _profile_once(path: Path, schema: Schema | None, json_output: bool) -> None:
    df = read_csv(path)
    issues = run_all_detectors(df, schema)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "event": "profile",
                    "path": str(path),
                    "issues_count": len(issues),
                    "issues": [issue.model_dump(mode="json") for issue in issues],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return
    render_profile_table(issues, Console(), file_path=str(path))


def _repair_once(path: Path, schema: Schema | None, apply: bool, json_output: bool) -> None:
    from dataforge.engine.repair import RepairPipelineRequest, run_repair_pipeline

    result = run_repair_pipeline(
        RepairPipelineRequest(
            source_path=path,
            mode="apply" if apply else "dry_run",
            schema=schema,
            interactive=False,
        )
    )
    if json_output:
        payload = result.model_dump(mode="json")
        payload["event"] = "repair"
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    render_repair_diff(result.fixes, Console(), file_path=str(path))


def _run_once(
    path: Path, schema: Schema | None, action: WatchAction, apply: bool, json: bool
) -> None:
    if action == "repair":
        _repair_once(path, schema, apply, json)
    else:
        _profile_once(path, schema, json)


def watch(
    path: Annotated[
        Path,
        typer.Argument(help="CSV or dbt artifact path to watch."),
    ],
    schema: Annotated[
        Path | None,
        typer.Option("--schema", help="Path to a YAML schema file with column types and FDs."),
    ] = None,
    action: Annotated[
        WatchAction,
        typer.Option("--action", help="Action to run when the file changes: profile or repair."),
    ] = "profile",
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply repairs on change. Defaults to dry-run repair."),
    ] = False,
    interval: Annotated[
        float,
        typer.Option("--interval", min=0.1, help="Polling interval in seconds."),
    ] = 2.0,
    once: Annotated[
        bool,
        typer.Option("--once", help="Run once and exit, useful for CI acceptance."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print watch events as JSON."),
    ] = False,
) -> None:
    """Poll a path and rerun profile or repair when it changes."""
    resolved_path = resolve_cli_path(path)
    if not resolved_path.exists():
        _console.print(f"[bold red]Watch path not found:[/bold red] {path}")
        raise typer.Exit(code=2)
    parsed_schema = _load_optional_schema(schema)

    if apply and action != "repair":
        _console.print(
            Panel(
                "--apply is only valid with --action repair.",
                title="Watch Error",
                style="red",
            )
        )
        raise typer.Exit(code=2)

    _run_once(resolved_path, parsed_schema, action, apply, json_output)
    if once:
        return

    last_mtime = resolved_path.stat().st_mtime_ns
    while True:
        time.sleep(interval)
        try:
            current_mtime = resolved_path.stat().st_mtime_ns
        except FileNotFoundError:
            _console.print(f"[bold red]Watch path disappeared:[/bold red] {resolved_path}")
            raise typer.Exit(code=2) from None
        if current_mtime == last_mtime:
            continue
        last_mtime = current_mtime
        _run_once(resolved_path, parsed_schema, action, apply, json_output)
