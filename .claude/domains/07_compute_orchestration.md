# Domain: Compute & orchestration

> How workloads are scheduled, executed, and shut down safely

## Core Principles

- **Explicit Ownership and Lifecycle**: Every spawned task/process MUST have explicit ownership and lifecycle handling: start, readiness signal, timeout/cancel, graceful shutdown, and force-kill fallback.
- **Structured Concurrency**: Concurrency MUST be structured (TaskGroup or equivalent). Untracked background tasks are prohibited.
- **Async Native**: Async code paths MUST use async-native APIs with explicit `await`; sync wrappers that spin nested event loops are prohibited in active async execution paths.
- **No Nested Event Loops**: Do not use `asyncio.run()` inside a coroutine — that blocks the event loop.
- **Backpressure Is Mandatory**: Producers MUST not overwhelm consumers. Queues/concurrency MUST be bounded.
- **Idempotent Work Under Retries**: Work that can be retried/replayed MUST be idempotent or guarded by state transitions.
- **Orphan Prevention**: Validation gates MUST fail if orphan processes/tasks remain after a run.
- **Crash/Restart Semantics**: Each background workflow MUST define behavior after crash/restart (resume, retry, or abort) explicitly.
- **Resource Limits & Quotas**: Workloads MUST define CPU/memory limits (or equivalent) and concurrency caps to prevent resource exhaustion.
- **Retry Budgets and Poison-Work Handling**: Repeated failures MUST not loop indefinitely. Retry budgets, dead-letter behavior, or explicit “abort and alert” rules MUST exist for failing workflows.

## Best Practices

- Use `asyncio.TaskGroup` or lifecycle management for concurrent tasks.
- Prefer `asyncio.TaskGroup` for structured concurrency.
- Ensure all subprocesses are reaped on exit.
- Use explicit timeouts for all network operations and long-running steps.
- Use durable checkpoints for long workflows where correctness requires it.

## Subchecklists

- [ ] Does the task have an explicit timeout?
- [ ] Are all spawned tasks registered for graceful shutdown?
- [ ] Is `await` used correctly for all async operations?
- [ ] Does every task/process have a clear owner and shutdown path?
- [ ] Are readiness, timeouts, and cancellation behavior explicit?
- [ ] Is concurrency bounded (TaskGroup limits / queue limits / semaphore)?
- [ ] Are background tasks tracked (no fire-and-forget)?
- [ ] Is work idempotent or guarded for retries/replays?
- [ ] Are crash/restart semantics defined for long-running workflows?
- [ ] Are orphan tasks/processes prevented and detected?
- [ ] Are CPU/memory limits (or equivalent) and concurrency caps explicitly defined?
- [ ] Is there an explicit retry budget for failing tasks/workflows?
- [ ] Is poison work handled (dead-letter, quarantine, or abort+alert) to prevent infinite loops?

## Deterministic Checks

- Run `pytest tests/lifecycle/` (or equivalent) to verify process/task reaping.
- Check runtime output for `"event loop is already running"` signals.
- Run a cancellation test to verify graceful shutdown.
- Run a forced-failure workflow and confirm retry budget + abort/alert behavior.