"""Playground API smoke tests.

Tests the FastAPI playground backend using TestClient. These tests exercise
the contract defined in specs/SPEC_playground.md Appendix A.

All tests use the FastAPI TestClient (synchronous) and do not require a
running server or network access.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from playground.api.app import (
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_CELLS,
    MAX_UPLOAD_COLUMNS,
    MAX_UPLOAD_ROWS,
    app,
    limiter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Create a fresh TestClient for each test."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    limiter._storage.reset()
    return TestClient(app)


def _hospital_csv_bytes() -> bytes:
    """Load the hospital_10rows fixture as raw bytes."""
    return (FIXTURES_DIR / "hospital_10rows.csv").read_bytes()


# ---------------------------------------------------------------------------
# API service root
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_root_returns_api_service_metadata(client: TestClient) -> None:
    """GET / returns stable service metadata instead of crashing."""
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "DataForge Playground API"
    assert body["docs_url"] == "/api/docs"
    assert body["frontend_hosting"] == "cloudflare_static_assets"


# ---------------------------------------------------------------------------
# Case A.5: Health endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_health(client: TestClient) -> None:
    """GET /api/health returns the backend readiness and UI capability contract."""
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "DataForge Playground API"
    assert body["advanced_available"] is False
    assert body["max_upload_bytes"] == MAX_UPLOAD_BYTES
    assert body["limits"] == {
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_rows": MAX_UPLOAD_ROWS,
        "max_columns": MAX_UPLOAD_COLUMNS,
        "max_cells": MAX_UPLOAD_CELLS,
    }
    assert body["api_version"] == "0.1.0"
    assert body["contract_version"] == "repair_contract_v2"
    assert "server_time_utc" in body
    assert "metrics" in body
    assert "requests_total" in body["metrics"]


@pytest.mark.integration
def test_health_reports_advanced_capability_when_keyed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/health exposes advanced mode availability when a provider key exists."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["advanced_available"] is True


@pytest.mark.integration
def test_cors_rejects_unconfigured_workers_dev_origin(client: TestClient) -> None:
    """Workers-hosted frontends must be explicitly configured in production CORS."""
    origin = "https://dataforge.example-subdomain.workers.dev"
    response = client.get(
        "/api/health",
        headers={"Origin": origin},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "origin_not_allowed"
    assert "access-control-allow-origin" not in response.headers

    preflight = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 403
    assert "access-control-allow-origin" not in preflight.headers


# ---------------------------------------------------------------------------
# Case A.1: Profile hospital_10rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_profile_hospital(client: TestClient) -> None:
    """POST /api/profile with hospital_10rows returns valid issue list."""
    csv_bytes = _hospital_csv_bytes()
    response = client.post(
        "/api/profile",
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()

    # Top-level keys
    assert "issues" in body
    assert "meta" in body

    # Meta section
    meta = body["meta"]
    assert meta["rows"] == 10
    assert meta["columns"] == 10
    assert meta["contract_version"] == "repair_contract_v2"

    # Issues are non-empty for the seeded fixture
    issues = body["issues"]
    assert len(issues) > 0

    # Each issue has required keys
    for issue in issues:
        assert "column" in issue
        assert "issue_type" in issue
        assert "severity" in issue
        assert "row_indices" in issue


@pytest.mark.integration
def test_profile_advanced_unavailable_without_provider_key(client: TestClient) -> None:
    """POST /api/profile?advanced=true returns 400 when no provider key is configured."""
    csv_bytes = _hospital_csv_bytes()
    response = client.post(
        "/api/profile",
        params={"advanced": "true"},
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["type"].endswith("/advanced_mode_unavailable")
    assert body["status"] == 400
    assert body["error"] == "advanced_mode_unavailable"


@pytest.mark.integration
def test_profile_advanced_allowed_when_provider_key_is_present(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/profile?advanced=true is accepted when a provider key is configured."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    csv_bytes = _hospital_csv_bytes()
    response = client.post(
        "/api/profile",
        params={"advanced": "true"},
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Case A.3: Oversize upload rejected
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_near_limit_upload_is_accepted(client: TestClient) -> None:
    """A valid CSV file at the 1 MiB file cap is not rejected for multipart overhead."""
    payload_prefix = b"value\n"
    csv_bytes = payload_prefix + (b"x" * (MAX_UPLOAD_BYTES - len(payload_prefix)))
    response = client.post(
        "/api/profile",
        files={"file": ("near_limit.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["meta"]["rows"] == 1


@pytest.mark.integration
def test_oversize_body_rejected(client: TestClient) -> None:
    """POST /api/profile with > 1 MB body returns 413."""
    oversized = b"value\n" + (b"x" * MAX_UPLOAD_BYTES)
    response = client.post(
        "/api/profile",
        files={"file": ("big.csv", io.BytesIO(oversized), "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "file_too_large"
    assert response.headers["x-dataforge-request-id"]


@pytest.mark.integration
def test_malformed_csv_returns_stable_problem_detail(client: TestClient) -> None:
    """Malformed CSV uploads are client errors, not profile pipeline failures."""
    response = client.post(
        "/api/profile",
        files={"file": ("broken.csv", io.BytesIO(b'id,name\n1,"unterminated'), "text/csv")},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_csv"
    assert body["status"] == 400
    assert body["request_id"] == response.headers["x-dataforge-request-id"]


@pytest.mark.integration
def test_empty_csv_returns_stable_problem_detail(client: TestClient) -> None:
    """Empty CSV uploads get a clear problem detail."""
    response = client.post(
        "/api/profile",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "empty_csv"


@pytest.mark.integration
def test_upload_row_and_column_limits_are_enforced(client: TestClient) -> None:
    """The backend rejects valid CSVs that exceed playground processing limits."""
    too_many_rows = "value\n" + "\n".join(str(index) for index in range(MAX_UPLOAD_ROWS + 1))
    row_response = client.post(
        "/api/profile",
        files={"file": ("rows.csv", io.BytesIO(too_many_rows.encode()), "text/csv")},
    )
    assert row_response.status_code == 413
    assert row_response.json()["error"] == "too_many_rows"

    too_many_columns = ",".join(f"c{index}" for index in range(MAX_UPLOAD_COLUMNS + 1))
    too_many_columns += "\n" + ",".join("x" for _ in range(MAX_UPLOAD_COLUMNS + 1))
    column_response = client.post(
        "/api/profile",
        files={"file": ("columns.csv", io.BytesIO(too_many_columns.encode()), "text/csv")},
    )
    assert column_response.status_code == 413
    assert column_response.json()["error"] == "too_many_columns"


# ---------------------------------------------------------------------------
# Case A.4: Missing file rejected
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_missing_file_rejected(client: TestClient) -> None:
    """POST /api/profile with no file field returns 422."""
    response = client.post("/api/profile")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Case A.6: Sample download
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_samples_hospital(client: TestClient) -> None:
    """GET /api/samples/hospital_10rows returns CSV with content-disposition."""
    response = client.get("/api/samples/hospital_10rows")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    disposition = response.headers.get("content-disposition", "")
    assert "hospital_10rows.csv" in disposition
    # Body should contain CSV content with a header row
    text = response.text
    assert len(text.strip().splitlines()) > 1


# ---------------------------------------------------------------------------
# Repair dry-run
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_repair_dry_run(client: TestClient) -> None:
    """POST /api/repair?dry_run=true returns fixes + a real ephemeral txn journal view."""
    csv_bytes = _hospital_csv_bytes()
    response = client.post(
        "/api/repair",
        params={"dry_run": "true"},
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()

    assert "fixes" in body
    assert "txn_journal" in body
    assert body["meta"]["contract_version"] == "repair_contract_v2"
    assert "receipt" in body
    assert body["receipt"]["contract_version"] == "repair_contract_v2"
    assert body["receipt"]["source_sha256"] == body["txn_journal"]["source_sha256"]

    journal = body["txn_journal"]
    assert "txn_id" in journal
    assert journal["txn_id"].startswith("txn-")
    assert journal["created_at"].startswith("20")
    assert journal["source_name"] == "hospital_10rows.csv"
    assert len(journal["source_sha256"]) == 64
    assert journal["applied"] is False
    assert journal["fixes_count"] == len(body["fixes"])
    assert journal["events"] == [{"event_type": "created"}]
    for fix in body["fixes"]:
        assert "verifier_reason" in fix


@pytest.mark.integration
def test_repair_advanced_unavailable_without_provider_key(client: TestClient) -> None:
    """POST /api/repair?advanced=true returns 400 when no provider key is configured."""
    csv_bytes = _hospital_csv_bytes()
    response = client.post(
        "/api/repair",
        params={"dry_run": "true", "advanced": "true"},
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "advanced_mode_unavailable"


@pytest.mark.integration
def test_rate_limit_returns_429_on_eleventh_post(client: TestClient) -> None:
    """The in-memory rate limiter rejects the eleventh POST within a minute."""
    csv_bytes = _hospital_csv_bytes()

    for _ in range(10):
        response = client.post(
            "/api/profile",
            files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert response.status_code == 200

    response = client.post(
        "/api/profile",
        files={"file": ("hospital_10rows.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["error"] == "rate_limit_exceeded"
