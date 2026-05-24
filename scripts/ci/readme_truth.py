"""CI check: verify README claims match shipped code.

Asserts that every `dataforge15 <subcommand>` or compatibility
`dataforge <subcommand>` shown in the root README resolves to a registered
Typer command. Also checks that the playground
URL (once added) returns HTTP 200.

Usage:
    python scripts/ci/readme_truth.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
README = PROJECT_ROOT / "README.md"
CONTRIBUTORS = PROJECT_ROOT / "CONTRIBUTORS.md"
RELEASE_TRUTH_DOCS = [
    README,
    PROJECT_ROOT / "META_CONTEXT.md",
    PROJECT_ROOT / "docs" / "docs" / "index.md",
    PROJECT_ROOT / "docs" / "docs" / "quickstart.md",
    PROJECT_ROOT / "dataforge-mcp" / "README.md",
]
DESIGN_PARTNER_TRUTH_DOCS = [
    README,
    CONTRIBUTORS,
    PROJECT_ROOT / "META_CONTEXT.md",
    PROJECT_ROOT / "docs" / "docs" / "index.md",
    PROJECT_ROOT / "docs" / "docs" / "architecture.md",
]
UNPUBLISHED_DISTS = (
    "dataforge15",
    "dataforge15-dbt",
    "dataforge15-evals",
    "dataforge15-mcp",
    "dataforge15-agent-patterns",
)
PUBLISHED_QUALIFIERS = (
    "after publication",
    "after pypi publication",
    "once published",
    "when published",
)
DESIGN_PARTNER_NOT_MET_MARKER = "Design Partner Gate: NOT MET"
DESIGN_PARTNER_CLAIM_PATTERNS = (
    re.compile(r"\bdesign[- ]partners?\b", re.IGNORECASE),
    re.compile(r"\bpilot users?\b", re.IGNORECASE),
    re.compile(r"\bcustomer validated\b", re.IGNORECASE),
    re.compile(r"\bcustomer validation\b", re.IGNORECASE),
    re.compile(r"\benterprise[- ]ready\b", re.IGNORECASE),
)
DESIGN_PARTNER_QUALIFIERS = (
    "not met",
    "not yet",
    "does not",
    "no ",
    "without",
    "future",
    "criteria",
    "permission-to-list",
    "empty",
    "unclaimed",
    "not claimed",
    "seeking",
    "before",
    "until",
)


def extract_subcommands_from_readme(text: str) -> set[str]:
    """Find all DataForge15 CLI subcommand references in the README."""
    pattern = re.compile(r"\bdataforge(?:15)?\s+([a-z][a-z0-9_-]*)")
    return {m.group(1) for m in pattern.finditer(text)}


def extract_release_subcommands_from_readme(text: str) -> set[str]:
    """Find all nested ``dataforge15 release <command>`` references."""
    pattern = re.compile(r"\bdataforge(?:15)?\s+release\s+([a-z][a-z0-9_-]*)")
    return {m.group(1) for m in pattern.finditer(text)}


def get_registered_typer_commands() -> set[str]:
    """Import the Typer app and list registered command names."""
    try:
        from dataforge.cli import app as typer_app
    except ImportError as exc:
        print(f"WARNING: could not import dataforge.cli: {exc}", file=sys.stderr)
        return set()

    registered: set[str] = set()
    if hasattr(typer_app, "registered_commands"):
        for cmd in typer_app.registered_commands:
            if hasattr(cmd, "name") and cmd.name:
                registered.add(cmd.name)
    if hasattr(typer_app, "registered_groups"):
        for group in typer_app.registered_groups:
            if hasattr(group, "name") and group.name:
                registered.add(group.name)

    # Also check the callback (single-command mode)
    if hasattr(typer_app, "info") and hasattr(typer_app.info, "name") and typer_app.info.name:
        registered.add(typer_app.info.name)

    return registered


def get_registered_release_commands() -> set[str]:
    """Import the release Typer app and list registered release commands."""
    try:
        from dataforge.cli.release import release_app
    except ImportError as exc:
        print(f"WARNING: could not import dataforge.cli.release: {exc}", file=sys.stderr)
        return set()

    registered: set[str] = set()
    if hasattr(release_app, "registered_commands"):
        for cmd in release_app.registered_commands:
            if hasattr(cmd, "name") and cmd.name:
                registered.add(cmd.name)
    return registered


def extract_playground_urls(text: str) -> list[str]:
    """Find playground URLs in the README."""
    pattern = re.compile(r"https?://[^\s)]+(?:pages\.dev|hf\.space|dataforge\.dev)[^\s)]*")
    return pattern.findall(text)


def check_playground_urls(urls: list[str]) -> list[str]:
    """Check that playground URLs return 200 (if any are present)."""
    if not urls:
        return []

    errors: list[str] = []
    try:
        import httpx
    except ImportError:
        print("WARNING: httpx not available, skipping URL checks.", file=sys.stderr)
        return []

    for url in urls:
        try:
            response = httpx.get(url, timeout=30.0, follow_redirects=True)
            if response.status_code != 200:
                errors.append(f"URL {url} returned {response.status_code}")
        except Exception as exc:
            errors.append(f"URL {url} failed: {exc}")

    return errors


def check_unpublished_install_claims(paths: list[Path]) -> list[str]:
    """Reject unqualified PyPI install claims for packages not yet published."""
    errors: list[str] = []
    install_pattern = re.compile(
        rf"\bpip\s+install\b[^\n`]*(?:{'|'.join(re.escape(name) for name in UNPUBLISHED_DISTS)})"
    )
    for path in paths:
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.lower()
            if not install_pattern.search(line):
                continue
            if any(qualifier in lowered for qualifier in PUBLISHED_QUALIFIERS):
                continue
            errors.append(
                f"{path.relative_to(PROJECT_ROOT)}:{line_number} has an unqualified "
                "PyPI install claim for an unpublished DataForge15 package."
            )
    return errors


def design_partner_gate_not_met() -> bool:
    """Return whether the design-partner gate is explicitly marked unmet."""
    if not CONTRIBUTORS.exists():
        return False
    return DESIGN_PARTNER_NOT_MET_MARKER.lower() in CONTRIBUTORS.read_text(encoding="utf-8").lower()


def check_design_partner_claims(paths: list[Path]) -> list[str]:
    """Reject unqualified customer/design-partner claims while the gate is unmet."""
    if not design_partner_gate_not_met():
        return []

    errors: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            display_path = path.relative_to(PROJECT_ROOT)
        except ValueError:
            display_path = path
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lowered = line.lower()
            if not any(pattern.search(line) for pattern in DESIGN_PARTNER_CLAIM_PATTERNS):
                continue
            if any(qualifier in lowered for qualifier in DESIGN_PARTNER_QUALIFIERS):
                continue
            errors.append(
                f"{display_path}:{line_number} has an unqualified "
                "design-partner or customer-validation claim while the gate is not met."
            )
    return errors


def main() -> None:
    """Run all README truth checks."""
    readme_text = README.read_text(encoding="utf-8")
    errors: list[str] = []

    # Check subcommands
    claimed = extract_subcommands_from_readme(readme_text)
    registered = get_registered_typer_commands()
    claimed_release = extract_release_subcommands_from_readme(readme_text)
    registered_release = get_registered_release_commands()

    # Exclude known non-command references (e.g. version flags)
    non_commands = {"version", "help"}
    claimed_commands = claimed - non_commands

    if registered:
        missing = claimed_commands - registered
        if missing:
            errors.append(
                f"README claims these subcommands but they are not registered: {sorted(missing)}"
            )
    else:
        print("WARNING: could not resolve registered commands, skipping subcommand check.")

    if registered_release:
        missing_release = claimed_release - registered_release
        if missing_release:
            errors.append(
                "README claims these release subcommands but they are not registered: "
                f"{sorted(missing_release)}"
            )
    elif claimed_release:
        print(
            "WARNING: could not resolve release commands, skipping release subcommand check.",
            file=sys.stderr,
        )

    # Check playground URLs
    playground_urls = extract_playground_urls(readme_text)
    url_errors = check_playground_urls(playground_urls)
    errors.extend(url_errors)
    errors.extend(check_unpublished_install_claims(RELEASE_TRUTH_DOCS))
    errors.extend(check_design_partner_claims(DESIGN_PARTNER_TRUTH_DOCS))

    if errors:
        print("README truth check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    print(
        f"README truth check passed. "
        f"Claimed commands: {sorted(claimed_commands)}. "
        f"Claimed release commands: {sorted(claimed_release)}. "
        f"Playground URLs checked: {len(playground_urls)}."
    )


if __name__ == "__main__":
    main()
