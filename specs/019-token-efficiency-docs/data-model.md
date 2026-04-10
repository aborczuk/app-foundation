# Data Model: Deterministic Pipeline Driver with LLM Handoff

Entities, relationships, and state transitions for deterministic phase routing, LLM handoff control, and ledger-safe progression.

---

## Entities

### DriverRunContext

**Purpose**: Immutable snapshot of one orchestrator invocation for a feature.  
**Lifecycle**: Created at invocation start, active during one step execution, then terminal (`completed`, `blocked`, or `errored`).

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `run_id` | string | Yes | UUID or monotonic unique ID | Correlation root for this invocation |
| `feature_id` | string | Yes | Matches `NNN-*` branch/feature pattern | Lock and ledger partition key |
| `phase` | string | Yes | Must be valid manifest phase key | Current resolved phase |
| `step_name` | string | Yes | Manifest allowlisted step only | Deterministic route target |
| `started_at_utc` | string | Yes | ISO-8601 UTC timestamp | Start timestamp |
| `timeout_seconds` | integer | Yes | `>0`, from manifest/default policy | Execution limit for step |
| `lock_path` | string | Yes | `.speckit/locks/<feature_id>.lock` | Single-flight guard path |

**Example**:
```json
{
  "run_id": "run_20260409T203102Z_019_0001",
  "feature_id": "019",
  "phase": "plan",
  "step_name": "speckit.plan",
  "started_at_utc": "2026-04-09T20:31:02Z",
  "timeout_seconds": 90,
  "lock_path": ".speckit/locks/019.lock"
}
```

### StepResultEnvelope

**Purpose**: Canonical machine-readable result produced by deterministic step scripts.  
**Lifecycle**: Emitted by script, validated by orchestrator, persisted to sidecar on non-success paths.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `schema_version` | string | Yes | Supported contract version | Hard-block on unsupported versions |
| `ok` | boolean | Yes | Must align with `exit_code` semantics | Routing guard |
| `exit_code` | integer | Yes | One of `0`, `1`, `2` | Primary routing signal |
| `gate` | string/null | No | Required when `exit_code=1` | Gate identifier |
| `reasons` | array[string] | No | Required when blocked/tooling error | Deterministic remediation keys |
| `error_code` | string/null | No | Required when `exit_code=2` | Stable tooling failure code |
| `next_phase` | string/null | No | Present when step advances | State transition hint |
| `debug_path` | string/null | No | Sidecar diagnostics path | Used for drill-down on explicit request |
| `correlation_id` | string | Yes | Must equal `run_id` or child-scope ID | End-to-end traceability |

**Example**:
```json
{
  "schema_version": "1.0.0",
  "ok": false,
  "exit_code": 1,
  "gate": "requirements_checklist",
  "reasons": ["incomplete_checklist_items"],
  "error_code": null,
  "next_phase": null,
  "debug_path": "specs/019-token-efficiency-docs/.debug/plan-gate.json",
  "correlation_id": "run_20260409T203102Z_019_0001"
}
```

### LLMHandoffTemplate

**Purpose**: Deterministic template contract for generative phases; constrains LLM work to artifact fill-in rather than routing logic.  
**Lifecycle**: Generated when next step is generative, filled by LLM, then validated before success event append.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `handoff_id` | string | Yes | Unique per run + step | Trace key |
| `step_name` | string | Yes | Must be generative step in manifest | Contract target |
| `required_inputs` | array[string] | Yes | Absolute/relative artifact paths | Minimal context set |
| `output_template_path` | string | Yes | Template file path | LLM fill target |
| `completion_marker` | string | Yes | Deterministic marker for done-state | Parsed by orchestrator only |
| `correlation_id` | string | Yes | Must map to run context | Cross-artifact traceability |

### FeatureLockRecord

**Purpose**: File-backed single-flight lock metadata for one feature ID.  
**Lifecycle**: Acquired before step execution, refreshed while active, released on terminal run outcome.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `feature_id` | string | Yes | Matches run context | Lock ownership key |
| `owner` | string | Yes | PID or runner identity | Stale-lock diagnosis |
| `acquired_at_utc` | string | Yes | ISO-8601 UTC | Lock age tracking |
| `expires_at_utc` | string | Yes | ISO-8601 UTC | Stale-lock timeout policy |

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| `DriverRunContext` | `StepResultEnvelope` | emits | 1:1 per step invocation | One canonical parsed result per executed step |
| `DriverRunContext` | `LLMHandoffTemplate` | creates | 0:1 | Present only for generative phases |
| `DriverRunContext` | `FeatureLockRecord` | acquires | 1:1 (active) | Prevents concurrent runs per feature |
| `StepResultEnvelope` | pipeline ledger event | gates append | 0:1 | Success paths append required event; blocked/tooling paths do not append success |

---

## State Transitions

### DriverRunContext Lifecycle

```
initialized → running_step → validating_result → (completed | blocked | errored)
                               \
                                waiting_llm -> validating_artifact -> completed
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| `initialized` | `running_step` | lock acquired | lock file valid and not stale | start step process |
| `running_step` | `validating_result` | child script exits | exit code captured | parse envelope |
| `validating_result` | `completed` | `exit_code=0` and artifact validation pass | required artifacts exist and validate | append required ledger event; print `Done/Next/Blocked` |
| `validating_result` | `blocked` | `exit_code=1` | gate + reasons present | print blocked status contract |
| `validating_result` | `errored` | `exit_code=2` and post-rerun still failing | verbose rerun attempted once | persist sidecar + tooling error status |
| `validating_result` | `waiting_llm` | next step is generative | handoff template generated | emit minimal handoff contract |
| `waiting_llm` | `validating_artifact` | LLM marks template complete | completion marker present | deterministic artifact validation |
| `validating_artifact` | `completed` | artifact validation pass | ledger append succeeds | advance phase |

---

## Storage & Indexing

- **Primary storage**: filesystem artifacts + append-only JSONL ledger (`.speckit/pipeline-ledger.jsonl`)
- **Caching**: none; each invocation resolves live state from ledger + artifacts
- **Indexes**:
  - Ledger indexed by `feature_id` then append order (JSONL line order)
  - Sidecar diagnostics indexed by `correlation_id` in file name/path
  - Lock file keyed by `feature_id` (`.speckit/locks/<feature_id>.lock`)

---

## Concurrency & Locking

- **Read**: read-only scans of ledger/artifacts before execution; no speculative state caching
- **Write**: file-lock single-writer per feature; append-only ledger writes after deterministic validation
- **Conflict resolution**: second invocation for same feature returns deterministic blocked state (`feature_lock_held`) unless stale-lock timeout policy allows lock takeover with owner metadata preserved
