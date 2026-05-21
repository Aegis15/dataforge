# SPEC: Playground (Hosted Demo)

> Status: Reviewed
> Owner: @Praneshrajan15
> Last updated: 2026-05-20

## 1. Purpose (2 sentences)

Provide a stateless, free-tier browser demo of DataForge profiling and
repair-dry-run behavior without weakening the core Safety -> Verifier ->
Transaction shape. The frontend is served from Cloudflare Workers Static Assets
and the backend is served as an API-only Hugging Face Docker Space.

## 2. Outcomes (measurable, binary pass/fail)

- [ ] `GET /api/health` returns `status`, `advanced_available`, and `max_upload_bytes`.
- [ ] `GET /` returns stable API service metadata and never tries to serve a SPA.
- [ ] `POST /api/profile` on `hospital_10rows.csv` returns a valid issue list within 5 s warm.
- [ ] `POST /api/repair?dry_run=true` returns fixes plus a redacted journal derived from a real `RepairTransaction`.
- [ ] API errors use RFC 9457 `application/problem+json` while preserving stable error codes as extension members.
- [ ] OpenAPI snapshots under `specs/openapi/` match the generated Playground and OpenEnv schemas.
- [ ] `advanced=true` is rejected with 400 when no provider key is configured and accepted when one is present.
- [ ] Uploaded CSV files larger than 1 MiB are rejected with 413; valid near-limit CSVs are not rejected only because of multipart overhead.
- [ ] Production CORS allows only exact origins from `DATAFORGE_PLAYGROUND_ORIGINS`; localhost is regex-allowed only when `DATAFORGE_PLAYGROUND_DEV=1`.
- [ ] Rate limiting returns 429 on the 11th POST within a minute from one client.
- [ ] The frontend uses relative assets plus `config.js` and never assumes HF static hosting.
- [ ] No browser storage APIs or frontend API keys appear under `playground/web/`.
- [ ] The authoritative HF deploy path uses `scripts/playground/stage_space.py`, not subtree push.
- [ ] The frontend imports the generated DataForge color system, passes
  `npm run colors:check`, and contains no hand-authored raw hex colors.
- [ ] Light and dark playground schemes preserve WCAG 2.2 contrast gates:
  primary text 7:1, secondary text 4.5:1, and non-text affordances 3:1.

## 3. Scope

**IN**:
- API endpoints: `/`, `/api/health`, `/api/samples/{name}`, `/api/profile`, `/api/repair`
- Temporary-directory-only dry-run transaction journaling
- Heuristic-first behavior with optional advanced mode
- Cloudflare Workers Static Assets frontend with runtime backend configuration
  via `config.js`
- Hugging Face Docker Space named `dataforge-playground`
- Hugging Face staging script and deployment runbooks
- Playground-focused tests, CI checks, and quality-gate coverage

**OUT**:
- Persistent state, sessions, accounts, or browser storage
- Apply-mode writes from the hosted playground
- Browser-side LLM calls
- Paid hosting or custom domains
- README claims that the playground is live before deploy verification

## 4. Constraints

- Performance: warm `/api/profile` and `/api/repair` on the 10-row sample should complete within 5 s.
- Compatibility: Python 3.11/3.12 development, Python 3.12 Docker runtime, modern evergreen browsers.
- Safety: no endpoint may silently bypass safety or verifier failures.
- Visual quality: color tokens come from `SPEC_color_system.md`; color never
  carries critical state without adjacent text, iconography, or ARIA semantics.
  The playground uses an institutional-console shell with a command bar,
  neutral-first surfaces, cobalt primary action, and subdued success green only
  for verified-safe states.
- Hosting: single-worker Space runtime, `PORT` honored, UID 1000, all temporary I/O under a request-local temp directory.
- Quality gate: `make lint`, `make type`, `make test`, playground smoke tests, and regression smoke must all pass.
- Contract gate: `make backend-gate` verifies OpenAPI drift, README truth,
  MCP tests, secret scan, dependency-audit availability, and package-build
  availability in addition to lint/type/test.

## 5. Prior decisions (locked - require new spec to change)

- Cloudflare Workers Static Assets serves the frontend; Hugging Face Space
  `dataforge-playground` serves the API backend.
- The hosted playground is stateless and dry-run only.
- Heuristic mode is the default; advanced mode is opt-in and backend-key-gated.
- Playground-only runtime dependencies stay out of core package runtime deps.
- The HF deploy artifact is built from a staged repo snapshot, not from subtree push.

## 6. Task breakdown (atomic sub-tasks)

### 6.1 Backend contract hardening
- Acceptance: `/` returns JSON service metadata; `/api/health` returns capability metadata; broken static-file assumptions are removed.
- Depends on: none
- Estimated complexity: M

### 6.2 Shared repair-pipeline reuse
- Acceptance: `/api/repair` calls `dataforge.engine.repair.run_repair_pipeline`
  and returns a redacted `RepairTransaction` view.
- Depends on: 6.1
- Estimated complexity: L

### 6.3 Advanced-mode enforcement
- Acceptance: keyless advanced requests fail with 400; keyed advanced requests are accepted.
- Depends on: 6.1
- Estimated complexity: S

### 6.4 Frontend decoupling
- Acceptance: relative assets, `config.js`, request-state locking, and keyboard-complete tabs all ship.
- Depends on: 6.1
- Estimated complexity: M

### 6.5 HF staging and runbooks
- Acceptance: `scripts/playground/stage_space.py` produces a Docker-buildable Space tree and docs reference that flow.
- Depends on: 6.1
- Estimated complexity: M

### 6.6 Quality gate expansion
- Acceptance: Makefile and CI cover the shipped Week 5 Python paths and playground contract tests.
- Depends on: 6.1 to 6.5
- Estimated complexity: S

### 6.7 Problem details and OpenAPI contracts
- Acceptance: expected HTTP failures return RFC 9457 problem details with
  stable `error` extension values, and `scripts/ci/openapi_contract.py --check`
  fails on schema drift.
- Depends on: 6.1, 6.2
- Estimated complexity: S

## 7. Verification

- Integration tests: `tests/integration/test_playground_smoke.py`
- Unit tests: `tests/unit/test_playground_stage_space.py`, `tests/unit/test_playground_web_contract.py`
- Regression tests: `tests/regression/test_env.py`
- Frontend visual contract: `npm run colors:check`, `npm run audit:colors`
- CI assertions: no browser storage APIs, no frontend API keys, no raw
  hand-authored hex colors, valid HF Space front matter

## 8. Acceptance gate (ALL must be TRUE to mark SPEC complete)

- [ ] All Section 2 outcomes are met.
- [ ] All Section 6 tasks have "passes".
- [ ] Playground smoke and contract tests are green.
- [ ] No test in `tests/regression/` fails.
- [ ] The HF staging script output matches Docker COPY sources.
- [ ] Docs describe the authoritative deploy flows and do not overclaim a live deployment.

## Appendix A - Toy cases (write the FIRST failing tests from these)

### Case A.1: API root is stable
Input: `GET /`
Expected output: 200 JSON response with `service`, `status`, and `docs_url`
Reasoning: catches the broken same-origin SPA fallback and guarantees the backend is API-only.

### Case A.2: Health exposes capabilities
Input: `GET /api/health`
Expected output: `{"status":"ok","advanced_available":<bool>,"max_upload_bytes":1048576}`
Reasoning: the frontend needs this to render the advanced toggle and upload guard honestly.

### Case A.3: Advanced mode is key-gated
Input: `POST /api/profile?advanced=true` with and without a provider key
Expected output: 400 when unkeyed, 200 when keyed
Reasoning: prevents a dead toggle in the hosted UI.

### Case A.4: Repair returns a real ephemeral journal
Input: `POST /api/repair?dry_run=true` with `hospital_10rows.csv`
Expected output: `fixes` plus `txn_journal` with `txn_id`, `created_at`, `source_sha256`, and `events`
Reasoning: proves the hosted flow still reflects the true transaction model.

### Case A.5: Rate limit boundary
Input: 11 POST requests from one client in under a minute
Expected output: first 10 accepted, 11th returns 429
Reasoning: validates the free-tier abuse guard and the single-worker contract.

### Case A.6: CORS is exact-origin in production
Input: production request from an unconfigured `workers.dev` origin
Expected output: no `Access-Control-Allow-Origin` response header
Reasoning: prevents another Cloudflare account from calling the API by virtue of sharing the same platform domain.

### Case A.7: HF staging is internally consistent
Input: `python scripts/playground/stage_space.py --output-dir <tmp>`
Expected output: staged repo contains every Docker COPY source and omits the frontend tree
Reasoning: prevents deploy docs from drifting away from the actual Docker build context.

### Case A.8: Problem detail shape
Input: `POST /api/profile?advanced=true` without a provider key.
Expected output: 400 `application/problem+json` with `type`, `title`, `status`, `detail`, and `error="advanced_mode_unavailable"`.
Reasoning: gives clients a stable error contract without preserving ad hoc FastAPI exception wrappers.

### Case A.9: OpenAPI drift check
Input: generated Playground or OpenEnv schema differs from `specs/openapi/*.json`.
Expected output: backend gate fails and asks the contributor to regenerate snapshots intentionally.
Reasoning: treats API schema as a reviewed contract artifact.
