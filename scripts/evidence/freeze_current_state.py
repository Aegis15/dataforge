"""Write a non-mutating evidence snapshot for release and training decisions."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT = Path("eval/results/evidence_freeze_current.json")
DEFAULT_SFT_SUMMARY = Path("eval/results/sft_release_v2_after_kaggle_summary.json")


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    """Run a read-only command and return a serializable result."""
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON object if it exists."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"payload": payload}


def build_evidence(root: Path, *, sft_summary: Path) -> dict[str, Any]:
    """Build the current evidence-freeze payload."""
    sft_summary_payload = _load_json(sft_summary)
    return {
        "schema_version": "dataforge_evidence_freeze_v1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": (
            "Freeze the pre-implementation diagnostic baseline before contract, "
            "inferability, and evaluation-gate changes."
        ),
        "worktree": {
            "git_status_short": _run(["git", "status", "--short"], cwd=root),
            "git_diff_stat": _run(["git", "diff", "--stat"], cwd=root),
        },
        "sft_diagnostic_baseline": sft_summary_payload,
        "promotion_decision": {
            "current_sft_is_training_baseline_only": True,
            "reason": (
                "The current release summary records no verified strict-F1 gain and "
                "schema/parse failures, so it must not be treated as a quality milestone."
            ),
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sft-summary", type=Path, default=DEFAULT_SFT_SUMMARY)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write the evidence-freeze JSON artifact."""
    args = _build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    evidence = build_evidence(root, sft_summary=args.sft_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote evidence freeze to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
