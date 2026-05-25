# Changelog

## 0.1.0rc1

- Added `dataforge15 constraints review` with a Textual review UI for
  `constraint_review_v1` artifacts.
- Added deterministic review flags for CI: `--accept`, `--reject`,
  `--pending`, `--note`, `--dry-run`, `--output`, `--json`, and `--no-tui`.
- Added artifact integrity checks for duplicate candidate IDs, tampered
  candidate payloads, strict source metadata, and atomic safe rewrites.
- Added an RC-first TestPyPI workflow using trusted publishing and an installed
  package smoke for profile, constraint review, repair, and release doctor.
- Guarded the real PyPI workflow so pre-release versions cannot publish there.

## 0.1.0

- Added the CLI-first DataForge15 repair pipeline with profile, repair, revert,
  and bench commands.
- Added detectors for type mismatches, decimal shifts, and functional
  dependency violations.
- Added deterministic repairers, safety checks, SMT verification, and
  reversible transaction journals.
- Added OpenEnv-compatible environment actions and causal root-cause analysis.
- Added benchmark generation from committed evidence.
- Added Hugging Face Space and Cloudflare frontend playground sources.
- Added model-training and release-verification scaffolding for SFT and GRPO
  research workflows.
