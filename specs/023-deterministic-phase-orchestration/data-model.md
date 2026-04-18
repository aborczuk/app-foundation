# Data Model: Deterministic Phase Orchestration

Entities, relationships, and state transitions for driver-managed phase execution.

---

## Entities

### PhaseExecutionRequest

**Purpose**: Driver input contract for one feature/phase execution attempt.  
**Lifecycle**: Created per invocation, resolved against ledger state, consumed by driver routing.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `feature_id` | string | Yes | `^\d{3}(-.*)?$` | Supports bare id (`023`) or slug. |
| `phase_hint` | string/null | No | Must be valid phase if present | Optional requested phase. |
| `approval_token` | string/null | No | Non-empty when required by gate | Required only for gated phase actions. |
| `dry_run` | boolean | Yes | Default `false` | Dry-run performs resolve/gate checks without mutation. |
| `correlation_id` | string | Yes | Immutable per run | Trace key for result + debug output. |

**Example**:
```json
{
  "feature_id": "023",
  "phase_hint": "plan",
  "approval_token": "phase:approved",
  "dry_run": false,
  "correlation_id": "run-023:plan"
}
```

### PhaseExecutionResult

**Purpose**: Deterministic envelope returned by the phase step runner.  
**Lifecycle**: Produced after routing + execution and consumed by validators/handoff.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `schema_version` | string | Yes | Must be supported (`1.0.0`) | Contract version pin. |
| `ok` | boolean | Yes | — | Logical success/failure. |
| `exit_code` | integer | Yes | One of `0,1,2` | Success / blocked / error. |
| `correlation_id` | string | Yes | Must match request correlation | Traceability invariant. |
| `gate` | string/null | Conditional | Required for blocked (`exit_code=1`) | Deterministic blocked reason family. |
| `reasons` | string[] | Conditional | Non-empty for blocked | Machine-readable gate reasons. |
| `next_phase` | string/null | Conditional | Required for success (`exit_code=0`) | Next phase handoff target. |
| `error_code` | string/null | Conditional | Required for error (`exit_code=2`) | Error taxonomy value. |
| `debug_path` | string/null | Conditional | Required for error (`exit_code=2`) | Sidecar/debug artifact path. |

### ValidationOutcome

**Purpose**: Deterministic validation result for generated artifact and execution envelope.  
**Lifecycle**: Produced before event append; governs emit/no-emit decision.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `valid` | boolean | Yes | — | Aggregate decision for emission gating. |
| `checks` | string[] | Yes | Controlled validator ids | Which checks executed. |
| `failures` | string[] | No | Empty when valid | Explicit contract violations. |

### EventAppendDecision

**Purpose**: Records whether completion event append is permitted and performed.  
**Lifecycle**: Derived from validation outcome and persisted through ledger append path.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `emit_allowed` | boolean | Yes | — | True only when validation passes. |
| `event_name` | string/null | Conditional | Required when allowed | Pulled from manifest `emits`. |
| `appended` | boolean | Yes | — | True only when ledger append exits successfully. |
| `append_error_code` | string/null | No | Populated on append failure | Prevents false-complete state. |

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| `PhaseExecutionRequest` | `PhaseExecutionResult` | produces | 1:1 | One request produces one terminal envelope. |
| `PhaseExecutionResult` | `ValidationOutcome` | validated_by | 1:1 | Validation evaluates envelope + artifact contract. |
| `ValidationOutcome` | `EventAppendDecision` | gates | 1:1 | Only valid outcomes can emit completion events. |

---

## State Transitions

### Phase Execution Lifecycle

```
Requested -> Orchestrated -> Extracted -> Scaffolded -> Synthesized -> Validated
                                                         |             |
                                                         |             +-> ValidationFailed (terminal, no emit)
                                                         +-> SynthesisFailed (terminal, no emit)
Validated -> Emitted -> HandedOff (terminal)
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| `Requested` | `Orchestrated` | Driver start | Feature id valid | Resolve ledger phase + gates. |
| `Orchestrated` | `Extracted` | Context extraction | Prerequisites pass | Collect normalized inputs. |
| `Extracted` | `Scaffolded` | Scaffold step | Template/paths resolve | Create or verify artifact shell. |
| `Scaffolded` | `Synthesized` | LLM Action | Approval gate satisfied | Fill artifact payload. |
| `Synthesized` | `Validated` | Deterministic validation | Envelope/artifact present | Run contract checks. |
| `Validated` | `Emitted` | Event append | Validation pass | Append ledger event. |
| `Emitted` | `HandedOff` | Handoff dispatch | Append succeeded | Return next phase contract. |

---

## Storage & Indexing

- **Primary storage**: `.speckit/pipeline-ledger.jsonl` for feature-level phase events.
- **Artifacts**: Feature-scoped markdown/contracts under `specs/<feature>/`.
- **Indexes**: No additional index layer required; sequence validation is deterministic by parser rules.

---

## Concurrency & Locking

- **Read**: Driver resolves phase state from append-only ledger snapshot at run start.
- **Write**: Event append is single-write operation performed only post-validation.
- **Conflict resolution**: Phase drift or lock conflicts return blocked/error envelopes; caller must rerun with corrected state.
