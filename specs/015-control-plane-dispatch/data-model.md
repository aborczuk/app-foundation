# Data Model: Phase 1 Event-Driven Dispatch

Date: 2026-04-02  
Spec: [spec.md](spec.md)

## Entity: ClickUpWebhookEvent

Purpose:
- Normalized representation of incoming ClickUp webhook payload used by policy and dispatch layers.

Fields:
- `event_id: str` — deterministic dedupe key source (derived from webhook payload fields)
- `task_id: str`
- `list_id: str | None`
- `space_id: str | None`
- `status_before: str | None`
- `status_after: str`
- `occurred_at_utc: datetime`
- `raw_payload: dict[str, Any]` (stored only for diagnostics with redaction rules)

Validation rules:
- Signature must be verified before model is accepted.
- `task_id` and `status_after` required.
- Timestamp defaults to receive time if upstream timestamp absent.

## Entity: RoutingMetadata

Purpose:
- Encodes workflow routing requirements present on a task.

Fields:
- `workflow_type: str` — maps to n8n workflow
- `context_ref: str` — pointer to spec/context artifact
- `execution_policy: str` — policy profile (e.g., strict/manual-safe)

Validation rules:
- All fields required for eligible trigger statuses.
- Unknown `workflow_type` values fail closed.

## Entity: DispatchDecision

Purpose:
- Single decision output for each webhook event.

Fields:
- `decision: Literal["dispatch","skip_duplicate","reject_active_run","reject_scope","reject_missing_metadata","reject_signature","schema_mismatch","dispatch_failed"]`
- `reason_code: str`
- `task_id: str`
- `event_id: str`
- `operator_message: str`
- `n8n_workflow_id: str | None`
- `created_at_utc: datetime`

Validation rules:
- `operator_message` is always required and must be safe for ClickUp comment visibility.
- `n8n_workflow_id` required only when `decision="dispatch"`.

## Entity: ActiveTaskRun

Purpose:
- Enforces single active workflow run per task (FR-006).

Fields:
- `task_id: str` (PK)
- `run_id: str`
- `event_id: str`
- `state: Literal["running","released","stale"]`
- `acquired_at_utc: datetime`
- `released_at_utc: datetime | None`

Validation rules:
- Only one `running` row per `task_id`.
- Release transitions require matching `run_id`.

## Entity: ProcessedEvent

Purpose:
- Durable dedupe record for webhook idempotency (FR-004).

Fields:
- `event_id: str` (PK)
- `task_id: str`
- `decision: str`
- `processed_at_utc: datetime`

Validation rules:
- Insert is atomic with lock acquisition path.
- Duplicate insert returns idempotent `skip_duplicate`.

## Entity: TaskOutcomeRecord

Purpose:
- Operator-visible task update payload written back to ClickUp.

Fields:
- `task_id: str`
- `severity: Literal["info","warning","error"]`
- `summary: str`
- `details: str`
- `reason_code: str`
- `linked_run_id: str | None`
- `written_at_utc: datetime`

Validation rules:
- Must never include tokens, internal stack traces, or raw unredacted payloads.
- Must provide actionable next step for non-success outcomes.

## State Transitions

### Dispatch lifecycle (per webhook event)

1. `received`
2. `validated_signature` or `rejected_signature`
3. `policy_checked`
4. terminal:
   - `dispatched`
   - `skipped_duplicate`
   - `rejected_active_run`
   - `rejected_scope_or_metadata`
   - `failed_schema_mismatch`
   - `failed_dispatch`

### Active run lifecycle (per task)

1. `none`
2. `running` (lock acquired)
3. `released` (normal completion/failure recorded)
4. `stale` (detected at startup reconciliation)
5. `released` (after stale cleanup)

## Invariants

1. A task cannot have more than one active run at any given moment.
2. A duplicate webhook event never triggers a second n8n dispatch.
3. Every terminal decision results in one operator-visible outcome write to ClickUp.
4. Signature-invalid requests never reach policy or dispatch layers.
