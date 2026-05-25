# Release

## 0.1.0rc1 TestPyPI Rehearsal

Status: pending maintainer configuration and TestPyPI run.

Required trusted-publisher setup before tagging:

- TestPyPI pending publisher for project `dataforge15`, workflow
  `publish-testpypi.yml`, environment `testpypi`.
- PyPI pending publisher for project `dataforge15`, workflow
  `publish-dataforge.yml`, environment `pypi`.
- GitHub environment approval rules for both `testpypi` and `pypi`.

RC evidence to record after the workflow passes:

- Git SHA and tag: `v0.1.0-rc1`.
- Wheel and sdist filenames plus SHA-256 hashes.
- TestPyPI project URL.
- Installed-package smoke output for `dataforge15 --version`, `profile`,
  `profile --constraints-out`, `constraints review --accept ... --no-tui`,
  `repair --constraints --dry-run --json`, and
  `release doctor --core --json`.

Real PyPI remains blocked until the RC evidence above is complete and ownership
is verified. The real PyPI workflow refuses pre-release package metadata.
