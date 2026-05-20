"""Masked Hugging Face authentication preflight for DataForge release work."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _sibling_hf_cli() -> Path:
    """Return the hf executable beside the current Python interpreter."""
    scripts_dir = Path(sys.executable).resolve().parent
    exe_name = "hf.exe" if os.name == "nt" else "hf"
    return scripts_dir / exe_name


def _run_json(command: list[str], *, timeout_s: int = 30) -> dict[str, Any]:
    """Run a CLI command that should emit JSON."""
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    first_line = result.stdout.strip().splitlines()[0]
    payload = json.loads(first_line)
    if not isinstance(payload, dict):
        raise RuntimeError("hf command did not return a JSON object")
    return payload


def check_hf_auth(*, hf_cli: Path | None = None) -> dict[str, Any]:
    """Return masked Hugging Face auth status without exposing tokens."""
    cli = hf_cli or _sibling_hf_cli()
    if not cli.exists():
        raise RuntimeError(f"hf CLI not found at {cli}")
    payload = _run_json([str(cli), "auth", "whoami", "--format", "json"])
    user = payload.get("user")
    if not isinstance(user, str) or not user:
        raise RuntimeError("hf auth whoami did not return an authenticated user")
    return {
        "authenticated": True,
        "user": user,
        "cli": str(cli),
        "hf_token_env_present": bool(os.environ.get("HF_TOKEN")),
        "token_printed": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-cli", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = check_hf_auth(hf_cli=args.hf_cli)
    except Exception as exc:
        print(f"Hugging Face auth preflight failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
