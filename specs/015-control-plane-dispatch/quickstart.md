# Quickstart: Phase 1 Event-Driven Dispatch

Date: 2026-04-02  
Spec: [spec.md](spec.md)

## 1. Prerequisites

1. Python 3.12 and project dependencies installed (`uv sync --group dev`).
2. n8n endpoint available for dispatch target testing (local setup below if needed).
3. ClickUp API token and webhook signing secret available.

### Adopted Dependency Setup Check

Install and verify the adopted runtime stack used by this feature:

```bash
uv sync --group dev
uv run python - <<'PY'
import aiosqlite, fastapi, httpx, pydantic, uvicorn, yaml
print("deps_ok:", ", ".join(["aiosqlite", "fastapi", "httpx", "pydantic", "uvicorn", "pyyaml"]))
PY
```

Expected result:

- `uv sync` completes without dependency resolution errors.
- The smoke script exits `0` and prints `deps_ok: ...`.

### Local n8n setup (Docker Compose)

Run n8n locally:

```bash
docker compose -f docker-compose.n8n.yml up -d
docker compose -f docker-compose.n8n.yml ps
```

Open `http://localhost:5678`, finish the n8n first-run owner setup, and create/activate the webhook workflows used by this spec.

## 2. Environment

Set required environment variables:

```bash
export CLICKUP_API_TOKEN="..."
export CLICKUP_WEBHOOK_SECRET="..."
export CONTROL_PLANE_ALLOWLIST='{"space_ids":["..."],"list_ids":["..."]}'
export N8N_DISPATCH_BASE_URL="http://localhost:5678/webhook"
export CONTROL_PLANE_DB_PATH=".speckit/control-plane.db"
```

## 3. API Key Placement Checkpoint

Use the template and validate required keys are discoverable without printing secrets:

```bash
cp .env.control-plane.example .env.control-plane.local
# Edit .env.control-plane.local with real values, then:
set -a
source .env.control-plane.local
set +a

uv run python - <<'PY'
from clickup_control_plane.config import load_runtime_config

cfg = load_runtime_config()
scope_count = len(cfg.allowlist.space_ids) + len(cfg.allowlist.list_ids)
print(f"config_ok: db_path={cfg.control_plane_db_path} allowlist_entries={scope_count}")
PY
```

Expected result:

- Script exits `0`.
- Output confirms config loaded and scope count.
- No token/secret values are printed.

## 4. Run Service Locally

```bash
uv run uvicorn clickup_control_plane.app:app --reload --port 8090
```

Webhook URL for ClickUp:

`http://localhost:8090/control-plane/clickup/webhook`

## 5. Validate Core Behaviors

### Signature rejection

- Send payload with invalid signature header.
- Expect: `401 invalid_signature`, no n8n dispatch.

### Allowlist rejection

- Send valid signed payload from out-of-scope list.
- Expect: `202 out_of_scope`, ClickUp outcome written.

### Missing metadata rejection

- Send valid signed payload for task missing routing metadata.
- Expect: `202 missing_metadata`, ClickUp outcome written.

### Duplicate delivery idempotency

- Send the same valid payload twice.
- Expect first dispatch accepted, second returns `duplicate_event`.

### Single active run guard

- Trigger a second event while first run lock is active.
- Expect: `active_run_exists`, no second dispatch.

## 6. Test Commands

```bash
uv run pytest tests/unit/clickup_control_plane -q
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
```

## 7. Operator Verification Checklist

1. Every terminal decision writes a visible ClickUp outcome.
2. No secret-bearing values appear in logs.
3. Duplicate events do not create duplicate workflow runs.
4. Invalid signatures never reach dispatch layer.

## 8. Failure-Mode Troubleshooting (ClickUp + n8n)

| Symptom | Likely Cause | Verification | Corrective Action |
| :--- | :--- | :--- | :--- |
| `invalid_signature` (`401`) from webhook endpoint | `CLICKUP_WEBHOOK_SECRET` mismatch | Recompute local signature against canonical payload and compare with `X-Signature` | Update the runtime secret to match the active ClickUp webhook secret and retry |
| `dispatch_failed` (`502`) on accepted payload | n8n workflow endpoint unavailable or rejected | `curl -i "$N8N_DISPATCH_BASE_URL/control-plane/build-spec"` and inspect `docker compose -f docker-compose.n8n.yml logs --tail=100` | Start/restart n8n, activate workflow route, and confirm webhook path mapping |
| ClickUp probe/outcome calls return `401`/`403` | Invalid or under-scoped ClickUp API token | Trigger any non-duplicate webhook and inspect response/status in logs | Rotate token and ensure read/write task scope is enabled |
| `reject_missing_metadata` (`202`) for expected dispatch task | Missing/invalid `workflow_type`, `context_ref`, or `execution_policy` fields | Inspect task custom fields via ClickUp UI/API and confirm all three values are present | Populate required fields with supported values and re-trigger status transition |
| `reject_scope` (`202`) for in-scope task | Task `list_id`/`space_id` not present in `CONTROL_PLANE_ALLOWLIST` | Compare webhook payload IDs with loaded allowlist config | Update allowlist config, restart service, and retry |

## 9. Dependency-Security Recheck Checkpoint

Run this checkpoint before merge for control-plane dependency safety:

```bash
uv sync --group dev --frozen
uv run python - <<'PY'
from importlib.metadata import version
for dep in ("fastapi", "uvicorn", "httpx", "pydantic", "aiosqlite", "pyyaml"):
    print(f"{dep}=={version(dep)}")
PY
```

Checkpoint requirements:

1. Dependency sync succeeds with the lockfile (`--frozen`).
2. Version output is captured in release notes/PR discussion for audit traceability.
3. No unresolved high/critical advisories exist for the printed dependency set.
4. If an exception is required, document the mitigation and recheck date before approval.

## 10. Verification Notes (2026-04-03)

Control-plane verification suites executed on April 3, 2026:

```bash
uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
# 2 passed in 0.32s
uv run pytest tests/unit/clickup_control_plane -q
# 26 passed in 0.34s
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
# 12 passed in 0.72s
```

Result summary:

- Contract: `2` passed
- Unit: `26` passed
- Integration: `12` passed
- Total control-plane tests: `40` passed
