"""Property tests for transaction audit invariants."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from dataforge.transactions.log import TransactionAuditVerdict, verify_transaction_log

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "transactions"
TXN_ID = "txn-2026-04-20-a1b2c3"
GOLDEN_HEAD = "fb0dbe2659a1d24126d87531c64e9a10d2bbbc3106651fe1898495ae490cdc92"


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read JSONL records from ``path``."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """Write JSONL records to ``path``."""
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


@settings(max_examples=10, deadline=None)
@given(_repeat=st.integers(min_value=1, max_value=10))
def test_golden_v2_audit_replay_is_stable(_repeat: int) -> None:
    """The committed v2 fixture always replays to the same verified head."""
    report = verify_transaction_log(
        TXN_ID,
        log_path=FIXTURE_DIR / "v2_created_applied_reverted.jsonl",
    )

    assert report.verdict == TransactionAuditVerdict.VERIFIED
    assert report.head_sha256 == GOLDEN_HEAD


@settings(max_examples=20, deadline=None)
@given(mutation=st.sampled_from(["delete", "duplicate", "reorder", "payload", "hash"]))
def test_golden_v2_audit_fails_after_structural_mutation(mutation: str) -> None:
    """Deletion, duplication, reorder, and payload/hash edits cannot verify."""
    records = _read_jsonl(FIXTURE_DIR / "v2_created_applied_reverted.jsonl")
    if mutation == "delete":
        mutated = records[:-1]
    elif mutation == "duplicate":
        mutated = [records[0], records[1], records[1], records[2]]
    elif mutation == "reorder":
        mutated = [records[0], records[2], records[1]]
    elif mutation == "payload":
        records[1]["post_sha256"] = "0" * 64
        mutated = records
    else:
        records[1]["event_sha256"] = "0" * 64
        mutated = records
    with tempfile.TemporaryDirectory() as temp_dir:
        log_path = Path(temp_dir) / f"{mutation}.jsonl"
        _write_jsonl(log_path, mutated)

        report = verify_transaction_log(TXN_ID, log_path=log_path)

    assert report.verdict != TransactionAuditVerdict.VERIFIED
