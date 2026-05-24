"""Masked Kaggle authentication preflight for DataForge remote training."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_KAGGLE_CREDENTIALS = Path.home() / ".kaggle" / "credentials.json"
STALE_KAGGLE_JSON = Path.home() / ".kaggle" / "kaggle.json"


def _load_credentials(path: Path) -> dict[str, Any]:
    """Load Kaggle OAuth credentials without returning tokens."""
    if path.name == "kaggle.json":
        raise RuntimeError(
            f"Refusing to read stale legacy Kaggle API key file: {path}. "
            f"Use OAuth credentials at {DEFAULT_KAGGLE_CREDENTIALS}."
        )
    if not path.exists():
        raise RuntimeError(f"Missing Kaggle credentials file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError("Kaggle credentials must contain a JSON object")
    required = {"refresh_token", "access_token", "access_token_expiration", "username", "scopes"}
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError("Kaggle OAuth credentials missing fields: " + ", ".join(missing))
    username = payload.get("username")
    scopes = payload.get("scopes")
    if not isinstance(username, str) or not username:
        raise RuntimeError("Kaggle OAuth credentials are missing username")
    if not isinstance(scopes, list) or not scopes:
        raise RuntimeError("Kaggle OAuth credentials are missing scopes")
    return {
        "credentials_present": True,
        "credential_path": str(path),
        "credential_type": "oauth",
        "username": username,
        "scopes_count": len(scopes),
        "legacy_kaggle_json_exists": STALE_KAGGLE_JSON.exists(),
        "legacy_kaggle_json_used": False,
        "tokens_printed": False,
    }


def check_kaggle_auth(
    *,
    kaggle_json: Path = DEFAULT_KAGGLE_CREDENTIALS,
    kaggle_cli: Path | None = None,
) -> dict[str, Any]:
    """Return masked Kaggle auth and CLI status without printing the API key."""
    report = _load_credentials(kaggle_json)
    del kaggle_cli
    try:
        kaggle_version = metadata.version("kaggle")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("Python package 'kaggle' is not installed") from exc
    report.update(
        {
            "client": "kaggle_python_package",
            "client_version": kaggle_version,
        }
    )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kaggle-json", type=Path, default=DEFAULT_KAGGLE_CREDENTIALS)
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
