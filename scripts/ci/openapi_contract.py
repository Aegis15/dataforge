"""Generate or verify OpenAPI contract snapshots for backend surfaces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
SNAPSHOT_DIR = PROJECT_ROOT / "specs" / "openapi"
SNAPSHOTS = {
    "playground": SNAPSHOT_DIR / "playground.openapi.json",
    "openenv": SNAPSHOT_DIR / "openenv.openapi.json",
}


def _canonical_json(payload: dict[str, Any]) -> str:
    """Return stable JSON for drift checks."""
    return json.dumps(payload, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _schemas() -> dict[str, dict[str, Any]]:
    """Load FastAPI apps lazily and return their OpenAPI schemas."""
    from dataforge.env.server import app as openenv_app
    from playground.api.app import app as playground_app

    return {
        "playground": playground_app.openapi(),
        "openenv": openenv_app.openapi(),
    }


def write_snapshots() -> None:
    """Write all OpenAPI snapshots."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for name, schema in _schemas().items():
        SNAPSHOTS[name].write_text(_canonical_json(schema), encoding="utf-8")


def check_snapshots() -> int:
    """Return non-zero when any generated OpenAPI schema differs from its snapshot."""
    failures: list[str] = []
    for name, schema in _schemas().items():
        expected_path = SNAPSHOTS[name]
        actual = _canonical_json(schema)
        if not expected_path.exists():
            failures.append(f"{name}: missing snapshot {expected_path}")
            continue
        expected = expected_path.read_text(encoding="utf-8")
        if actual != expected:
            failures.append(
                f"{name}: schema drift detected; run scripts/ci/openapi_contract.py --write"
            )

    if failures:
        for failure in failures:
            print(f"OPENAPI DRIFT: {failure}")
        return 1
    print("OpenAPI contract snapshots are current.")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Regenerate OpenAPI snapshots.")
    mode.add_argument("--check", action="store_true", help="Verify snapshots are current.")
    args = parser.parse_args()
    if args.write:
        write_snapshots()
        return 0
    return check_snapshots()


if __name__ == "__main__":
    raise SystemExit(main())
