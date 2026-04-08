# Domain: Data storage & persistence

> Where and how state is durably stored

## Core Principles

- **Explicit Source of Truth per Field**: For every persisted lifecycle/risk/financial field, the authoritative source (external venue vs local DB vs derived) MUST be explicitly documented. If a field is mirrored, the reconciliation rule MUST be explicit.
- **Reconcile Before Side Effects**: If external state is authoritative for any field used in decisions (risk, scoring, order placement, settlement), reconciliation MUST run before those decisions.
- **Atomic Transactions for Multi-Write Mutations**: Lifecycle/risk/financial state mutations that touch multiple rows/tables MUST be wrapped in an explicit transaction boundary. Mutations MUST commit atomically or roll back entirely.
- **Concurrency Control Is Mandatory**: Any record that can be written by multiple tasks/processes MUST define concurrency control (locking, compare-and-swap/version columns, or unique constraints). Last-writer-wins without an explicit rule is prohibited.
- **Idempotent Writes for Retries/Replays**: Any persistence mutation that can be retried, replayed, or triggered by duplicate events MUST be idempotent, enforced via keys/constraints and/or state-transition guards.
- **Persistence Failures Must Be Observable and Fail the Operation**: Swallowed DB errors are prohibited. Persistence failures MUST fail the active operation and emit structured error telemetry.
- **Schema/Migration Safety**: Schema migrations MUST be planned with forward and rollback behavior. Migration steps that can corrupt or orphan state MUST be blocked unless a safe recovery path exists.
- **Rebuildability and Auditability**: For critical state, the system MUST define whether it can be reconstructed from external sources and/or append-only history. If not rebuildable, backup/restore expectations MUST be explicit.
- **Retention & Archival Policy**: Persistent data MUST define retention windows, archival behavior, and deletion rules (if any). Retention MUST be explicit for critical state and audit-relevant records.
- **Backup/Restore Policy (If Not Rebuildable)**: If critical state is not fully rebuildable from external authority or append-only history, a backup cadence, retention window, and restore procedure MUST be defined and periodically tested.

## Best Practices

- Enforce constraints at the database layer (foreign keys, unique constraints, CHECK constraints) rather than only in application code.
- Prefer explicit state-transition functions that enforce allowed transitions before writing.
- Keep migrations small, reversible where possible, and tested against representative data.

## Subchecklists

- [ ] Is the source of truth for every persisted lifecycle/risk/financial field explicitly documented?
- [ ] If external reconciliation applies, is it performed before risk/scoring/side-effect decisions?
- [ ] Are all multi-table or multi-row mutations wrapped in an explicit transaction?
- [ ] For any concurrently written records, is concurrency control defined (locking/versioning/constraints)?
- [ ] For any retried/replayed flows, are writes idempotent and enforced by constraints or guards?
- [ ] Are persistence failures surfaced (not swallowed) and do they fail the active operation?
- [ ] Are migrations planned with forward + rollback behavior (or an explicit recovery plan)?
- [ ] Can critical state be rebuilt (from external truth or append-only history), or is backup/restore explicitly defined?
- [ ] Are orphan/stale local records transitioned out of active states deterministically?
- [ ] Are retention windows and archival/deletion rules explicitly defined for critical persisted data?
- [ ] If critical state is not rebuildable, is there an explicit backup cadence + retention window + restore procedure?
- [ ] Is restore tested periodically (or as part of a deterministic gate) for any non-rebuildable critical state?

## Deterministic Checks

- Run `pytest tests/persistence/` (or equivalent) for transaction and idempotency tests.
- Verify foreign keys are enabled (SQLite: `PRAGMA foreign_keys = ON;`).
- Run an integrity check where applicable (SQLite: `PRAGMA integrity_check;`).
- Verify backup job exists and last backup timestamp is recorded (where applicable).
- Perform a restore drill against a test DB snapshot (where applicable).