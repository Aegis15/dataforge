"""Verify the deployed Cloudflare frontend against the HF backend."""

from __future__ import annotations

import argparse

import httpx

DEFAULT_BACKEND_URL = "https://Praneshrajan15-data-quality-env.hf.space"


def normalize_url(value: str) -> str:
    """Strip whitespace and trailing slashes from a URL."""
    return value.strip().rstrip("/")


def require(condition: bool, message: str) -> None:
    """Exit with a readable error when an assertion fails."""
    if not condition:
        raise SystemExit(message)


def verify(frontend_url: str, backend_url: str) -> None:
    """Run the end-to-end deployment checks."""
    frontend_url = normalize_url(frontend_url)
    backend_url = normalize_url(backend_url)

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        frontend = client.get(frontend_url)
        require(frontend.status_code == 200, f"Frontend root returned {frontend.status_code}")
        require("<!DOCTYPE html>" in frontend.text, "Frontend root did not return HTML.")
        require("./config.js" in frontend.text, "Frontend HTML is missing config.js.")
        require("./app.js" in frontend.text, "Frontend HTML is missing app.js.")

        config = client.get(f"{frontend_url}/config.js")
        require(config.status_code == 200, f"config.js returned {config.status_code}")
        require(
            backend_url in config.text,
            f"config.js does not contain backend URL {backend_url}",
        )

        health = client.get(f"{backend_url}/api/health")
        require(health.status_code == 200, f"Backend health returned {health.status_code}")

        cors = client.get(
            f"{backend_url}/api/health",
            headers={"Origin": frontend_url},
        )
        require(cors.status_code == 200, f"CORS health probe returned {cors.status_code}")
        require(
            cors.headers.get("access-control-allow-origin") == frontend_url,
            "Backend CORS response does not allow the deployed frontend origin.",
        )

    print(f"Verified frontend {frontend_url}")
    print(f"Verified backend {backend_url}")


def _build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True, help="Cloudflare frontend URL.")
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help="Hugging Face backend base URL.",
    )
    return parser


def main() -> None:
    """Run the deployment verification checks."""
    args = _build_parser().parse_args()
    verify(args.frontend_url, args.backend_url)


if __name__ == "__main__":
    main()
