# Domain: Testing & quality gates

> How you prevent regressions and defects

## Core Principles

- **Test-Driven Development (TDD)**: Tests MUST be written before implementation, using them to define behavior, edge cases, and failure modes.
- **Deterministic Tests by Default**: Tests MUST be deterministic; flaky tests are defects and MUST be fixed or quarantined with an explicit owner and expiry.
- **Tests as Blocking CI Gates**: In ALL critical code paths (auth, payments, financial/business logic, data access, agent tool calls), tests are mandatory CI gates.
- **Automation-First Validation Gates**: End-to-end (E2E) and checkpoint validation MUST prioritize deterministic automated gates over human confirmation.
- **PASS/FAIL Oracles**: If a deterministic pass/fail oracle exists, it MUST be implemented as an automated gate.
- **State-Transition Coverage**: Lifecycle/state machines MUST have tests covering transitions, retries, duplicates, and out-of-order scenarios.
- **Mocks Don’t Replace Reality Checks**: Critical integration paths MUST have at least one non-mocked validation path.
- **Regression Coverage for Bug Classes**: Fixes MUST include tests that prevent recurrence (not just the single observed instance).
- **Gate Failures Block**: Failing gates MUST block merges/releases unless explicitly waived with documented approval and expiry.
- **E2E Environment Parity**: If E2E tests gate releases, the E2E environment MUST be sufficiently production-like (dependencies, configs, permissions) or limitations MUST be explicitly documented.

## Best Practices

- Use `pytest` for unit/integration tests and `scripts/e2e_*.sh` (or equivalent) for user story validation.
- Every task MUST have a corresponding regression test.
- No task is complete without passing all existing unit tests in the module.
- Use time-freezing and seeded randomness for deterministic behavior.
- Treat test data as a first-class artifact; use representative edge-case fixtures.

## Subchecklists

- [ ] Does a deterministic pass/fail oracle exist for this?
- [ ] If yes, is it implemented as an automated gate (not manual confirmation)?
- [ ] Are E2E tests run on real infrastructure where critical paths require it (not mocks)?
- [ ] Is TDD methodology used (test written first) or explicitly justified if not?
- [ ] Are tests deterministic (no timing races / hidden randomness / external nondeterminism)?
- [ ] Are flaky tests tracked with an owner and expiry if temporarily quarantined?
- [ ] Does every bug fix include a regression test targeting the bug class?
- [ ] Are state transitions (including retries/duplicates/out-of-order) tested where applicable?
- [ ] Is there at least one reality-check integration test for critical paths?
- [ ] Are any gate waivers documented with rationale and expiry?
- [ ] If E2E gates exist, is the E2E environment production-like or are differences explicitly documented?
- [ ] Are fixtures/test accounts representative of real edge cases and permission models?

## Deterministic Checks

- Run `pytest` and confirm it reaches 0 failures.
- Run `/speckit.e2e-run` (or equivalent) and confirm it returns PASS.
- Run `ruff check .` (or equivalent) to ensure lint gates are enforced.
- If randomness is used, run tests with a fixed seed and verify consistent results.
- Run an E2E gate in the release-like environment and confirm parity assumptions hold.