"""Masked Hugging Face authentication preflight for DataForge release work."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def check_hf_auth(*, hf_cli: Path | None = None) -> dict[str, Any]:
    """Return masked Hugging Face auth status without exposing tokens."""
    del hf_cli
    from huggingface_hub import HfApi, get_token

    token = get_token()
    if not token:
        raise RuntimeError("No Hugging Face token found in env or local cache.")
    payload = HfApi(token=token).whoami()
    user = payload.get("name")
    if not isinstance(user, str) or not user:
        raise RuntimeError("Hugging Face API did not return an authenticated user")
    return {
        "authenticated": True,
        "user": user,
        "auth_method": "huggingface_hub_python_api",
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
