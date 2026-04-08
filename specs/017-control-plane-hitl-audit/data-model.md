# Data Model: Phase 3 HITL Pause/Resume + Lifecycle Auditability

Date: 2026-04-04  
Spec: [spec.md](spec.md)

## Entity: WorkflowCompletionPayload

Purpose:
- Normalized completion callback payload from workflow runtime to control plane.

Fields:
- `task_id: str`
- `workflow_type: str`
- `status: Literal["completed","failed","waiting_input","timed_out","cancelled"]`
- `summary: str`
- `details: str | None`
- `context_ref: str | None`
- `execution_policy: str | None`
- `run_id: str | None`
- `artifact_links: list[str]`
- `human_input_request: HumanInputRequest | None`

Validation rules:
- `task_id`, `workflow_type`, `status`, and `summary` are required.
- `human_input_request` is required when `status="waiting_input"`.
- Payload rejects unknown fields.

## Entity: HumanInputRequest

Purpose:
- Structured operator prompt recorded when automation pauses.

Fields:
- `prompt: str`
- `response_format: str` (default `text`)
- `timeout_at_utc: datetime | None`

Validation rules:
- `prompt` and `response_format` are required non-empty strings.

## Entity: PausedTaskRun

Purpose:
- Durable pointer from task to the paused workflow run awaiting operator input.

Fields:
- `task_id: str`
- `run_id: str`
- `workflow_type: str`
- `context_ref: str`
- `execution_policy: str`
- `requested_at_utc: datetime`
- `timeout_at_utc: datetime | None`
- `prompt: str`

Validation rules:
- One paused pointer per task at a time.
- Resume/cleanup can be scoped by both `task_id` and `run_id` for idempotency.

## Entity: ActiveTaskRun

Purpose:
- One-active-run guard for workflow execution per task.

Fields:
- `task_id: str` (PK)
- `run_id: str`
- `event_id: str`
- `state: Literal["running","released","stale"]`
- `acquired_at_utc: datetime`
- `released_at_utc: datetime | None`

Validation rules:
- At most one `running` row per `task_id`.
- Terminal completion/cancel/timeout must release active run lock.

## Entity: ProcessedEvent

Purpose:
- Durable idempotency record for webhook and resume/cancel paths.

Fields:
- `event_id: str` (PK)
- `task_id: str`
- `decision: str`
- `processed_at_utc: datetime`

Validation rules:
- Duplicate `event_id` inserts become `skip_duplicate`.
- Non-dispatch lifecycle events (`input_resumed`, `cancelled_by_operator`) still persist terminal decision.

## Entity: OrchestrationResult

Purpose:
- Internal terminal decision emitted by orchestration service.

Fields:
- `decision: Literal["dispatch","input_resumed","cancelled_by_operator","qa_passed","qa_failed_to_build","qa_blocked_after_retries","skip_duplicate","stale_event","reject_active_run","reject_scope","action_scope_violation","reject_missing_metadata","reject_signature","schema_mismatch","dispatch_failed","missing_criteria","qa_unblock_required"]`
- `reason_code: str`
- `task_id: str`
- `event_id: str`
- `workflow_type: str | None`
- `run_id: str | None`

Validation rules:
- Every terminal branch emits a stable `reason_code` for operator/audit surfaces.

## Entity: TaskOutcomeRecord (operator-visible)

Purpose:
- ClickUp comment/status update that records lifecycle transitions and outcomes.

Fields:
- `severity: Literal["info","warning","error"]`
- `summary: str`
- `details: str`
- `reason_code: str`
- `run_id: str | None`

Validation rules:
- No secrets or raw internal traces in visible fields.
- Timeout and cancellation paths must render explicit operator actionability.

## State Transitions

### Workflow run lifecycle (per task/run)

1. `none`
2. `running` (dispatch accepted, active lock acquired)
3. Optional `waiting_input` (completion callback with structured HITL request; paused pointer created; task set to waiting status)
4. `input_resumed` (operator response detected, resumed dispatch sent, paused pointer cleared)
5. Terminal:
   - `completed`
   - `failed`
   - `timed_out` (task moved to blocked status)
   - `cancelled_by_operator` (manual status move out of controlled statuses)
6. `released` (active lock released; paused pointer cleared)

### Manual cancel path

1. Task has `active_run` in `running`.
2. Webhook status transition moves from controlled status -> non-controlled status.
3. Control plane emits best-effort `/control-plane/cancel-run`.
4. Local active run released regardless of cancel endpoint response.
5. Terminal decision persisted as `cancelled_by_operator`.

## Invariants

1. Operator response can only resume when `active_run.run_id == paused_run.run_id`.
2. A `waiting_input` completion callback without `run_id` is rejected.
3. `HITL_RESPONSE:` parsing is case-insensitive and requires non-empty suffix to resume.
4. Timeout/cancel/completed/failed all clear paused state and release active lock.
5. Replay of identical webhook events never creates duplicate resume/cancel side effects.
