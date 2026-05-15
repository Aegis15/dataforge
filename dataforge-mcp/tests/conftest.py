"""Test path setup for the nested dataforge-mcp package."""

from __future__ import annotations

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent

for path in (str(PACKAGE_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
