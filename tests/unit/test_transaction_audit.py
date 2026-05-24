"""Transaction hash-chain audit tests."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dataforge.cli import app
from dataforge.transactions.log import (
    TransactionAuditVerdict,
    append_applied_event,
    append_created_transaction,
    append_reverted_event,
    load_transaction,
    transaction_log_path_for,
    verify_transaction_log,
)
from dataforge.transactions.revert import TransactionRevertError, revert_transaction
from dataforge.transactions.txn import CellFix, RepairTransaction

runner = CliRunner()


def _sha256_bytes(payload: bytes) -> str:
    """Return the SHA-256 digest for bytes."""
    return hashlib.sha256(payload).hexdigest()


def _transaction(source_path: Path, snapshot_path: Path, source_bytes: bytes) -> RepairTransaction:
    """Build a sample transaction rooted at ``source_path``."""
    return RepairTransaction(
        txn_id="txn-2026-04-20-a1b2c3",
        created_at=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        source_path=str(source_path.resolve()),
        source_sha256=_sha256_bytes(source_bytes),
        source_snapshot_path=str(snapshot_path.resolve()),
        fixes=[
            CellFix(
                row=1,
                column="amount",
                old_value="1020",
                new_value="102",
                detector_id="decimal_shift",
            )
        ],
        applied=False,
    )


def _write_v2_log(tmp_path: Path) -> tuple[Path, RepairTransaction]:
    """Write a valid v2 created/applied/reverted log."""
    source_path = tmp_path / "data.csv"
    snapshot_path = tmp_path / ".dataforge" / "snapshots" / "txn.bin"
    source_bytes = b"id,amount\n1,100\n2,1020\n"
    post_bytes = b"id,amount\n1,100\n2,102\n"
    source_path.write_bytes(source_bytes)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(source_bytes)
    transaction = _transaction(source_path, snapshot_path, source_bytes)
    log_path = append_created_transaction(transaction)
    append_applied_event(
        log_path,
        transaction.txn_id,
        post_sha256=_sha256_bytes(post_bytes),
        applied_at=datetime(2026, 4, 20, 12, 1, tzinfo=UTC),
    )
    append_reverted_event(
        log_path,
        transaction.txn_id,
        reverted_at=datetime(2026, 4, 20, 12, 2, tzinfo=UTC),
    )
    return log_path, transaction


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    """Read JSONL records from ``path``."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """Write JSONL records to ``path``."""
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def test_v2_transaction_log_has_verified_hash_chain(tmp_path: Path) -> None:
    log_path, transaction = _write_v2_log(tmp_path)
    records = _read_jsonl(log_path)

    assert [record["schema_version"] for record in records] == [2, 2, 2]
    assert [record["event_index"] for record in records] == [0, 1, 2]
    assert records[0]["previous_event_sha256"] is None
    assert records[1]["previous_event_sha256"] == records[0]["event_sha256"]
    assert records[2]["previous_event_sha256"] == records[1]["event_sha256"]

    report = verify_transaction_log(transaction.txn_id, log_path=log_path)

    assert report.verdict == TransactionAuditVerdict.VERIFIED
    assert report.txn_id == transaction.txn_id
    assert report.event_count == 3
    assert report.head_sha256 == records[-1]["event_sha256"]


@pytest.mark.parametrize(
    "mutation",
    [
        "payload",
        "previous_hash",
        "event_index",
    ],
)
def test_v2_transaction_log_tampering_is_reported(tmp_path: Path, mutation: str) -> None:
    log_path, transaction = _write_v2_log(tmp_path)
    records = _read_jsonl(log_path)
    if mutation == "payload":
        created = records[0]["transaction"]
        assert isinstance(created, dict)
        created["source_sha256"] = "0" * 64
    elif mutation == "previous_hash":
        records[1]["previous_event_sha256"] = "0" * 64
    else:
        records[1]["event_index"] = 9
    _write_jsonl(log_path, records)

    report = verify_transaction_log(transaction.txn_id, log_path=log_path)

    assert report.verdict == TransactionAuditVerdict.TAMPERED
    assert report.errors


def test_missing_transaction_log_reports_missing(tmp_path: Path) -> None:
    report = verify_transaction_log("txn-2026-04-20-ffffff", search_root=tmp_path)

    assert report.verdict == TransactionAuditVerdict.MISSING
    assert report.event_count == 0


def test_legacy_v1_log_replays_but_is_not_cryptographically_verified(tmp_path: Path) -> None:
    source_path = tmp_path / "data.csv"
    snapshot_path = tmp_path / ".dataforge" / "snapshots" / "txn.bin"
    source_bytes = b"id,amount\n1,100\n"
    source_path.write_bytes(source_bytes)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(source_bytes)
    transaction = _transaction(source_path, snapshot_path, source_bytes)
    log_path = transaction_log_path_for(source_path, transaction.txn_id)
    log_path.parent.mkdir(parents=True)
    post_sha256 = _sha256_bytes(b"id,amount\n1,101\n")
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_type": "created",
                "occurred_at": transaction.created_at.isoformat(),
                "transaction": transaction.model_dump(mode="json"),
            },
            sort_keys=True,
        )
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "event_type": "applied",
                "occurred_at": "2026-04-20T12:01:00+00:00",
                "txn_id": transaction.txn_id,
                "post_sha256": post_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = verify_transaction_log(transaction.txn_id, log_path=log_path)
    replayed = load_transaction(log_path)

    assert report.verdict == TransactionAuditVerdict.LEGACY_UNVERIFIED
    assert replayed.applied is True
    assert replayed.post_sha256 == post_sha256


def test_audit_cli_reports_verified_json(tmp_path: Path) -> None:
    _log_path, transaction = _write_v2_log(tmp_path)

    result = runner.invoke(
        app,
        ["audit", transaction.txn_id, "--search-root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["verdict"] == "verified"
    assert payload["txn_id"] == transaction.txn_id


def test_audit_cli_rejects_legacy_unverified_log(tmp_path: Path) -> None:
    source_path = tmp_path / "data.csv"
    snapshot_path = tmp_path / ".dataforge" / "snapshots" / "txn.bin"
    source_bytes = b"id,amount\n1,100\n"
    source_path.write_bytes(source_bytes)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(source_bytes)
    transaction = _transaction(source_path, snapshot_path, source_bytes)
    log_path = transaction_log_path_for(source_path, transaction.txn_id)
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_type": "created",
                "occurred_at": transaction.created_at.isoformat(),
                "transaction": transaction.model_dump(mode="json"),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["audit", transaction.txn_id, "--search-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "legacy_unverified" in result.output


def test_revert_refuses_tampered_v2_log_before_mutating_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "data.csv"
    snapshot_path = tmp_path / ".dataforge" / "snapshots" / "txn.bin"
    source_bytes = b"id,amount\n1,100\n2,1020\n"
    post_bytes = b"id,amount\n1,100\n2,102\n"
    source_path.write_bytes(source_bytes)
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_bytes(source_bytes)
    transaction = _transaction(source_path, snapshot_path, source_bytes)
    log_path = append_created_transaction(transaction)
    source_path.write_bytes(post_bytes)
    append_applied_event(log_path, transaction.txn_id, post_sha256=_sha256_bytes(post_bytes))
    records = _read_jsonl(log_path)
    records[1]["post_sha256"] = "0" * 64
    _write_jsonl(log_path, records)

    with pytest.raises(TransactionRevertError, match="audit verification failed"):
        revert_transaction(transaction.txn_id, search_root=tmp_path)

    assert source_path.read_bytes() == post_bytes
