# Contract: HITL Pause/Resume + Cancellation Lifecycle (Phase 3)

Date: 2026-04-04  
Spec: [../spec.md](../spec.md)

## 1. Inbound Interface: Completion Callback

### Endpoint

- `POST /control-plane/workflow/completion`

### Required Headers

| Header | Required | Description |
| :----- | :------- | :---------- |
| `Content-Type` | Yes | Must be `application/json` |
| `X-Completion-Token` | Conditional | Required when `CONTROL_PLANE_COMPLETION_TOKEN` is configured |

### Request Body

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `task_id` | string | Yes | Target task |
| `workflow_type` | string | Yes | Workflow discriminator (`build_spec`/`qa_loop`) |
| `status` | enum | Yes | `completed`, `failed`, `waiting_input`, `timed_out`, `cancelled` |
| `summary` | string | Yes | Operator-safe summary |
| `details` | string | No | Optional details |
| `run_id` | string | Conditional | Required for `waiting_input`; recommended for all terminal callbacks |
| `context_ref` | string | No | Passed through for resume |
| `execution_policy` | string | No | Passed through for resume |
| `artifact_links` | string[] | No | Optional evidence links |
| `human_input_request` | object | Conditional | Required when `status=waiting_input` |

`human_input_request` shape:

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `prompt` | string | Yes | Prompt shown in operator-facing outcome |
| `response_format` | string | Yes | Example: `text`, `yes_no` |
| `timeout_at_utc` | datetime | No | If omitted, service computes using `CONTROL_PLANE_HITL_TIMEOUT_SECONDS` |

### Success Response

- `202 Accepted`

```json
{
  "accepted": true,
  "task_id": "task_123",
  "status": "waiting_input"
}
```

## 2. Inbound Interface: ClickUp Webhook (Operator Response + Manual Cancel)

### Endpoint

- `POST /control-plane/clickup/webhook`

### HITL Response Convention

Any of the following payload forms can supply operator response text:

1. `human_input_response` (or camelCase variant), top-level or nested in `routing` / `metadata`.
2. `comment_text` / `comment` / `text` that starts with prefix `HITL_RESPONSE:` (case-insensitive) and includes non-empty response body.

Example:

```json
{
  "event": "taskCommentPosted",
  "task_id": "task_123",
  "comment_text": "HITL_RESPONSE: Approved by operator"
}
```

### Manual Cancel Signal Rule

When a task has an active run and the webhook status transition is:
- `before` in workflow-controlled statuses, and
- `after` outside workflow-controlled statuses,

the event is treated as operator cancellation signal.

### Success Response Envelope

- `202 Accepted`

```json
{
  "accepted": true,
  "event_id": "evt_...",
  "decision": "input_resumed"
}
```

Possible `decision` values relevant to this phase:
- `input_resumed`
- `cancelled_by_operator`
- `skip_duplicate`
- `dispatch_failed`
- `schema_mismatch`
- plus existing phase-1/2 decisions

## 3. Outbound Interface: Resume Dispatch to n8n

### Endpoint

- Existing workflow route mapping:
  - `/control-plane/build-spec`
  - `/control-plane/qa-loop`

### Request Body (resume path additions)

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `task_id` | string | Yes | |
| `event_id` | string | Yes | |
| `workflow_type` | string | Yes | Normalized snake_case |
| `context_ref` | string | Yes | Derived from paused pointer |
| `execution_policy` | string | Yes | Derived from paused pointer |
| `resume_run_id` | string | Yes | Paused run to resume |
| `human_input_response` | string | Yes | Parsed operator response |
| `human_input_prompt` | string | Yes | Original prompt from paused pointer |

Non-2xx response is treated as `dispatch_failed` with `reason_code=resume_dispatch_failed`.

## 4. Outbound Interface: Cancel Run Request to n8n

### Endpoint

- `POST /control-plane/cancel-run`

### Request Body

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `task_id` | string | Yes | |
| `run_id` | string | Yes | Active run id to cancel |
| `event_id` | string | Yes | Source webhook event id |
| `reason` | string | Yes | `manual_status_change` |
| `occurred_at_utc` | datetime | Yes | Server UTC timestamp |

Rule:
- Cancel dispatch is best-effort; active run is still released locally even if cancel endpoint returns non-2xx.

## 5. Error Envelope

All endpoint errors use:

```json
{
  "error": {
    "code": "string",
    "message": "string",
    "action": "string"
  }
}
```

### Error Codes

| Code | HTTP | Rule |
| :--- | :--- | :--- |
| `invalid_payload` | 400 | Malformed JSON or missing required fields |
| `invalid_completion_token` | 401 | Completion callback token mismatch |
| `invalid_signature` | 401 | Webhook signature mismatch |
| `completion_write_failed` | 502 | ClickUp status/comment write failure during completion handling |
| `dispatch_failed` | 502 or `202` decision | n8n request rejected/timeout/transport failure |
| `schema_mismatch` | `202` decision | ClickUp schema/status mismatch in write path |
| `internal_error` | 500 | Sanitized service configuration/runtime failures |

Rules:
1. `message` and `action` must be operator-safe and non-secret-bearing.
2. No raw stack traces or token-bearing URLs are returned.
3. `202` decision outcomes still require ClickUp-visible lifecycle records.
