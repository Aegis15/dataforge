"""Masked Kaggle authentication preflight for DataForge remote training."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_KAGGLE_JSON = Path.home() / ".kaggle" / "kaggle.json"


def _sibling_kaggle_cli() -> Path:
    """Return the kaggle executable beside the current Python interpreter."""
    scripts_dir = Path(sys.executable).resolve().parent
    exe_name = "kaggle.exe" if os.name == "nt" else "kaggle"
    return scripts_dir / exe_name


def _load_credentials(path: Path) -> dict[str, Any]:
    """Load Kaggle credentials without returning the secret key."""
    if not path.exists():
        raise RuntimeError(f"Missing Kaggle credentials file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError("kaggle.json must contain a JSON object")
    username = payload.get("username")
    key = payload.get("key")
    if not isinstance(username, str) or not username:
        raise RuntimeError("kaggle.json is missing username")
    if not isinstance(key, str) or not key:
        raise RuntimeError("kaggle.json is missing key")
    return {
        "credentials_present": True,
        "credential_path": str(path),
        "username": username,
        "key_present": True,
        "key_printed": False,
    }


def check_kaggle_auth(
    *,
    kaggle_json: Path = DEFAULT_KAGGLE_JSON,
    kaggle_cli: Path | None = None,
) -> dict[str, Any]:
    """Return masked Kaggle auth and CLI status without printing the API key."""
    report = _load_credentials(kaggle_json)
    cli = kaggle_cli or _sibling_kaggle_cli()
    if not cli.exists():
        raise RuntimeError(f"Kaggle CLI not found at {cli}")
    result = subprocess.run(
        [str(cli), "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    report.update(
        {
            "cli": str(cli),
            "cli_version": result.stdout.strip(),
        }
    )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaggle-json", type=Path, default=DEFAULT_KAGGLE_JSON)
    parser.add_argument("--kaggle-cli", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = check_kaggle_auth(kaggle_json=args.kaggle_json, kaggle_cli=args.kaggle_cli)
    except Exception as exc:
        print(f"Kaggle auth preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
