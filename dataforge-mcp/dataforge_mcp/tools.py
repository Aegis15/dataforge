"""Structured MCP tool functions backed by DataForge internals."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from dataforge.cli.common import load_schema, read_csv
from dataforge.cli.repair import _apply_transaction, _propose_repairs
from dataforge.detectors import run_all_detectors
from dataforge.detectors.base import Issue, Schema
from dataforge.repairers.base import ProposedFix
from dataforge.safety import SafetyContext, SafetyFilter, SafetyVerdict
from dataforge.transactions.revert import revert_transaction
from dataforge.transactions.txn import CellFix
from dataforge.verifier import SMTVerifier, VerificationVerdict


class IssueResult(BaseModel):
    """MCP-safe representation of a DataForge issue."""

    row: int
    column: str
    issue_type: str
    severity: str
    confidence: float
    expected: str | None
    actual: str
    reason: str


class FixResult(BaseModel):
    """MCP-safe representation of an accepted repair proposal."""

    row: int
    column: str
    old_value: str
    new_value: str
    detector_id: str
    operation: str
    reason: str
    confidence: float
    provenance: str


class ProfileResult(BaseModel):
    """Structured result returned by the profile tool."""

    path: str
    rows: int
    columns: int
    column_names: list[str]
    total_issues: int
    issues: list[IssueResult]


class VerifyFixResult(BaseModel):
    """Structured result returned by the fix verifier tool."""

    accept: bool
    reason: str
    safety_verdict: str | None = None
    verifier_verdict: str | None = None
    unsat_core: list[str] = Field(default_factory=list)


class TxnReceipt(BaseModel):
    """Structured receipt returned by the repair tool."""

    path: str
    mode: Literal["dry_run", "apply"]
    applied: bool
    txn_id: str | None
    issues_count: int
    fixes_count: int
    reason: str
    fixes: list[FixResult]


class RevertReceipt(BaseModel):
    """Structured receipt returned by the revert tool."""

    txn_id: str
    source_path: str
    restored: bool
    reverted_at: str | None
    reason: str


def _resolve_csv_path(path: str) -> Path:
    """Resolve and validate a CSV path supplied by an MCP client."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"CSV file does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"CSV path is not a file: {resolved}")
    return resolved


def _load_optional_schema(raw_path: object) -> Schema | None:
    """Load an optional schema path from an untrusted payload."""
    if raw_path is None:
        return None
    schema_path = Path(str(raw_path)).expanduser().resolve()
    if not schema_path.exists():
        raise ValueError(f"Schema file does not exist: {schema_path}")
    return load_schema(schema_path)


def _issue_to_result(issue: Issue) -> IssueResult:
    """Convert a DataForge issue into a stable MCP payload."""
    return IssueResult(
        row=issue.row,
        column=issue.column,
        issue_type=issue.issue_type,
        severity=issue.severity.value,
        confidence=issue.confidence,
        expected=issue.expected,
        actual=issue.actual,
        reason=issue.reason,
    )


def _fix_to_result(proposed_fix: ProposedFix) -> FixResult:
    """Convert a proposed fix into a stable MCP payload."""
    fix = proposed_fix.fix
    return FixResult(
        row=fix.row,
        column=fix.column,
        old_value=fix.old_value,
        new_value=fix.new_value,
        detector_id=fix.detector_id,
        operation=fix.operation,
        reason=proposed_fix.reason,
        confidence=proposed_fix.confidence,
        provenance=proposed_fix.provenance,
    )


def _run_detection(path: Path, schema: Schema | None = None) -> tuple[Any, list[Issue]]:
    """Read a CSV and run all DataForge detectors."""
    df = read_csv(path)
    return df, run_all_detectors(df, schema)


def _proposed_fix_from_spec(fix_spec: dict[str, Any]) -> tuple[Path, Schema | None, ProposedFix]:
    """Parse a verifier payload into a CSV path, optional schema, and fix."""
    raw_path = fix_spec.get("path")
    if not raw_path:
        raise ValueError("fix_spec must include a CSV 'path'.")
    path = _resolve_csv_path(str(raw_path))
    schema = _load_optional_schema(fix_spec.get("schema_path"))
    raw_fix = fix_spec.get("fix")
    if not isinstance(raw_fix, dict):
        raw_fix = {
            key: value
            for key, value in fix_spec.items()
            if key in {"row", "column", "old_value", "new_value", "detector_id", "operation"}
        }
    cell_fix = CellFix.model_validate(raw_fix)
    proposed = ProposedFix(
        fix=cell_fix,
        reason=str(fix_spec.get("reason", "MCP-provided candidate fix.")),
        confidence=float(fix_spec.get("confidence", 1.0)),
        provenance=fix_spec.get("provenance", "deterministic"),
    )
    return path, schema, proposed


def dataforge_profile(path: str) -> ProfileResult:
    """Profile a CSV file and return detected DataForge issues."""
    csv_path = _resolve_csv_path(path)
    df, issues = _run_detection(csv_path)
    return ProfileResult(
        path=str(csv_path),
        rows=len(df.index),
        columns=len(df.columns),
        column_names=[str(column) for column in df.columns],
        total_issues=len(issues),
        issues=[_issue_to_result(issue) for issue in issues],
    )


def dataforge_detect_errors(path: str) -> list[IssueResult]:
    """Detect data-quality errors in a CSV file."""
    csv_path = _resolve_csv_path(path)
    _df, issues = _run_detection(csv_path)
    return [_issue_to_result(issue) for issue in issues]


def dataforge_verify_fix(fix_spec: dict[str, Any]) -> VerifyFixResult:
    """Verify whether one candidate fix may be accepted by DataForge gates."""
    path, schema, proposed = _proposed_fix_from_spec(fix_spec)
    df = read_csv(path)
    fix = proposed.fix
    if fix.column not in df.columns:
        return VerifyFixResult(accept=False, reason=f"Column '{fix.column}' does not exist.")
    if fix.row < 0 or fix.row >= len(df.index):
        return VerifyFixResult(accept=False, reason=f"Row {fix.row} is out of bounds.")
    current_value = str(df.at[fix.row, fix.column])
    if current_value != fix.old_value:
        return VerifyFixResult(
            accept=False,
            reason=(
                f"Refusing stale fix for row {fix.row}, column '{fix.column}': "
                f"expected '{fix.old_value}', found '{current_value}'."
            ),
        )

    safety_result = SafetyFilter().evaluate(proposed, schema, SafetyContext())
    if safety_result.verdict != SafetyVerdict.ALLOW:
        return VerifyFixResult(
            accept=False,
            reason=safety_result.reason,
            safety_verdict=safety_result.verdict.value,
        )

    verifier_result = SMTVerifier().verify(df, [proposed], schema)
    return VerifyFixResult(
        accept=verifier_result.verdict == VerificationVerdict.ACCEPT,
        reason=verifier_result.reason,
        safety_verdict=safety_result.verdict.value,
        verifier_verdict=verifier_result.verdict.value,
        unsat_core=list(verifier_result.unsat_core),
    )


def dataforge_apply_repairs(path: str, mode: Literal["dry_run", "apply"]) -> TxnReceipt:
    """Detect, verify, and optionally apply DataForge repairs to a CSV file."""
    csv_path = _resolve_csv_path(path)
    if mode not in {"dry_run", "apply"}:
        raise ValueError("mode must be 'dry_run' or 'apply'.")

    df, issues = _run_detection(csv_path)
    accepted_fixes, _attempt_groups = _propose_repairs(
        issues,
        csv_path,
        df.copy(deep=True),
        None,
        allow_llm=False,
        model="gemini-2.0-flash",
        allow_pii=False,
        confirm_pii=False,
        confirm_escalations=False,
        interactive=False,
    )
    batch_safety = SafetyFilter().evaluate_batch(accepted_fixes)
    if batch_safety.verdict != SafetyVerdict.ALLOW:
        return TxnReceipt(
            path=str(csv_path),
            mode=mode,
            applied=False,
            txn_id=None,
            issues_count=len(issues),
            fixes_count=0,
            reason=batch_safety.reason,
            fixes=[],
        )

    if mode == "dry_run" or not accepted_fixes:
        return TxnReceipt(
            path=str(csv_path),
            mode=mode,
            applied=False,
            txn_id=None,
            issues_count=len(issues),
            fixes_count=len(accepted_fixes),
            reason=(
                "Dry run completed without mutating the source file."
                if accepted_fixes
                else "No accepted fixes were produced."
            ),
            fixes=[_fix_to_result(fix) for fix in accepted_fixes],
        )

    txn_id = _apply_transaction(csv_path, accepted_fixes, csv_path.read_bytes())
    return TxnReceipt(
        path=str(csv_path),
        mode=mode,
        applied=True,
        txn_id=txn_id,
        issues_count=len(issues),
        fixes_count=len(accepted_fixes),
        reason=f"Applied {len(accepted_fixes)} fix(es).",
        fixes=[_fix_to_result(fix) for fix in accepted_fixes],
    )


def dataforge_revert(txn_id: str) -> RevertReceipt:
    """Revert a previously applied DataForge repair transaction."""
    transaction = revert_transaction(txn_id)
    return RevertReceipt(
        txn_id=transaction.txn_id,
        source_path=transaction.source_path,
        restored=transaction.reverted_at is not None,
        reverted_at=transaction.reverted_at.isoformat() if transaction.reverted_at else None,
        reason="Source restored successfully.",
    )
