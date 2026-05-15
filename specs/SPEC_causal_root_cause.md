# SPEC: causal root-cause analyzer

> Status: Reviewed
> Owner: pranesh
> Last updated: 2026-05-15

## 1. Purpose

Add causal DAG construction and minimal root-cause identification for cascaded
tabular data-quality errors. Expose the analyzer to the RL environment through a
typed `ROOT_CAUSE` action without bypassing the existing repair safety pipeline.

## 2. Outcomes

- [x] `CausalDAG` represents column-level causal influence as an acyclic
  `networkx.DiGraph` with confidence and provenance on every edge.
- [x] PC discovery seeds declared functional dependencies as causal priors,
  handles missing values before calling `causal-learn`, and returns a DAG even
  when orientation is underdetermined.
- [x] Root-cause analysis returns the minimal subset of error indices that
  reaches every other selected error through the DAG.
- [x] `ROOT_CAUSE(error_indices: list[int])` parses as an eighth environment
  action and returns a structured observation.
- [x] Cascading fixture evaluation reaches precision >= 0.85 and recall >= 0.90.

## 3. Scope

**IN**:
- `dataforge/causal/dag.py` for DAG operations.
- `dataforge/causal/pc.py` for FD-prior and PC-backed causal discovery.
- `dataforge/causal/root_cause.py` for minimal root-set analysis.
- `dataforge/agent/tool_actions.py`, `dataforge/env/environment.py`,
  `dataforge/env/reward.py`, and `dataforge/env/server.py` updates for
  `ROOT_CAUSE`.
- Deterministic cascading `.csv` and `.json` fixtures under
  `tests/fixtures/cascading/`.

**OUT**:
- Automated repairs based on root-cause output.
- LLM-judged causal explanations.
- Publishing or deploying any package from local execution.

## 4. Constraints

- Python 3.11 / 3.12 compatibility.
- `causal-learn` must not receive NaN values.
- The analyzer is read-only; no disk mutation outside committed fixtures.
- Existing regression tests must pass unchanged.

## 5. Prior Decisions

- Z3 remains the SMT solver for verified repair actions.
- Environment action space is expanded from seven to eight typed actions; this
  supersedes the Week 6 "7 action types" statement only for `ROOT_CAUSE`.
- `R_ROOT_CAUSE = 0.10` is a dense bonus awarded only when task metadata exposes
  root labels and the action matches them.

## 6. Task Breakdown

### 6.1 DAG core
- Acceptance: adding an edge that would create a cycle raises `ValueError`;
  reachability and coverage are deterministic.
- Depends on: none.
- Complexity: M.

### 6.2 PC discovery with FD priors
- Acceptance: declared FDs always seed determinant -> dependent edges; missing
  values are imputed before `causal-learn` runs.
- Depends on: 6.1.
- Complexity: L.

### 6.3 Minimal root set
- Acceptance: for errors on `a`, `b`, `c` with `a -> b -> c`, the root set is
  only the selected `a` error; if `a` is absent, `b` becomes the root.
- Depends on: 6.1.
- Complexity: M.

### 6.4 Environment action
- Acceptance: `ROOT_CAUSE` validates non-negative indices, rejects out-of-range
  issue references, and returns structured result data.
- Depends on: 6.2, 6.3.
- Complexity: M.

## 7. Verification

- Unit tests: `tests/unit/test_causal_root_cause.py`,
  `tests/unit/test_tool_actions.py`, `tests/unit/test_reward.py`.
- Regression: `tests/regression/test_env.py` unchanged.
- Gates: `make lint`, `make type`, `make test-mapped FILE=<touched source>`,
  `make test`.

## 8. Acceptance Gate

- [x] All Section 2 outcomes are met.
- [x] `ARCHITECTURE.md` documents `networkx`, `causal-learn`, and `hyppo`.
- [x] `DECISIONS.md` records the eighth action decision.
- [x] No public function or class lacks type hints/docstrings.

## Appendix A - Toy Cases

### Case A.1: Minimal root through chain
Input: DAG `discount_pct -> order_total`, errors at both columns.
Expected: root set contains only the discount error.

### Case A.2: Missing upstream error
Input: DAG `discount_pct -> order_total`, selected error only at `order_total`.
Expected: root set contains `order_total`.

### Case A.3: Same-column tie
Input: two selected errors on `discount_pct`.
Expected: earliest selected index is the root for that column.
