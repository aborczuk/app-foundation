# Quickstart: Phase 3 HITL Pause/Resume + Lifecycle Auditability

Date: 2026-04-04  
Spec: [spec.md](spec.md)

## 1. Prerequisites

1. Python 3.12 + project dependencies installed (`uv sync --group dev`).
2. Control-plane runtime from Phase 1/2 is already configured and reachable.
3. n8n webhook routes exist for:
   - `/control-plane/build-spec`
   - `/control-plane/qa-loop`
   - `/control-plane/cancel-run`
4. ClickUp list/status model includes:
   - build/qa statuses used by existing phases
   - `Waiting for Input` and `Blocked` statuses.

## 2. Environment

Load runtime env values (example names are exact):

```bash
export CLICKUP_API_TOKEN="..."
export CLICKUP_WEBHOOK_SECRET="..."
export CONTROL_PLANE_ALLOWLIST='{"space_ids":["..."],"list_ids":["..."]}'
export N8N_DISPATCH_BASE_URL="http://localhost:5678/webhook"
export CONTROL_PLANE_DB_PATH=".speckit/control-plane.db"
export CONTROL_PLANE_COMPLETION_TOKEN="..."
export CONTROL_PLANE_HITL_WAITING_STATUS="Waiting for Input"
export CONTROL_PLANE_HITL_BLOCKED_STATUS="Blocked"
export CONTROL_PLANE_HITL_TIMEOUT_SECONDS="86400"
```

Validation checkpoint:

```bash
uv run python - <<'PY'
from clickup_control_plane.config import load_runtime_config
cfg = load_runtime_config()
print("config_ok", cfg.hitl_waiting_status, cfg.hitl_blocked_status, cfg.hitl_timeout_seconds)
PY
```

## 3. Run Service

```bash
uv run uvicorn clickup_control_plane.app:app --reload --port 8090
```

Ingress endpoints:
- `POST /control-plane/clickup/webhook`
- `POST /control-plane/workflow/completion`
- `GET /control-plane/health`

## 4. Validate Phase 3 Behaviors

### A) Pause into waiting-input

1. Trigger a normal build/qa dispatch webhook for a scoped task.
2. Send completion callback:
   - `status=waiting_input`
   - include `run_id`
   - include `human_input_request.prompt`
3. Expected:
   - `202` accepted response with `status=waiting_input`
   - ClickUp status set to `Waiting for Input`
   - paused pointer stored in local DB.

### B) Operator response resumes paused run

1. Post webhook event with task comment:
   - `comment_text: "HITL_RESPONSE: <operator response>"`
2. Expected:
   - webhook returns decision `input_resumed`
   - second n8n dispatch includes `resume_run_id` and `human_input_response`
   - paused pointer is cleared.

### C) Timeout leads to blocked state

1. Send completion callback with:
   - `status=timed_out`
   - same `task_id` and run id.
2. Expected:
   - ClickUp status updated to `Blocked`
   - active lock released
   - next valid trigger can dispatch again.

### D) Manual status change cancels active run

1. While run is active, move task status from a controlled status to non-controlled status in ClickUp.
2. Expected:
   - webhook decision `cancelled_by_operator`
   - control-plane emits `POST /control-plane/cancel-run`
   - local active run released even if cancel endpoint fails.

## 5. Test Commands

```bash
uv run pytest tests/contract/test_clickup_control_plane_contract.py tests/unit/clickup_control_plane tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
```

## 6. Troubleshooting

| Symptom | Likely Cause | Verification | Corrective Action |
| :--- | :--- | :--- | :--- |
| `waiting_input` callback rejected (`400 invalid_payload`) | Missing `run_id` or `human_input_request` | Inspect callback JSON body | Send full structured waiting-input payload |
| Operator response ignored | Comment missing `HITL_RESPONSE:` prefix or empty response body | Inspect posted comment payload | Use exact `HITL_RESPONSE: <text>` convention |
| Timeout callback accepted but status not blocked | Invalid/missing `CONTROL_PLANE_HITL_BLOCKED_STATUS` mapping | Check env and ClickUp status names | Fix env/status mapping and retry callback |
| Manual status move does not cancel | `before`/`after` status transition not crossing controlled -> non-controlled boundary | Inspect webhook `history_items` | Confirm transition payload and controlled status configuration |
| Completion callback unauthorized (`401`) | Missing/wrong `X-Completion-Token` | Compare token with runtime env | Update caller secret and retry |

## 7. Verification Notes (2026-04-05)

Executed in this branch after Phase 3 + Phase 4 implementation:

```bash
uv run pytest tests/contract/test_clickup_control_plane_contract.py tests/unit/clickup_control_plane tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
```

Result: **89 passed**

Additional regression coverage added:
- `test_resume_dispatch_path_works_under_active_asyncio_event_loop` — resume path verified under active event loop (no nested `asyncio.run`).
- `test_no_orphan_state_records_remain_after_terminal_completion_callbacks` — all terminal statuses (completed, failed, timed_out, cancelled) clear both active_run and paused_run.
- `test_manual_cancel_clears_active_and_paused_state_even_when_cancel_endpoint_fails` — state cleanup verified even when n8n cancel endpoint returns 503.

Pyright result: `0 errors, 0 warnings, 0 informations` across all touched modules.
