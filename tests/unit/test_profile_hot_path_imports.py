"""Cold-path import guard for the profile command."""

from __future__ import annotations

import importlib
import sys


def test_profile_import_does_not_eagerly_import_heavy_optional_modules() -> None:
    """The profile command must stay independent of pandas/openenv/duckdb."""
    for module_name in ("pandas", "numpy", "duckdb", "openenv", "trl"):
        sys.modules.pop(module_name, None)

    importlib.import_module("dataforge.cli.profile")

    for module_name in ("pandas", "numpy", "duckdb", "openenv", "trl"):
        assert module_name not in sys.modules
