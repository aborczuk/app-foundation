# Domain: Resilience & continuity

> How the system survives failures

## Core Principles

- **Fail Closed on Ambiguous State**: When state is ambiguous, the system MUST not proceed with consequential side effects.
- **Defined Degraded Modes**: Degraded behavior MUST be explicit (what is disabled, what remains safe).
- **Dependency Exhaustion Considered**: Rate limits, timeouts, and saturation MUST be part of failure planning.
- **Prevent Retry Storms**: Retries MUST be bounded and coordinated with backoff/circuit breaking.
- **Recovery Is Part of Design**: Recovery steps (manual or automated) MUST be documented and testable.
- **Data Integrity Under Failure**: Failures MUST NOT leave partial writes or corrupted lifecycle state.
- **Operator Safety**: Manual intervention paths MUST be defined for critical stuck states.
- **RTO/RPO Expectations**: For critical state and workflows, recovery time and recovery point expectations MUST be stated (even if “best effort”).
- **Dependency Fallback Rules**: For each critical dependency, fallback behavior MUST be explicit (fail closed, fail open, degraded mode, or block).

## Best Practices

- Use circuit breakers for all external dependencies.
- Implement robust retry-with-exponential-backoff for idempotent operations.
- Prefer idempotent operations for retryable paths.
- Ensure zero-trust boundaries are safe during failure state.
- Practice rollback and recovery.

## Subchecklists

- [ ] Does the system fail gracefully?
- [ ] Is there clear observability for failure points?
- [ ] Are retry mechanisms in place for non-critical transient errors?
- [ ] Does ambiguous state block side effects?
- [ ] Are degraded modes explicitly defined?
- [ ] Are dependency exhaustion scenarios handled (timeouts, rate limits, saturation)?
- [ ] Are retry storms prevented (bounded retries, backoff, circuit breaker)?
- [ ] Are recovery steps documented and testable?
- [ ] Are partial-write scenarios prevented (transactions/idempotency) during failure?
- [ ] Is there a safe manual intervention/runbook path for stuck states?
- [ ] Are RTO/RPO expectations stated for critical flows/state?
- [ ] For each critical dependency, is fallback behavior explicitly defined (fail closed/open/degraded/block)?
- [ ] Are recovery steps validated in a deterministic test or procedural drill?

## Deterministic Checks

- Run failure-mode/timeout tests (or equivalent) for critical dependencies.
- Verify circuit breaker behavior where applicable.
- Run chaos tests (if available) to verify component isolation.
- Run a dependency-timeout test and confirm fallback mode matches the defined policy.