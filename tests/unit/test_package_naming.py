"""Release naming contract for the DataForge15 distributions."""

from __future__ import annotations

import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_pyproject(path: Path) -> dict[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_core_distribution_uses_dataforge15_name_and_cli_aliases() -> None:
    """The core PyPI distribution is renamed without changing imports."""
    pyproject = _load_pyproject(PROJECT_ROOT / "pyproject.toml")
    project = pyproject["project"]

    assert project["name"] == "dataforge15"
    assert (
        "dataforge15[dev,train,eval,playground,openenv]" in project["optional-dependencies"]["all"]
    )
    assert project["scripts"]["dataforge15"] == "dataforge.cli:app"
    assert project["scripts"]["dataforge"] == "dataforge.cli:app"
    assert pyproject["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "dataforge",
        "dataforge.*",
        "data_quality_env",
        "data_quality_env.*",
    ]


def test_mcp_distribution_uses_dataforge15_name_and_legacy_alias() -> None:
    """The MCP side package publishes under DataForge15 while keeping an alias."""
    pyproject = _load_pyproject(PROJECT_ROOT / "dataforge-mcp" / "pyproject.toml")
    project = pyproject["project"]

    assert project["name"] == "dataforge15-mcp"
    assert "dataforge15>=0.1.0" in project["dependencies"]
    assert project["scripts"]["dataforge15-mcp"] == "dataforge_mcp.server:main"
    assert project["scripts"]["dataforge-mcp"] == "dataforge_mcp.server:main"
