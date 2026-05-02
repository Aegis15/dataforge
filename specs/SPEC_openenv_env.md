# SPEC: OpenEnv-Compatible DataForge RL Environment

> Status: **Accepted** — all open questions resolved (DECISIONS.md 2026-05-01)
> Owner: pranesh
> Last updated: 2026-05-01

## 1. Purpose (2 sentences)

Provide a typed, OpenEnv-compatible RL environment inside the shipped `dataforge`
package that exposes a 7-action tool-use interface for data-quality detection,
diagnosis, and repair — with no LLM calls inside the environment. This replaces
the legacy `data_quality_env` hackathon code for new training and evaluation
while keeping the legacy package frozen as a compatibility shim.

## 2. Outcomes (measurable, binary pass/fail)

- [x] `DataForgeEnv.reset()` returns a well-formed `ResetResult` with a valid
  `DataForgeObservation` containing visible rows and step budget.
- [x] All 7 action types (`INSPECT_ROWS`, `SQL_QUERY`, `STAT_TEST`,
  `PATTERN_MATCH`, `HYPOTHESIS`, `DIAGNOSE`, `FIX`) produce well-formed
  `StepResult` objects with correct reward signals.
- [x] Terminal score formula matches `REWARD_DESIGN.md` bit-for-bit:
  `detection_rate * 0.40 + fix_rate * 0.60 - false_positives * fp_rate`.
- [x] FIX actions pass through SafetyFilter -> SMTVerifier before acceptance;
  rejected fixes appear in observations, not as exceptions.
- [x] Step-budget termination auto-finalizes the episode.
- [x] HTTP endpoints (`POST /reset`, `POST /step`, `POST /close`, `GET /health`,
  `GET /metadata`, `GET /schema`) return OpenEnv-compatible JSON.
- [x] `tests/regression/test_env.py` continues to pass unchanged.

## 3. Scope

**IN**:
- `dataforge/env/environment.py` — `DataForgeEnv` with `reset()`, `step()`,
  `state()`, `close()` (no-op)
- `dataforge/agent/tool_actions.py` — 7 discriminated Pydantic action models
  with `parse_action()` entry point
- `dataforge/agent/scratchpad.py` — in-episode hypothesis tracker
- `dataforge/env/observation.py` — observation builder with noise injection
- `dataforge/env/reward.py` — reward engine preserving REWARD_DESIGN.md formula
- `dataforge/env/server.py` — FastAPI app for OpenEnv HTTP protocol
- `openenv.yaml` — updated for `dataforge-env`
- `Dockerfile.env` — env-specific Docker image

**OUT** (explicitly excluded, to prevent scope creep):
- Agent loop / LLM integration (future Week 7+)
- Training pipeline (SFT/GRPO/GiGPO)
- Durable CSV mutation or transaction log creation (owned by CLI repair)
- Modification of legacy `data_quality_env/` package
- WebSocket protocol (HTTP-only for now)
- Concurrent session management

## 4. Constraints

- Performance: `reset()` completes in < 500ms on the hospital fixture;
  `step()` completes in < 200ms per action.
- Compatibility: Python 3.11+, works on Linux / macOS / Windows.
- Backward compatibility: `tests/regression/test_env.py` must not fail.
  Legacy `data_quality_env` imports remain functional.
- `openenv-core[core]>=0.2.2` is an optional dependency, not a mandatory
  runtime requirement for the `dataforge` CLI.

## 5. Prior decisions (locked — require new spec to change)

- Three-tier severity (SAFE / REVIEW / UNSAFE) — DECISIONS.md 2026-04-20
- Z3 as SMT solver — DECISIONS.md 2026-04-20
- Safety pipeline: SafetyFilter -> SMTVerifier -> TransactionLog — META_CONTEXT.md §0.4
- OpenEnv core API is `reset() / step() / state()`, not `close()` — CLAUDE.md
- Reward formula from REWARD_DESIGN.md is canonical (0.40/0.60 weights)

## 5.1 Reward coefficient mismatch (documented)

The Week 6 prompt contained alternate coefficient values that differ from
`REWARD_DESIGN.md`. This spec preserves the `REWARD_DESIGN.md` formula
(detection_rate × 0.40 + fix_rate × 0.60 - false_positives × 0.05) as
canonical. The prompt's alternate values are not implemented.

## 5.2 Resolved design decisions (DECISIONS.md 2026-05-01)

All five open questions from the initial plan were resolved:

1. **Action space**: expanded from 4 legacy actions to 7 typed tool-use
   actions with discriminated Pydantic union. `finalize` replaced by
   automatic step-budget termination. See DECISIONS.md "Expand action
   space from 4 to 7".

2. **INSPECT_ROWS cap**: 20 rows per action (not 20 cells). The cell-level
   interpretation creates perverse incentives — agents waste step budget
   on data access instead of analysis. See DECISIONS.md "INSPECT_ROWS
   returns up to 20 rows, not 20 cells".

3. **Default dataset**: `fixtures/hospital_10rows.csv` with its schema
   YAML, configurable for future BYOD scenarios. See DECISIONS.md "Use
   hospital fixture as default".

4. **Noise model**: legacy ε=0.15 seed-based noise ported verbatim.
   Refining the noise model is a research concern for future milestones.
   See DECISIONS.md "Port legacy noise model verbatim".

5. **Hypothesis matching**: `issue_type` (from `IssueTypeLiteral`) plus
   row/column membership against ground truth. The `claim` text is
   recorded but not scored. See DECISIONS.md "Hypothesis root-cause
   matching on issue_type".

## 6. Task breakdown (atomic sub-tasks)

### 6.1 Typed action models
- Acceptance: `parse_action()` correctly discriminates all 7 action types;
  invalid actions raise `ValidationError`.
- Depends on: none
- Estimated complexity: M

### 6.2 Scratchpad
- Acceptance: hypotheses, confirmed issues, and dead ends are tracked
  per-episode; `summary()` returns a compact string.
- Depends on: none
- Estimated complexity: S

### 6.3 Reward engine
- Acceptance: all constants match REWARD_DESIGN.md; `compute_terminal_score()`
  produces identical results to legacy `_compute_final_score()`.
- Depends on: none
- Estimated complexity: M

### 6.4 Observation builder
- Acceptance: observations contain visible_rows, scratchpad_summary,
  step_budget_remaining, tool_usage_history (last 5), and latest_result.
  Noise injection is deterministic for same seed.
- Depends on: 6.1, 6.2
- Estimated complexity: M

### 6.5 Environment core
- Acceptance: `reset()` loads fixture data, runs detectors for ground truth;
  `step()` dispatches to all 7 action handlers; `state()` returns snapshot;
  FIX passes through SafetyFilter -> SMTVerifier.
- Depends on: 6.1–6.4
- Estimated complexity: L

### 6.6 FastAPI server
- Acceptance: all 6 HTTP endpoints return correct JSON shapes;
  `POST /step` parses actions via `parse_action()`.
- Depends on: 6.5
- Estimated complexity: M

### 6.7 Configuration updates
- Acceptance: `openenv.yaml` points at `dataforge.env.server:app`;
  `pyproject.toml` has `openenv` extra; `ARCHITECTURE.md` documents dependency.
- Depends on: 6.6
- Estimated complexity: S

## 7. Verification

- Unit tests: `tests/unit/test_tool_actions.py`, `test_reward.py`,
  `test_observation.py`, `test_scratchpad.py`, `test_sql_query.py`,
  `test_reward_design_parity.py`
- Integration tests: `tests/integration/test_openenv_spec.py`
- Property tests: `tests/property/test_reward_bounds.py`
- Coverage target: >= 90% line, >= 80% branch
- Regression: `tests/regression/test_env.py` passes unchanged

## 8. Acceptance gate (ALL must be TRUE to mark SPEC complete)

- [x] All Section 2 outcomes are met.
- [x] All Section 6 tasks have "passes".
- [x] Coverage thresholds (Section 7) are met.
- [x] No test in `tests/regression/` fails.
- [x] `DECISIONS.md` has an entry for the OpenEnv migration.
- [x] `REWARD_DESIGN.md` is not modified.

## Appendix A — Toy cases (write the FIRST failing tests from these)

### Case A.1: Reset returns valid observation
Input: `env.reset(seed=42)`
Expected output: `ResetResult` with `observation.step_budget_remaining > 0`,
  `observation.visible_rows` is not None, `observation.done == False`.
Reasoning: verifies the fundamental environment lifecycle starts correctly.

### Case A.2: INSPECT_ROWS returns data
Input: `env.step(InspectRows(action_type="INSPECT_ROWS", row_indices=[0, 1, 2]))`
Expected output: `StepResult` with `observation.visible_rows` containing
  data for rows 0, 1, 2.
Reasoning: confirms the primary data access mechanism works.

### Case A.3: SQL_QUERY executes and returns results
Input: `env.step(SqlQuery(action_type="SQL_QUERY", query="SELECT * FROM data LIMIT 5"))`
Expected output: `StepResult` with `observation.latest_result` containing
  up to 5 rows and no error.
Reasoning: validates DuckDB integration for read-only SQL.

### Case A.4: SQL_QUERY rejects writes
Input: `env.step(SqlQuery(action_type="SQL_QUERY", query="DROP TABLE data"))`
Expected output: `StepResult` with `observation.latest_result.error` containing
  a structured rejection.
Reasoning: ensures read-only enforcement.

### Case A.5: STAT_TEST with valid column
Input: `env.step(StatTest(action_type="STAT_TEST", test_type="zscore", column="rating"))`
Expected output: `StepResult` with numeric results in `latest_result`.
Reasoning: validates statistical test integration.

### Case A.6: STAT_TEST with invalid column
Input: `env.step(StatTest(action_type="STAT_TEST", test_type="zscore", column="nonexistent"))`
Expected output: `StepResult` with error in observation, episode NOT terminated.
Reasoning: ensures graceful error handling without episode termination.

### Case A.7: PATTERN_MATCH with valid regex
Input: `env.step(PatternMatch(action_type="PATTERN_MATCH", pattern=r"^\d{5}$", column="zip_code"))`
Expected output: `StepResult` with matching row/column candidates.
Reasoning: validates regex evaluation against data.

### Case A.8: PATTERN_MATCH with invalid regex
Input: `env.step(PatternMatch(action_type="PATTERN_MATCH", pattern="[invalid", column="zip_code"))`
Expected output: `StepResult` with error in observation, episode NOT terminated.
Reasoning: ensures malformed regex is caught safely.

### Case A.9: DIAGNOSE correct issue
Input: `env.step(Diagnose(action_type="DIAGNOSE", row=5, column="rating", issue_type="decimal_shift"))`
Expected output: `StepResult` with positive reward (>= R_DIAGNOSE = 0.10).
Reasoning: validates reward signal for correct diagnosis.

### Case A.10: FIX accepted after safety/SMT
Input: `env.step(Fix(action_type="FIX", row=5, column="rating", new_value="4.5", justification="Decimal shift correction"))` where row 5 has a known decimal_shift issue.
Expected output: `StepResult` with positive reward (>= R_FIX = 0.15).
Reasoning: validates the full fix pipeline including safety gate.

### Case A.11: Step-budget termination
Input: Execute `max_steps` actions.
Expected output: Final `StepResult` with `done=True` and terminal score.
Reasoning: confirms auto-finalize at budget exhaustion.

### Case A.12: Reward formula parity
Input: Episode with 3/5 issues detected, 2/3 fixable fixed, 1 false positive.
Expected output: `score = (3/5)*0.40 + (2/3)*0.60 - 1*0.05 = 0.24 + 0.40 - 0.05 = 0.59`
Reasoning: validates terminal score matches REWARD_DESIGN.md formula exactly.

### Case A.13: HTTP /health endpoint
Input: `GET /health`
Expected output: `{"status": "healthy", ...}`
Reasoning: validates OpenEnv discovery endpoint.

### Case A.14: HTTP /schema endpoint
Input: `GET /schema`
Expected output: JSON containing action and observation model schemas.
Reasoning: validates OpenEnv schema discovery.
