"""Unit tests for the mapped-test runner."""

from __future__ import annotations

import sys

from scripts import test_mapped


def test_test_mapped_invokes_pytest_through_current_interpreter() -> None:
    assert (sys.executable, "-m", "pytest") == test_mapped._PYTEST_CMD
