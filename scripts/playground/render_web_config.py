"""Render the deploy-time frontend config for Cloudflare static assets."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "playground" / "web" / "config.js"


def normalize_backend_url(raw_url: str) -> str:
    """Validate and normalize the backend base URL."""
    value = raw_url.strip()
    if not value:
        raise ValueError("BACKEND_URL must be set.")

    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise ValueError("BACKEND_URL must use https.")
    if not parsed.netloc:
        raise ValueError("BACKEND_URL must include a hostname.")
    if parsed.query or parsed.fragment:
        raise ValueError("BACKEND_URL must not include a query string or fragment.")

    normalized_path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, "", ""))


def render_config(backend_url: str, output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    """Write the deployable config.js file and return its path."""
    normalized_url = normalize_backend_url(backend_url)
    body = (
        "window.__DATAFORGE_CONFIG__ = Object.freeze({\n"
        f"    BACKEND_URL: {json.dumps(normalized_url)},\n"
        "});\n"
    )
    output_path.write_text(body, encoding="utf-8")
    return output_path


def _build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Where to write the rendered config.js file.",
    )
    return parser


def main() -> None:
    """Render the runtime frontend config from BACKEND_URL."""
    args = _build_parser().parse_args()
    output_path = args.output_path.resolve()
    try:
        render_config(os.environ.get("BACKEND_URL", ""), output_path=output_path)
    except ValueError as exc:
        raise SystemExit(f"Invalid BACKEND_URL: {exc}") from exc

    print(f"Rendered frontend config at {output_path}")


if __name__ == "__main__":
    main()
