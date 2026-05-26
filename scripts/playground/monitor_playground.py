"""Run production Playground uptime, CORS, and latency checks."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

from dataforge.release.playground_check import (
    DEFAULT_BACKEND_URL,
    DEFAULT_FRONTEND_URL,
    PlaygroundCheckReport,
    report_to_json,
    run_playground_check,
)


def _post_webhook(webhook_url: str, report: PlaygroundCheckReport) -> None:
    """Send a compact optional alert payload without secrets."""
    failed = [check.name for check in report.checks if not check.ok]
    payload: dict[str, Any] = {
        "ok": report.ok,
        "frontend_url": report.frontend_url,
        "backend_url": report.backend_url,
        "failed_checks": failed,
    }
    with httpx.Client(timeout=10.0) as client:
        client.post(webhook_url, json=payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL)
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--latency-threshold-ms", type=float, default=5_000.0)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("PLAYGROUND_ALERT_WEBHOOK_URL", ""),
        help="Optional alert webhook. Defaults to PLAYGROUND_ALERT_WEBHOOK_URL.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run monitor checks and return a CI-friendly exit code."""
    args = _build_parser().parse_args(argv)
    report = run_playground_check(
        frontend_url=args.frontend_url,
        backend_url=args.backend_url,
        latency_threshold_ms=args.latency_threshold_ms,
        include_doctor=False,
        include_smoke=False,
    )
    if args.json:
        print(report_to_json(report))
    else:
        for check in report.checks:
            status = "ok" if check.ok else "fail"
            print(f"{status:4} {check.name}: {check.detail}")

    if args.webhook_url and not report.ok:
        _post_webhook(args.webhook_url, report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
