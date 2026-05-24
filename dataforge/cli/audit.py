"""CLI subcommand: ``dataforge audit <txn_id>``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from dataforge.transactions import TransactionAuditVerdict, verify_transaction_log

_console = Console(stderr=True)


def audit(
    txn_id: Annotated[
        str,
        typer.Argument(help="Transaction identifier to audit."),
    ],
    search_root: Annotated[
        Path | None,
        typer.Option(
            "--search-root",
            help="Root directory used to locate the transaction log.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ] = None,
    log_path: Annotated[
        Path | None,
        typer.Option(
            "--log-path",
            help="Explicit JSONL transaction log path.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the audit report as JSON."),
    ] = False,
) -> None:
    """Verify a transaction log's local hash chain."""
    report = verify_transaction_log(txn_id, log_path=log_path, search_root=search_root)
    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        style = "green" if report.verdict == TransactionAuditVerdict.VERIFIED else "red"
        body = (
            f"Verdict: [bold]{report.verdict.value}[/bold]\n"
            f"Transaction: {report.txn_id or txn_id}\n"
            f"Events: {report.event_count}\n"
            f"Head SHA-256: {report.head_sha256 or 'n/a'}"
        )
        if report.errors:
            body += "\n\n" + "\n".join(f"- {error}" for error in report.errors)
        _console.print(Panel(body, title="Transaction Audit", style=style))

    if report.verdict == TransactionAuditVerdict.VERIFIED:
        raise typer.Exit(code=0)
    if report.verdict == TransactionAuditVerdict.LEGACY_UNVERIFIED:
        raise typer.Exit(code=1)
    raise typer.Exit(code=2)
