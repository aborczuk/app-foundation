# Contract: Webhook Intake and Dispatch Behavior (Phase 1)

Date: 2026-04-02  
Spec: [spec.md](../spec.md)

## 1. Inbound Interface: ClickUp Webhook

### Endpoint

- `POST /control-plane/clickup/webhook`

### Required Headers

| Header | Required | Description |
| :----- | :------- | :---------- |
| `X-Signature` | Yes | ClickUp signature used for webhook authenticity validation |
| `Content-Type` | Yes | Must be `application/json` |

### Request Body (normalized)

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `event` | string | Yes | ClickUp event type |
| `task_id` | string | Yes | Target task identifier |
| `history_items` | array | No | Used to derive status transition context |
| `space_id` | string | No | Used for allowlist validation |
| `list_id` | string | No | Used for allowlist validation |

### Success Response

- `202 Accepted`
- Body:

```json
{
  "accepted": true,
  "event_id": "evt_...",
  "decision": "dispatch|skip_duplicate|stale_event|reject_active_run|reject_scope|action_scope_violation|reject_missing_metadata"
}
```

## 2. Outbound Interface: n8n Trigger

### Endpoint

- Configured per `workflow_type` mapping (internal configuration file/env mapping)

### Request Body

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `task_id` | string | Yes | ClickUp task id |
| `event_id` | string | Yes | Internal dedupe key |
| `workflow_type` | string | Yes | Routing discriminator |
| `context_ref` | string | Yes | Spec/context pointer from task metadata |
| `execution_policy` | string | Yes | Policy profile |

### Expected Response

- `2xx` indicates accepted dispatch
- non-`2xx` results in `dispatch_failed` decision and operator-visible failure outcome

## 3. Outbound Interface: ClickUp Outcome Write

### Operation

- Write comment and/or status marker to originating task to keep operator visibility complete.

### Outcome Payload Shape

| Field | Type | Required | Notes |
| :---- | :--- | :------- | :---- |
| `severity` | enum | Yes | `info`, `warning`, `error` |
| `summary` | string | Yes | Single-line operator-facing summary |
| `details` | string | Yes | Actionable details; no internal secret data |
| `reason_code` | string | Yes | Stable machine-readable reason |
| `run_id` | string | No | Present when n8n trigger occurred |

## 4. Error Shape and Rules

All error responses from the webhook endpoint follow:

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
| `invalid_signature` | 401 | Emitted when `X-Signature` verification fails |
| `invalid_payload` | 400 | Emitted when required event/task fields are missing or malformed |
| `out_of_scope` | 202 | Event accepted but dispatch rejected due to allowlist constraints |
| `missing_metadata` | 202 | Event accepted but dispatch rejected due to missing routing metadata |
| `stale_event` | 202 | Event accepted but skipped because it predates the latest processed transition for the task |
| `duplicate_event` | 202 | Event accepted but skipped due to dedupe record |
| `active_run_exists` | 202 | Event accepted but skipped due to one-active-run guard |
| `action_scope_violation` | 202 | Event accepted but dispatch rejected because requested behavior exceeds task action-scope policy |
| `schema_mismatch` | 202 | Write path references unknown ClickUp schema fields/statuses |
| `dispatch_failed` | 502 | n8n trigger call failed after validation |
| `internal_error` | 500 | Unhandled internal failure (sanitized) |

Rules:
1. `message` must be operator-safe and must not expose secrets, raw stack traces, or upstream token-bearing data.
2. `action` must tell the operator what to do next when human intervention is needed.
3. `202` terminal decisions must still produce ClickUp-visible outcome records.
