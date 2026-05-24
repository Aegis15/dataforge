"""Public repair engine for DataForge backend surfaces.

The engine is the stable boundary shared by CLI, Playground, MCP, and any
OpenEnv adapter that needs repair semantics. It keeps the core invariant in one
place: detect -> propose -> safety -> SMT verification -> journal/snapshot ->
atomic mutation -> byte-identical revert.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from dataforge.detectors import run_all_detectors
from dataforge.detectors.base import Issue, Schema
from dataforge.observability import repair_stage_span
from dataforge.repair_contract import CONTRACT_VERSION
from dataforge.repairers import build_repairers
from dataforge.repairers.base import ProposedFix, RepairAttempt, RetryContext
from dataforge.safety import SafetyContext, SafetyFilter, SafetyResult, SafetyVerdict
from dataforge.schema_inference import (
    ConstraintReviewArtifact,
    merge_schema_with_reviewed_constraints,
)
from dataforge.table import (
    Table,
    TableLike,
    cell_value,
    column_names,
    copy_table,
    row_count,
    set_cell_value,
    table_to_csv_bytes,
)
from dataforge.table import (
    read_csv as read_table_csv,
)
from dataforge.transactions.files import (
    SourceLockError,
    atomic_write_bytes,
    lock_path_for,
)
from dataforge.transactions.files import (
    source_path_lock as transaction_source_path_lock,
)
from dataforge.transactions.log import (
    append_applied_event,
    append_created_transaction,
    cache_dir_for,
    sha256_bytes,
    sha256_file,
    snapshot_path_for,
)
from dataforge.transactions.txn import CellFix, RepairTransaction, generate_txn_id
from dataforge.verifier import SMTVerifier, VerificationVerdict

RepairMode = Literal["dry_run", "apply"]
EscalationResolver = Callable[
    [ProposedFix, Schema | None, SafetyContext, SafetyFilter, SafetyResult],
    tuple[SafetyContext, SafetyResult],
]


class RepairEngineError(RuntimeError):
    """Base exception for public repair engine failures."""


class TransactionApplyError(RepairEngineError):
    """Raised when an apply transaction cannot be completed safely."""


class CandidateFix(BaseModel):
    """Stable public representation of a proposed cell repair."""

    row: int = Field(ge=0)
    column: str = Field(min_length=1)
    old_value: str
    new_value: str
    detector_id: str = Field(min_length=1)
    operation: Literal["update", "delete_row"] = "update"
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str = Field(min_length=1)

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    @classmethod
    def from_proposed(cls, proposed_fix: ProposedFix) -> CandidateFix:
        """Create a public candidate from an internal repair proposal."""
        fix = proposed_fix.fix
        return cls(
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


class VerifiedFix(CandidateFix):
    """A candidate that passed safety and SMT verification."""

    verifier_reason: str = Field(min_length=1)


class RepairFailure(BaseModel):
    """Machine-readable account of an issue that could not be repaired."""

    row: int = Field(ge=0)
    column: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    status: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    attempt_count: int = Field(ge=1)
    unsat_core: tuple[str, ...] = Field(default_factory=tuple)

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    @classmethod
    def from_attempts(cls, attempts: list[RepairAttempt]) -> RepairFailure:
        """Build a public failure record from one issue's attempt trace."""
        final = attempts[-1]
        issue = final.issue
        return cls(
            row=issue.row,
            column=issue.column,
            issue_type=issue.issue_type,
            status=final.status,
            reason=final.reason,
            attempt_count=len(attempts),
            unsat_core=tuple(final.unsat_core),
        )


class RepairReceipt(BaseModel):
    """Stable receipt for a dry-run or applied repair pipeline run."""

    schema_version: Literal["repair_receipt_v1"] = "repair_receipt_v1"
    contract_version: str = CONTRACT_VERSION
    mode: RepairMode
    applied: bool
    reversible: bool
    source_path: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    post_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    txn_id: str | None = None
    allowed_columns: list[str] = Field(default_factory=list)
    valid_rows: list[int] = Field(default_factory=list)
    safety_verdict: str = Field(default="allow", min_length=1)
    verifier_verdict: str = Field(default="not_run", min_length=1)
    candidate_provenance: list[str] = Field(default_factory=list)
    accepted_constraint_ids: list[str] = Field(default_factory=list)
    constraints_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    abstentions: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)
    issues_count: int = Field(ge=0)
    fixes_count: int = Field(ge=0)
    reason: str = Field(min_length=1)

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class RepairPipelineRequest(BaseModel):
    """Input contract for running the public repair pipeline."""

    source_path: Path
    mode: RepairMode = "dry_run"
    repair_schema: Schema | None = Field(default=None, alias="schema")
    allow_llm: bool = False
    model: str = "gemini-2.0-flash"
    allow_pii: bool = False
    confirm_pii: bool = False
    confirm_escalations: bool = False
    interactive: bool = False
    create_dry_run_transaction: bool = False
    constraints: ConstraintReviewArtifact | None = None
    constraints_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(
        strict=True,
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class RepairPipelineResult(BaseModel):
    """Output contract for a public repair pipeline run."""

    receipt: RepairReceipt
    issues: list[Issue]
    fixes: list[VerifiedFix]
    failures: list[RepairFailure] = Field(default_factory=list)
    transaction: RepairTransaction | None = None

    model_config = ConfigDict(
        strict=True, arbitrary_types_allowed=True, extra="forbid", frozen=True
    )


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write bytes to ``path`` through an atomic same-directory replacement."""
    atomic_write_bytes(path, payload)


def read_csv(path: Path) -> Table:
    """Read a CSV using conservative string-preserving defaults."""
    return read_table_csv(path)


def _csv_bytes_after_fixes(path: Path, fixes: list[CellFix]) -> bytes:
    """Validate fixes against a CSV and return the mutated CSV bytes."""
    df = read_csv(path)
    for fix in fixes:
        if fix.operation != "update":
            raise ValueError(f"Unsupported repair operation '{fix.operation}' for row {fix.row}.")
        if fix.column not in column_names(df):
            raise ValueError(f"Column '{fix.column}' not found in '{path}'.")
        if fix.row < 0 or fix.row >= row_count(df):
            raise ValueError(f"Row {fix.row} is out of bounds for '{path}'.")

        current_value = cell_value(df, fix.row, fix.column)
        if current_value != fix.old_value:
            raise ValueError(
                f"Refusing to apply stale fix for row {fix.row}, column '{fix.column}': "
                f"expected '{fix.old_value}', found '{current_value}'."
            )
        set_cell_value(df, fix.row, fix.column, fix.new_value)

    return table_to_csv_bytes(df)


def apply_fixes_to_csv(path: Path, fixes: list[CellFix]) -> str:
    """Atomically apply ordered cell fixes to a CSV and return post-state SHA-256."""
    payload = _csv_bytes_after_fixes(path, fixes)
    _atomic_write_bytes(path, payload)
    return hashlib.sha256(payload).hexdigest()


def _lock_path_for(source_path: Path) -> Path:
    """Return the filesystem lock path for a source file."""
    return lock_path_for(source_path)


@contextmanager
def source_path_lock(
    source_path: Path,
    *,
    timeout_seconds: float = 5.0,
    stale_after_seconds: float = 300.0,
) -> Iterator[None]:
    """Acquire an exclusive lock for a source path using an atomic lock file."""
    try:
        with transaction_source_path_lock(
            source_path,
            timeout_seconds=timeout_seconds,
            stale_after_seconds=stale_after_seconds,
        ):
            yield
    except SourceLockError as exc:
        raise TransactionApplyError(str(exc)) from exc


def _write_snapshot_once(snapshot_path: Path, source_bytes: bytes) -> None:
    """Write an immutable snapshot and fail if the transaction id already exists."""
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with snapshot_path.open("xb") as handle:
            handle.write(source_bytes)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise TransactionApplyError(
            f"Transaction snapshot already exists: {snapshot_path}"
        ) from exc


def create_repair_transaction(
    path: Path,
    fixes: list[ProposedFix],
    source_bytes: bytes,
    *,
    txn_id: str | None = None,
) -> tuple[RepairTransaction, Path]:
    """Create an unapplied transaction journal and immutable source snapshot."""
    resolved_path = path.resolve()
    transaction_id = txn_id or generate_txn_id()
    snapshot_path = snapshot_path_for(resolved_path, transaction_id)
    _write_snapshot_once(snapshot_path, source_bytes)

    transaction = RepairTransaction(
        txn_id=transaction_id,
        created_at=datetime.now(UTC),
        source_path=str(resolved_path),
        source_sha256=sha256_bytes(source_bytes),
        source_snapshot_path=str(snapshot_path.resolve()),
        fixes=[proposal.fix for proposal in fixes],
        applied=False,
    )
    try:
        log_path = append_created_transaction(transaction)
    except Exception:
        snapshot_path.unlink(missing_ok=True)
        raise
    return transaction, log_path


def apply_transaction(
    path: Path,
    fixes: list[ProposedFix],
    source_bytes: bytes,
    *,
    txn_id: str | None = None,
) -> str:
    """Journal, snapshot, atomically apply fixes, and restore bytes on failure."""
    resolved_path = path.resolve()
    with source_path_lock(resolved_path):
        current_bytes = resolved_path.read_bytes()
        if current_bytes != source_bytes:
            raise TransactionApplyError(
                "Refusing to apply repairs because the source file changed after detection."
            )

        with repair_stage_span("dataforge.repair.transaction.create", fixes_count=len(fixes)):
            transaction, log_path = create_repair_transaction(
                resolved_path,
                fixes,
                source_bytes,
                txn_id=txn_id,
            )
        try:
            with repair_stage_span("dataforge.repair.transaction.apply", fixes_count=len(fixes)):
                post_sha256 = apply_fixes_to_csv(
                    resolved_path,
                    [proposal.fix for proposal in fixes],
                )
                append_applied_event(log_path, transaction.txn_id, post_sha256=post_sha256)
        except Exception as exc:
            _atomic_write_bytes(resolved_path, source_bytes)
            if sha256_file(resolved_path) != transaction.source_sha256:
                raise TransactionApplyError(
                    "Apply failed and the source file could not be restored to original bytes."
                ) from exc
            raise

    return transaction.txn_id


def _build_retry_context(issue: Issue, attempts: list[RepairAttempt]) -> RetryContext:
    """Build retry hints from previous failed attempts."""
    rejected_values = frozenset(
        attempt.fix.fix.new_value
        for attempt in attempts
        if attempt.fix is not None and attempt.status in {"denied", "rejected", "unknown"}
    )
    hints: list[str] = []
    for attempt in attempts:
        hints.append(attempt.reason)
        hints.extend(attempt.unsat_core)
    return RetryContext(
        issue=issue,
        previous_attempts=tuple(attempts),
        rejected_values=rejected_values,
        hints=tuple(hints),
    )


def propose_repairs(
    issues: list[Issue],
    path: Path,
    working_df: TableLike,
    schema: Schema | None,
    *,
    allow_llm: bool,
    model: str,
    allow_pii: bool,
    confirm_pii: bool,
    confirm_escalations: bool,
    interactive: bool,
    escalation_resolver: EscalationResolver | None = None,
) -> tuple[list[ProposedFix], list[list[RepairAttempt]]]:
    """Run repairers and gates issue-by-issue against a working dataframe."""
    with repair_stage_span("dataforge.repair.repairers.build", allow_llm=allow_llm):
        repairers = build_repairers(
            cache_dir=cache_dir_for(path),
            allow_llm=allow_llm,
            model=model,
        )
    safety_filter = SafetyFilter()
    verifier = SMTVerifier()
    safety_context = SafetyContext(
        allow_pii=allow_pii,
        confirm_pii=confirm_pii,
        confirm_escalations=confirm_escalations,
    )

    accepted_fixes: list[ProposedFix] = []
    attempt_groups: list[list[RepairAttempt]] = []

    for issue in issues:
        attempts: list[RepairAttempt] = []
        repairer = repairers.get(issue.issue_type)
        if repairer is None:
            attempts.append(
                RepairAttempt(
                    issue=issue,
                    attempt_number=1,
                    status="attempted_not_fixed",
                    reason="No repairer is registered for this issue type.",
                )
            )
            attempt_groups.append(attempts)
            continue

        accepted = False
        retry_context = RetryContext(issue=issue)
        for attempt_number in range(1, 4):
            candidate = repairer.propose(issue, working_df, schema, retry_context=retry_context)
            if candidate is None:
                attempts.append(
                    RepairAttempt(
                        issue=issue,
                        attempt_number=attempt_number,
                        status="attempted_not_fixed",
                        reason="No repair proposal was available for this issue.",
                    )
                )
                break

            preferred = safety_filter.choose_preferred([candidate], schema, safety_context)
            safety_result = safety_filter.evaluate(preferred, schema, safety_context)
            if (
                safety_result.verdict == SafetyVerdict.ESCALATE
                and interactive
                and escalation_resolver is not None
            ):
                safety_context, safety_result = escalation_resolver(
                    preferred,
                    schema,
                    safety_context,
                    safety_filter,
                    safety_result,
                )

            if safety_result.verdict == SafetyVerdict.DENY:
                attempts.append(
                    RepairAttempt(
                        issue=issue,
                        attempt_number=attempt_number,
                        fix=preferred,
                        status="denied",
                        reason=safety_result.reason,
                    )
                )
                retry_context = _build_retry_context(issue, attempts)
                continue

            if safety_result.verdict == SafetyVerdict.ESCALATE:
                attempts.append(
                    RepairAttempt(
                        issue=issue,
                        attempt_number=attempt_number,
                        fix=preferred,
                        status="escalated",
                        reason=safety_result.reason,
                    )
                )
                break

            with repair_stage_span(
                "dataforge.repair.verifier.verify",
                issue_type=issue.issue_type,
                row=issue.row,
            ):
                verifier_result = verifier.verify(working_df, [preferred], schema)
            if verifier_result.verdict == VerificationVerdict.ACCEPT:
                accepted_fixes.append(preferred)
                set_cell_value(
                    working_df,
                    preferred.fix.row,
                    preferred.fix.column,
                    preferred.fix.new_value,
                )
                attempts.append(
                    RepairAttempt(
                        issue=issue,
                        attempt_number=attempt_number,
                        fix=preferred,
                        status="accepted",
                        reason=verifier_result.reason,
                    )
                )
                accepted = True
                break

            attempts.append(
                RepairAttempt(
                    issue=issue,
                    attempt_number=attempt_number,
                    fix=preferred,
                    status=(
                        "rejected"
                        if verifier_result.verdict == VerificationVerdict.REJECT
                        else "unknown"
                    ),
                    reason=verifier_result.reason,
                    unsat_core=verifier_result.unsat_core,
                )
            )
            retry_context = _build_retry_context(issue, attempts)

        if (
            not accepted
            and attempts
            and attempts[-1].status not in {"attempted_not_fixed", "escalated"}
        ):
            last_reason = attempts[-1].reason
            attempts[-1] = attempts[-1].model_copy(
                update={
                    "status": "attempted_not_fixed",
                    "reason": (
                        f"Issue was attempted but not fixed after {len(attempts)} attempt(s). "
                        f"Last failure: {last_reason}"
                    ),
                }
            )
        attempt_groups.append(attempts)

    return accepted_fixes, attempt_groups


def _verified_fixes(
    fixes: list[ProposedFix],
    attempt_groups: list[list[RepairAttempt]],
) -> list[VerifiedFix]:
    """Build public verified fix payloads using accepted attempt reasons."""
    accepted_reasons: dict[tuple[int, str, str], str] = {}
    for attempts in attempt_groups:
        for attempt in attempts:
            if attempt.status == "accepted" and attempt.fix is not None:
                fix = attempt.fix.fix
                accepted_reasons[(fix.row, fix.column, fix.new_value)] = attempt.reason

    return [
        VerifiedFix(
            **CandidateFix.from_proposed(fix).model_dump(),
            verifier_reason=accepted_reasons.get(
                (fix.fix.row, fix.fix.column, fix.fix.new_value),
                "Accepted by verifier.",
            ),
        )
        for fix in fixes
    ]


def _failed_attempts(attempt_groups: list[list[RepairAttempt]]) -> list[RepairFailure]:
    """Return failures for issue groups whose final status was not accepted."""
    return [
        RepairFailure.from_attempts(attempts)
        for attempts in attempt_groups
        if attempts and attempts[-1].status != "accepted"
    ]


def _receipt_verifier_verdict(
    fixes: list[ProposedFix],
    failures: list[RepairFailure],
) -> str:
    """Summarize verifier outcomes for the public repair receipt."""
    statuses = {failure.status for failure in failures}
    if "unknown" in statuses:
        return "unknown"
    if "rejected" in statuses:
        return "reject"
    if fixes:
        return "accept"
    return "not_run"


def run_repair_pipeline(request: RepairPipelineRequest) -> RepairPipelineResult:
    """Run the public repair pipeline from detection through optional apply."""
    source_path = request.source_path.resolve()
    source_bytes = source_path.read_bytes()
    source_sha256 = sha256_bytes(source_bytes)
    effective_schema, accepted_constraint_ids = merge_schema_with_reviewed_constraints(
        request.repair_schema,
        request.constraints,
        source_sha256=source_sha256,
    )
    df = read_csv(source_path)
    with repair_stage_span("dataforge.repair.detect", row_count=row_count(df)):
        issues = run_all_detectors(df, effective_schema)
    with repair_stage_span("dataforge.repair.propose", issue_count=len(issues)):
        accepted_fixes, attempt_groups = propose_repairs(
            issues,
            source_path,
            copy_table(df),
            effective_schema,
            allow_llm=request.allow_llm,
            model=request.model,
            allow_pii=request.allow_pii,
            confirm_pii=request.confirm_pii,
            confirm_escalations=request.confirm_escalations,
            interactive=request.interactive,
        )

    with repair_stage_span("dataforge.repair.safety.batch", fixes_count=len(accepted_fixes)):
        batch_safety = SafetyFilter().evaluate_batch(accepted_fixes)
    failures = _failed_attempts(attempt_groups)
    transaction: RepairTransaction | None = None
    txn_id: str | None = None
    post_sha256: str | None = None
    applied = False
    reason = "No accepted fixes were produced."

    if batch_safety.verdict != SafetyVerdict.ALLOW:
        accepted_fixes = []
        reason = batch_safety.reason
    elif request.mode == "apply" and accepted_fixes:
        txn_id = apply_transaction(source_path, accepted_fixes, source_bytes)
        post_sha256 = sha256_file(source_path)
        applied = True
        reason = f"Applied {len(accepted_fixes)} fix(es)."
    elif request.create_dry_run_transaction:
        transaction, _log_path = create_repair_transaction(
            source_path, accepted_fixes, source_bytes
        )
        txn_id = transaction.txn_id
        reason = (
            "Dry run completed without mutating the source file."
            if accepted_fixes
            else "No accepted fixes were produced."
        )
    elif accepted_fixes:
        reason = "Dry run completed without mutating the source file."

    if txn_id is not None and transaction is None:
        # Replaying the log is unnecessary for the public contract here; this
        # minimal receipt is intentionally enough for API callers.
        transaction = None

    receipt = RepairReceipt(
        mode=request.mode,
        applied=applied,
        reversible=True,
        source_path=str(source_path),
        source_sha256=source_sha256,
        post_sha256=post_sha256,
        txn_id=txn_id,
        allowed_columns=column_names(df),
        valid_rows=list(range(row_count(df))),
        safety_verdict=batch_safety.verdict.value,
        verifier_verdict=_receipt_verifier_verdict(accepted_fixes, failures),
        candidate_provenance=sorted({fix.provenance for fix in accepted_fixes}),
        accepted_constraint_ids=accepted_constraint_ids,
        constraints_artifact_sha256=request.constraints_artifact_sha256,
        abstentions=[failure.reason for failure in failures],
        failure_reasons=[failure.reason for failure in failures],
        issues_count=len(issues),
        fixes_count=len(accepted_fixes),
        reason=reason,
    )
    return RepairPipelineResult(
        receipt=receipt,
        issues=issues,
        fixes=_verified_fixes(accepted_fixes, attempt_groups),
        failures=failures,
        transaction=transaction,
    )
