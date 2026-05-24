"""Rich rendering for repair proposals and transaction output."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


@dataclass(frozen=True)
class _RepairDiffRow:
    row: int
    column: str
    old_value: str
    new_value: str
    detector_id: str
    confidence: float
    provenance: str


def _row_from_fix(fix: object) -> _RepairDiffRow:
    """Normalize internal ProposedFix and public VerifiedFix objects."""
    nested = getattr(fix, "fix", None)
    if nested is None:
        public = cast(Any, fix)
        return _RepairDiffRow(
            row=public.row,
            column=public.column,
            old_value=public.old_value,
            new_value=public.new_value,
            detector_id=public.detector_id,
            confidence=public.confidence,
            provenance=public.provenance,
        )
    proposed = cast(Any, fix)
    return _RepairDiffRow(
        row=nested.row,
        column=nested.column,
        old_value=nested.old_value,
        new_value=nested.new_value,
        detector_id=nested.detector_id,
        confidence=proposed.confidence,
        provenance=proposed.provenance,
    )


def render_repair_diff(
    fixes: Sequence[object],
    console: Console | None = None,
    *,
    file_path: str = "",
) -> None:
    """Render a rich table describing proposed repairs."""
    target_console = console or Console()
    title = "Proposed Repairs"
    if file_path:
        title = f"{title}  |  {file_path}"
    target_console.print(Panel(title, style="bold cyan", expand=True))

    if not fixes:
        target_console.print(
            Panel("[yellow]No fixes proposed.[/yellow]", title="Result", style="yellow")
        )
        return

    table = Table(title="Repair Diff", show_lines=True, header_style="bold magenta")
    table.add_column("Row", justify="right", width=5)
    table.add_column("Column", style="cyan", min_width=12)
    table.add_column("Old", min_width=12)
    table.add_column("New", min_width=12)
    table.add_column("Detector", min_width=14)
    table.add_column("Confidence", justify="right", min_width=10)
    table.add_column("Provenance", min_width=13)

    for fix in fixes:
        row = _row_from_fix(fix)
        table.add_row(
            str(row.row),
            row.column,
            row.old_value,
            row.new_value,
            row.detector_id,
            f"{row.confidence:.0%}",
            row.provenance,
        )

    target_console.print(table)
