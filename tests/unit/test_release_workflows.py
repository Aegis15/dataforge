"""Release workflow guard tests for PyPI and TestPyPI publishing."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_pypi_workflow_refuses_prerelease_versions() -> None:
    """The real PyPI workflow must not publish RC metadata by accident."""
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "publish-dataforge.yml").read_text(
        encoding="utf-8"
    )

    assert "Refuse prerelease versions on PyPI" in workflow
    assert '("a", "b", "rc", ".dev")' in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" not in workflow


def test_testpypi_workflow_uses_trusted_publishing_and_installed_smoke() -> None:
    """The RC workflow publishes only to TestPyPI and smokes the installed artifact."""
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "publish-testpypi.yml").read_text(
        encoding="utf-8"
    )

    assert 'tags:\n      - "v*-rc*"' in workflow
    assert "environment: testpypi" in workflow
    assert "id-token: write" in workflow
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "--extra-index-url https://pypi.org/simple/" in workflow
    assert "dataforge15==0.1.0rc1" in workflow
    assert "dataforge15 constraints review constraints.json --accept" in workflow
    assert "dataforge15 release doctor --core --json" in workflow
