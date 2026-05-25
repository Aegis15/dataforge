"""DataForge public package.

The root package is the stable facade for integration surfaces. Symbols are
resolved lazily so importing :mod:`dataforge` does not eagerly import pandas,
FastAPI-facing helpers, or the SMT stack.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dataforge.cli.common import load_schema, read_csv, schema_from_mapping
    from dataforge.detectors import Issue, Schema, Severity, run_all_detectors
    from dataforge.engine.repair import (
        CandidateFix,
        RepairFailure,
        RepairPipelineRequest,
        RepairPipelineResult,
        RepairReceipt,
        VerifiedFix,
        run_repair_pipeline,
    )
    from dataforge.repair_contract import CONTRACT_VERSION
    from dataforge.repairers import ProposedFix
    from dataforge.safety import SafetyContext, SafetyFilter, SafetyResult, SafetyVerdict
    from dataforge.schema_inference import (
        ConstraintCandidate,
        ConstraintReviewArtifact,
        ConstraintReviewError,
        ReviewedConstraintCandidate,
        SchemaInferenceResult,
        build_constraint_review_artifact,
        dump_constraint_review_artifact,
        infer_schema,
        load_constraint_review_artifact,
    )
    from dataforge.transactions.log import (
        TransactionAuditReport,
        TransactionAuditVerdict,
        TransactionLogError,
        verify_transaction_log,
    )
    from dataforge.transactions.revert import TransactionRevertError, revert_transaction
    from dataforge.transactions.txn import CellFix, RepairTransaction
    from dataforge.verifier import SMTVerifier, VerificationResult, VerificationVerdict

__all__ = [
    "CONTRACT_VERSION",
    "CandidateFix",
    "CellFix",
    "ConstraintCandidate",
    "ConstraintReviewArtifact",
    "ConstraintReviewError",
    "Issue",
    "ProposedFix",
    "RepairFailure",
    "RepairPipelineRequest",
    "RepairPipelineResult",
    "RepairReceipt",
    "RepairTransaction",
    "ReviewedConstraintCandidate",
    "SMTVerifier",
    "SafetyContext",
    "SafetyFilter",
    "SafetyResult",
    "SafetyVerdict",
    "Schema",
    "SchemaInferenceResult",
    "Severity",
    "TransactionAuditReport",
    "TransactionAuditVerdict",
    "TransactionLogError",
    "TransactionRevertError",
    "VerificationResult",
    "VerificationVerdict",
    "VerifiedFix",
    "__version__",
    "load_schema",
    "build_constraint_review_artifact",
    "dump_constraint_review_artifact",
    "load_constraint_review_artifact",
    "read_csv",
    "revert_transaction",
    "run_all_detectors",
    "run_repair_pipeline",
    "schema_from_mapping",
    "infer_schema",
    "verify_transaction_log",
]

__version__ = "0.1.0rc1"

_PUBLIC_EXPORTS: dict[str, tuple[str, str]] = {
    "CONTRACT_VERSION": ("dataforge.repair_contract", "CONTRACT_VERSION"),
    "CandidateFix": ("dataforge.engine.repair", "CandidateFix"),
    "CellFix": ("dataforge.transactions.txn", "CellFix"),
    "ConstraintCandidate": ("dataforge.schema_inference", "ConstraintCandidate"),
    "ConstraintReviewArtifact": ("dataforge.schema_inference", "ConstraintReviewArtifact"),
    "ConstraintReviewError": ("dataforge.schema_inference", "ConstraintReviewError"),
    "Issue": ("dataforge.detectors", "Issue"),
    "ProposedFix": ("dataforge.repairers", "ProposedFix"),
    "RepairFailure": ("dataforge.engine.repair", "RepairFailure"),
    "RepairPipelineRequest": ("dataforge.engine.repair", "RepairPipelineRequest"),
    "RepairPipelineResult": ("dataforge.engine.repair", "RepairPipelineResult"),
    "RepairReceipt": ("dataforge.engine.repair", "RepairReceipt"),
    "RepairTransaction": ("dataforge.transactions.txn", "RepairTransaction"),
    "ReviewedConstraintCandidate": ("dataforge.schema_inference", "ReviewedConstraintCandidate"),
    "SMTVerifier": ("dataforge.verifier", "SMTVerifier"),
    "SafetyContext": ("dataforge.safety", "SafetyContext"),
    "SafetyFilter": ("dataforge.safety", "SafetyFilter"),
    "SafetyResult": ("dataforge.safety", "SafetyResult"),
    "SafetyVerdict": ("dataforge.safety", "SafetyVerdict"),
    "Schema": ("dataforge.detectors", "Schema"),
    "SchemaInferenceResult": ("dataforge.schema_inference", "SchemaInferenceResult"),
    "Severity": ("dataforge.detectors", "Severity"),
    "TransactionAuditReport": ("dataforge.transactions.log", "TransactionAuditReport"),
    "TransactionAuditVerdict": ("dataforge.transactions.log", "TransactionAuditVerdict"),
    "TransactionLogError": ("dataforge.transactions.log", "TransactionLogError"),
    "TransactionRevertError": ("dataforge.transactions.revert", "TransactionRevertError"),
    "VerificationResult": ("dataforge.verifier", "VerificationResult"),
    "VerificationVerdict": ("dataforge.verifier", "VerificationVerdict"),
    "VerifiedFix": ("dataforge.engine.repair", "VerifiedFix"),
    "load_schema": ("dataforge.cli.common", "load_schema"),
    "build_constraint_review_artifact": (
        "dataforge.schema_inference",
        "build_constraint_review_artifact",
    ),
    "dump_constraint_review_artifact": (
        "dataforge.schema_inference",
        "dump_constraint_review_artifact",
    ),
    "load_constraint_review_artifact": (
        "dataforge.schema_inference",
        "load_constraint_review_artifact",
    ),
    "read_csv": ("dataforge.cli.common", "read_csv"),
    "revert_transaction": ("dataforge.transactions.revert", "revert_transaction"),
    "run_all_detectors": ("dataforge.detectors", "run_all_detectors"),
    "run_repair_pipeline": ("dataforge.engine.repair", "run_repair_pipeline"),
    "schema_from_mapping": ("dataforge.cli.common", "schema_from_mapping"),
    "infer_schema": ("dataforge.schema_inference", "infer_schema"),
    "verify_transaction_log": ("dataforge.transactions.log", "verify_transaction_log"),
}


def __getattr__(name: str) -> Any:
    """Resolve public facade exports on first use."""
    try:
        module_name, attribute_name = _PUBLIC_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
