"""Tests for the canonical release gate contracts."""

from __future__ import annotations

import zipfile
from pathlib import Path

from dataforge.release.gate import (
    REQUIRED_WHEEL_MEMBERS,
    SCHEMA_VERSION,
    ReleaseGateReport,
    _audit_wheel_contents,
)


def _write_wheel(path: Path, members: set[str]) -> None:
    """Write a minimal wheel-like zip for content-audit tests."""
    with zipfile.ZipFile(path, "w") as archive:
        for member in sorted(members):
            archive.writestr(member, "")


def test_release_gate_report_schema_is_versioned() -> None:
    report = ReleaseGateReport(ok=True, steps=[])

    payload = report.to_dict()

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["offline_install"] is True
    assert payload["secrets_printed"] is False


def test_wheel_contents_audit_accepts_allowed_surface(tmp_path: Path) -> None:
    wheel_path = tmp_path / "dataforge15-0.1.0-py3-none-any.whl"
    members = set(REQUIRED_WHEEL_MEMBERS) | {
        "dataforge/__init__.py",
        "dataforge15-0.1.0.dist-info/METADATA",
        "dataforge15-0.1.0.dist-info/WHEEL",
        "dataforge15-0.1.0.dist-info/RECORD",
    }
    _write_wheel(wheel_path, members)

    step = _audit_wheel_contents(wheel_path)

    assert step.ok is True


def test_wheel_contents_audit_rejects_non_package_files(tmp_path: Path) -> None:
    wheel_path = tmp_path / "dataforge15-0.1.0-py3-none-any.whl"
    members = set(REQUIRED_WHEEL_MEMBERS) | {
        "dataforge/__init__.py",
        "dataforge15-0.1.0.dist-info/METADATA",
        "tests/test_leaked.py",
        "data_quality_env/legacy.py",
        "root_script.py",
    }
    _write_wheel(wheel_path, members)

    step = _audit_wheel_contents(wheel_path)

    assert step.ok is False
    assert step.metadata["errors"]
