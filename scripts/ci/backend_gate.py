"""Canonical backend release-quality gate for DataForge15."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable

PYTHON_PATHS = [
    "dataforge",
    "data_quality_env",
    "tests",
    "scripts/ci",
    "scripts/playground",
    "scripts/data",
    "scripts/model",
    "scripts/publish_model.py",
    "playground/api/app.py",
]
MYPY_PATHS = [
    "dataforge",
    "data_quality_env",
    "playground/api/app.py",
    "scripts/ci/readme_truth.py",
    "scripts/ci/openapi_contract.py",
    "scripts/ci/backend_gate.py",
    "scripts/playground/build_samples.py",
    "scripts/playground/stage_space.py",
    "scripts/playground/verify_space_backend.py",
    "scripts/data/collect_sft_trajectories.py",
    "scripts/data/validate_sft_readiness.py",
    "scripts/model/verify_sft_release.py",
    "scripts/model/publish_dataset_readme.py",
    "scripts/publish_model.py",
]
EXCLUDED_SECRET_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "benchmark_results",
    "build",
    "datasets",
    "dist",
    "htmlcov",
    "node_modules",
}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{36,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
]


def _run(label: str, command: list[str], *, optional: bool = False) -> bool:
    """Run a gate command and return whether it passed."""
    print(f"\n==> {label}")
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    except FileNotFoundError as exc:
        if optional:
            print(f"SKIP {label}: {exc}")
            return True
        print(f"FAIL {label}: {exc}")
        return False
    if result.returncode == 0:
        print(f"PASS {label}")
        return True
    if optional:
        print(f"SKIP {label}: command exited {result.returncode}")
        return True
    print(f"FAIL {label}: command exited {result.returncode}")
    return False


def _module_available(module: str) -> bool:
    """Return whether ``python -m module`` is importable."""
    result = subprocess.run(
        [PYTHON, "-c", f"import {module}"],
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _secret_scan() -> bool:
    """Scan first-party files for high-confidence secret material."""
    print("\n==> secret scan")
    findings: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(
            part in EXCLUDED_SECRET_DIRS or part.startswith(".hf-space") for part in relative.parts
        ):
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".parquet", ".bin"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(str(relative))
                break
    if findings:
        for finding in findings:
            print(f"SECRET? {finding}")
        return False
    print("PASS secret scan")
    return True


def main() -> int:
    """Run the backend gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-full-tests", action="store_true", help="Skip full pytest suite.")
    parser.add_argument(
        "--require-optional",
        action="store_true",
        help="Fail when optional supply-chain tools are unavailable.",
    )
    args = parser.parse_args()

    checks: list[bool] = [
        _run("ruff check", [PYTHON, "-m", "ruff", "check", *PYTHON_PATHS]),
        _run("ruff format --check", [PYTHON, "-m", "ruff", "format", "--check", *PYTHON_PATHS]),
        _run("strict mypy", [PYTHON, "-m", "mypy", "--strict", *MYPY_PATHS]),
    ]
    if not args.skip_full_tests:
        checks.append(_run("root pytest", [PYTHON, "-m", "pytest", "tests/", "-x", "-v"]))
    checks.extend(
        [
            _run("MCP pytest", [PYTHON, "-m", "pytest", "dataforge-mcp/tests", "-v"]),
            _run("README truth", [PYTHON, "scripts/ci/readme_truth.py"]),
            _run("OpenAPI drift", [PYTHON, "scripts/ci/openapi_contract.py", "--check"]),
            _secret_scan(),
        ]
    )

    pip_audit_optional = not (
        args.require_optional or os.environ.get("DATAFORGE_REQUIRE_PIP_AUDIT")
    )
    if _module_available("pip_audit"):
        checks.append(_run("pip-audit", [PYTHON, "-m", "pip_audit"], optional=False))
    else:
        checks.append(
            _run(
                "pip-audit",
                [PYTHON, "-m", "pip_audit"],
                optional=pip_audit_optional,
            )
        )

    sbom_optional = not (args.require_optional or os.environ.get("DATAFORGE_REQUIRE_SBOM"))
    checks.append(
        _run(
            "CycloneDX SBOM",
            [PYTHON, "-m", "cyclonedx_py", "environment", "-o", "dist/cyclonedx-env.json"],
            optional=sbom_optional,
        )
    )

    build_optional = not (args.require_optional or os.environ.get("DATAFORGE_REQUIRE_BUILD"))
    checks.append(
        _run(
            "dataforge15 package build",
            [PYTHON, "-m", "build", "--sdist", "--wheel"],
            optional=build_optional,
        )
    )
    checks.append(
        _run(
            "dataforge15-mcp package build",
            [PYTHON, "-m", "build", "--sdist", "--wheel", "dataforge-mcp"],
            optional=build_optional,
        )
    )

    if all(checks):
        print("\nBackend gate passed.")
        return 0
    print("\nBackend gate failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
