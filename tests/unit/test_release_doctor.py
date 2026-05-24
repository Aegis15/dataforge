"""Tests for release doctor auth checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from dataforge.release.doctor import _load_kaggle_oauth, run_doctor


def test_kaggle_oauth_loader_refuses_legacy_kaggle_json(tmp_path: Path) -> None:
    legacy = tmp_path / "kaggle.json"
    legacy.write_text('{"username":"u","key":"secret"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="Refusing to read stale legacy"):
        _load_kaggle_oauth(legacy)


def test_kaggle_oauth_loader_accepts_credentials_json(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.json"
    credentials.write_text(
        """
        {
          "refresh_token": "hidden",
          "access_token": "hidden",
          "access_token_expiration": "2099-01-01T00:00:00Z",
          "username": "Praneshrajan15",
          "scopes": ["resources.admin:*"]
        }
        """,
        encoding="utf-8",
    )

    payload = _load_kaggle_oauth(credentials)

    assert payload["username"] == "Praneshrajan15"


def test_release_doctor_core_scope_does_not_require_personal_auth() -> None:
    """The default OSS release doctor avoids maintainer-only account checks."""
    report = run_doctor(core=True, maintainer_deploy=False)

    assert report.scopes == ["core"]
    assert {check.name for check in report.checks} == {
        "core_package_boundary",
        "core_packaged_files",
    }
