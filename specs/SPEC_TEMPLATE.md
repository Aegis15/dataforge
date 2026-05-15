# SPEC: <component-name>

> Status: Draft | Reviewed | Accepted | Superseded
> Owner: <handle>
> Last updated: YYYY-MM-DD

## 1. Purpose

Describe the component in one or two concrete sentences. State the user or
system problem it solves.

## 2. Outcomes

- [ ] <measurable pass/fail outcome>
- [ ] <measurable pass/fail outcome>

## 3. Scope

**IN**:

- <behavior this component must own>

**OUT**:

- <related behavior intentionally excluded>

## 4. Constraints

- Compatibility: Python `>=3.11,<3.13` unless a narrower surface requires more.
- Safety: applied repairs must preserve SafetyFilter -> SMTVerifier ->
  transaction-log ordering.
- Backward compatibility: existing regression tests must pass unchanged unless a
  spec and decision explicitly justify changing them.
- Documentation: public behavior changes require updates to `README.md`,
  `ARCHITECTURE.md`, and/or the relevant runbook.

## 5. Prior Decisions

- <link or name the relevant `DECISIONS.md` entry>
- <state any invariant this spec must not change>

## 6. Task Breakdown

### 6.1 <task name>

- Acceptance: <binary pass/fail criterion>
- Depends on: <list or "none">
- Estimated complexity: S | M | L

### 6.2 <task name>

- Acceptance: <binary pass/fail criterion>
- Depends on: <list or "none">
- Estimated complexity: S | M | L

## 7. Verification

Use the narrowest relevant checks while developing, then broaden before handoff.

- Unit tests: `tests/unit/test_<module>.py`
- Integration tests: `tests/integration/test_<surface>.py`
- Property tests, benchmark tests, or adversarial tests when the behavior
  affects safety, reversibility, performance, or provider boundaries
- Mapped gate: `make test-mapped FILE=<source_file>`
- Standard gates: `make lint`, `make type`, `make test`
- Documentation gate when docs change: `python scripts/ci/readme_truth.py`

## 8. Acceptance Gate

- [ ] All Section 2 outcomes are met.
- [ ] All required tests pass.
- [ ] No regression test fails.
- [ ] Public interfaces and docs are updated.
- [ ] `DECISIONS.md` records any non-obvious architecture/product choice.

## Appendix A - Toy Cases

Write the first failing tests from concrete toy cases.

### Case A.1: <short name>

Input: <concrete input>
Expected output: <concrete output>
Reasoning: <what bug this catches>

### Case A.2: <short name>

Input: <concrete input>
Expected output: <concrete output>
Reasoning: <what bug this catches>
