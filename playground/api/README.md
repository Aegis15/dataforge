---
title: DataForge Playground
emoji: 📊
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Profile CSVs and dry-run safe repairs.
---

# DataForge Playground API

This is the API backend for the DataForge playground. The browser UI is deployed
separately through Cloudflare Workers Static Assets; this Hugging Face Docker
Space serves stateless CSV profiling and dry-run repair endpoints.

## What It Does

- Profile: detects type mismatches, decimal shifts, and functional dependency
  violations.
- Repair dry run: proposes fixes through SafetyFilter -> SMTVerifier and
  returns an ephemeral transaction receipt without persisting user data.
- Samples: serves small deterministic CSV examples for the static frontend.

## What It Does Not Do

- It does not persist uploaded files.
- It does not use cookies or analytics for file contents.
- It does not call an LLM by default.
- It does not perform autonomous production repair.

## Run Locally

```bash
python -m pip install -e ".[dev]"
pip install -r playground/api/requirements.txt
uvicorn playground.api.app:app --reload --port 7860
```

## Source

- Main repository: `github.com/Praneshrajan15/data-quality-env`
- Spec: `specs/SPEC_playground.md`
- License: Apache-2.0
