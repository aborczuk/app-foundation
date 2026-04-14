# Data Model: CodeGraph Reliability Hardening

Entities, relationships, and state transitions for the local CodeGraph/Kuzu health and recovery model.

---

## Entities

### GraphHealthSnapshot

**Purpose**: Captures the current health classification for the local CodeGraph stack so CLI and MCP surfaces can return the same answer.
**Lifecycle**: Created on every doctor/smoke check, active only for the current probe result, superseded by the next probe.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `status` | enum | Yes | `healthy`, `stale`, `locked`, `unavailable` | Canonical readiness classification. |
| `checked_at` | datetime | Yes | ISO-8601 UTC | Timestamp of the probe. |
| `source` | string | Yes | `doctor`, `smoke`, `mcp-health` | Which surface produced the snapshot. |
| `detail` | string | No | Human-readable, short | Summary of the failure or healthy state. |
| `recovery_hint_id` | string | No | Must match a `GraphRecoveryHint.id` if present | Links to the recommended fix. |

**Example**:
```json
{
  "status": "locked",
  "checked_at": "2026-04-14T15:30:00Z",
  "source": "doctor",
  "detail": "Kuzu database lock present; safe refresh deferred.",
  "recovery_hint_id": "refresh-after-lock-clear"
}
```

### GraphLockRecord

**Purpose**: Describes a local lock or stale-session indicator that can block indexing or browsing.
**Lifecycle**: Observed from the local graph runtime, marked active while the lock exists, cleared when the runtime is healthy again.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `lock_id` | string | Yes | Immutable for the record instance | Local identifier for the lock observation. |
| `lock_type` | enum | Yes | `db-lock`, `session-lock`, `index-lock` | Distinguishes recovery strategy. |
| `path` | string | Yes | Must remain repo-local | Path or socket associated with the lock. |
| `observed_at` | datetime | Yes | ISO-8601 UTC | When the lock was detected. |
| `active` | boolean | Yes | Derived from probe | `false` when the lock is no longer present. |

**Example**:
```json
{
  "lock_id": "db-lock-20260414T153000Z",
  "lock_type": "db-lock",
  "path": ".codegraphcontext/db/kuzudb",
  "observed_at": "2026-04-14T15:30:00Z",
  "active": true
}
```

### GraphSnapshot

**Purpose**: Records a validated graph state that can be used as a last-known-good restore target.
**Lifecycle**: Created after a successful refresh/index validation, retained until superseded by a newer validated snapshot.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `snapshot_id` | string | Yes | Unique, immutable | Snapshot identity. |
| `db_path` | string | Yes | Must be repo-local | Path to the active Kuzu database. |
| `validated_at` | datetime | Yes | ISO-8601 UTC | When the snapshot was confirmed usable. |
| `source_commit` | string | No | Git SHA if available | Optional provenance for rebuilds. |
| `ready_for_use` | boolean | Yes | `true` only after validation passes | Prevents promoting unvalidated rebuilds. |

**Example**:
```json
{
  "snapshot_id": "snapshot-20260414T153000Z",
  "db_path": ".codegraphcontext/db/kuzudb",
  "validated_at": "2026-04-14T15:30:00Z",
  "source_commit": "abc1234",
  "ready_for_use": true
}
```

### GraphRecoveryHint

**Purpose**: Provides the next safe action when the graph is unhealthy.
**Lifecycle**: Returned alongside a non-healthy snapshot and retired when the next probe is healthy.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `id` | string | Yes | Stable identifier | Used for deterministic reporting. |
| `action` | enum | Yes | `retry`, `safe_refresh`, `safe_rebuild`, `fallback_to_files` | Recommended next move. |
| `summary` | string | Yes | Human-readable | Short operator-facing guidance. |
| `command` | string | No | Must be repo-local and non-destructive by default | Suggested command or invocation. |
| `preserves_last_good` | boolean | Yes | Must be `true` for rebuild paths | Indicates whether the last known good graph remains intact. |

**Example**:
```json
{
  "id": "refresh-after-lock-clear",
  "action": "safe_refresh",
  "summary": "Clear the lock, then refresh the graph with the safe index wrapper.",
  "command": "scripts/cgc_safe_index.sh src/mcp_codebase",
  "preserves_last_good": true
}
```

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| `GraphHealthSnapshot` | `GraphRecoveryHint` | `links_to` | 0:1 | Healthy snapshots have no recovery hint. |
| `GraphHealthSnapshot` | `GraphLockRecord` | `describes` | 0:N | A snapshot may reflect one or more active lock conditions. |
| `GraphSnapshot` | `GraphHealthSnapshot` | `produces` | 1:N | A validated snapshot can produce future health snapshots. |
| `GraphRecoveryHint` | `GraphSnapshot` | `preserves` | 0:1 | Safe rebuild hints must preserve the last-known-good snapshot. |

---

## State Transitions

### GraphHealthSnapshot Lifecycle

```
healthy → stale → locked → unavailable
   ↑         ↓         ↓          ↓
   └────── refreshed ──┴──── safe_refresh / safe_rebuild ─┘
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| `healthy` | `stale` | Graph probe detects outdated index state | Read-only probe succeeds | Return warning and recovery hint. |
| `stale` | `healthy` | Safe refresh completes and validates | Snapshot still matches repo-local state | Promote validated snapshot. |
| `stale` | `locked` | Lock metadata indicates active DB/session lock | Lock is active or subprocess unavailable | Block mutation; suggest safe retry/refresh. |
| `locked` | `unavailable` | Recovery path cannot safely attach to DB | No healthy fallback snapshot available | Fall back to file reads. |
| `unavailable` | `healthy` | Safe rebuild or refresh validates a replacement snapshot | Replacement snapshot passes checks | Swap in validated snapshot atomically. |

---

## Storage & Indexing

- **Primary storage**: `.codegraphcontext/db/kuzudb`
- **Operational metadata**: repo-local lock/state files under `.codegraphcontext/`
- **Caching**: local uv cache only, no remote cache dependency for health checks
- **Indexes**:
  - Kuzu graph indexes for code graph queries
  - Deterministic file/path lookups for fallback reads

---

## Concurrency & Locking

- **Read**: Read-only probes; no mutation during health checks
- **Write**: Atomic replacement only for refresh/rebuild paths
- **Conflict resolution**: If a lock or stale session exists, report it explicitly and preserve the last-known-good snapshot until a validated replacement is ready
