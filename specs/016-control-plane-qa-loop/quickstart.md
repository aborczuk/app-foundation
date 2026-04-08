# Quickstart: Phase 2 QA Verification and Rework Loop

Date: 2026-04-03  
Spec: [spec.md](spec.md)

## 1. Prerequisites

1. Phase 1 dispatch runtime is available and healthy.
2. Python 3.12 and project dependencies installed (`uv sync --group dev`).
3. n8n workflow for QA loop route is active.
4. ClickUp task schema includes acceptance criteria + QA failure context fields.

## 2. Environment

Set the same baseline environment used in Phase 1 plus QA route/status mapping values:

```bash
export CLICKUP_API_TOKEN="..."
export CLICKUP_WEBHOOK_SECRET="..."
export N8N_DISPATCH_BASE_URL="http://localhost:5678/webhook"
export CONTROL_PLANE_DB_PATH=".speckit/control-plane.db"

# Example QA loop mapping/config inputs
export CONTROL_PLANE_QA_TRIGGER_STATUS="Ready for QA"
export CONTROL_PLANE_BUILD_STATUS="Build"
export CONTROL_PLANE_QA_PASS_STATUS="Done"
export CONTROL_PLANE_QA_MAX_FAILURES="3"
export CONTROL_PLANE_COMPLETION_TOKEN="replace-with-internal-token"
```

Notes:
- `CONTROL_PLANE_QA_TRIGGER_STATUS`, `CONTROL_PLANE_BUILD_STATUS`, `CONTROL_PLANE_QA_PASS_STATUS` must be non-empty strings.
- `CONTROL_PLANE_QA_MAX_FAILURES` must be an integer greater than `0`.

## 3. Runtime Readiness Probe (Ingress)

Validate control-plane health endpoint returns control-plane payload (not n8n editor HTML):

```bash
curl -s -o /tmp/cp_health.out -w "%{http_code}\n" \
  https://67.205.175.182.nip.io/control-plane/health
cat /tmp/cp_health.out
```

Expected:

- HTTP `200`
- Body should be control-plane health JSON (or documented health payload)
- If body is n8n editor HTML, ingress route is misconfigured and must be fixed before implementation sign-off

## 4. Run Service Locally

```bash
uv run uvicorn clickup_control_plane.app:app --reload --port 8090
```

Webhook URL:

`http://localhost:8090/control-plane/clickup/webhook`

Completion callback URL for host-runner/webhook handlers:

`http://localhost:8090/control-plane/workflow/completion`

## 5. Validate Core QA Loop Behaviors

### Scenario A: QA pass

1. Move task to `Ready for QA` with valid acceptance criteria.
2. Verify QA workflow executes and returns pass.
3. Expect task status advances to configured pass status.

### Scenario B: QA fail with rework backflow

1. Trigger QA with a failing condition.
2. Expect task moved back to build status.
3. Verify structured failure report includes:
- issue description
- expected behavior
- observed behavior
- reproduction context

### Scenario C: 3-failure escalation

1. Repeat fail cycle until third consecutive fail.
2. Expect task enters blocked state requiring human intervention.
3. Verify automated re-dispatch is rejected while blocked.

### Scenario D: manual unblock reset

1. Human unblocks task via configured ClickUp action.
2. Verify failure counter resets.
3. Confirm task can re-enter build->QA cycle.

## 6. Test Commands

Run focused suites that should own Phase 2 behavior:

```bash
uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
uv run pytest tests/unit/clickup_control_plane -q
uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
```

## 10. Host Runner (Codex CLI) Callback Pattern

When webhook handlers run outside the `n8n` container, invoke Codex on host and post terminal completion:

```bash
scripts/codex_webhook_runner.py \
  --task-id task-123 \
  --workflow-type build_spec \
  --repo-path /Users/andreborczuk/ib-trading \
  --prompt-file /tmp/codex-prompt.txt \
  --completion-url http://localhost:8090/control-plane/workflow/completion \
  --completion-token "$CONTROL_PLANE_COMPLETION_TOKEN"
```

For local Docker Desktop, `n8n` container can reach host-runner at `host.docker.internal`.
For Linux deployment, explicitly configure host routing (`extra_hosts: host.docker.internal:host-gateway` or equivalent).

## 11. n8n Webhook Dispatch Wiring Gate (T012)

Current webhook handlers are wired as:

- `build-spec` (`e60ZZ7GYaNGPRSbs`): `Webhook -> Dispatch Codex Workflow (GitHub)`
- `qa-loop` (`XEaqgA0PsffcYlIu`): `Webhook -> Dispatch Codex Workflow (GitHub)`

Both dispatch `.github/workflows/codex-clickup-runner-callback-basic.yml` on `main`, passing:
- `task_id`
- `workflow_type` (`build_spec` or `qa_loop`)
- `event_id`
- `context_ref`
- `execution_policy`
- `occurred_at_utc`
- `callback_url` (`https://67.205.175.182.nip.io/control-plane/workflow/completion`)

Required setup:

1. n8n GitHub credential configured and attached to both dispatch nodes.
2. GitHub repo secrets configured:
- `OPENAI_API_KEY`
- `CONTROL_PLANE_COMPLETION_TOKEN`
3. Control-plane runtime has matching `CONTROL_PLANE_COMPLETION_TOKEN`.
4. Both n8n workflows published and active.

Verification evidence (2026-04-03):

- n8n manual executions:
- `build-spec`: execution ids `15` (success)
- `qa-loop`: execution id `13` (success)
- GitHub runs triggered from n8n:
- `23963801429` (`build_spec`) completed and callback accepted
- `23963836184` (`qa_loop`) completed and callback accepted
- Guard hardening for sandbox-block false-success path deployed in `main` commit `47c0b3f`
- Post-fix verification run:
- `23964277014` completed with callback accepted and ClickUp completion outcome written (`run_id=gh_run_23964277014`)

## 7. Operator Verification Checklist

1. QA never runs without acceptance criteria.
2. Every fail creates structured failure report on the task.
3. Third consecutive fail always produces blocked/escalation state.
4. Manual unblock is required before automation resumes.
5. Prior failure context remains visible through rework cycles.

## 8. Failure-Mode Troubleshooting

| Symptom | Likely Cause | Verification | Corrective Action |
| :--- | :--- | :--- | :--- |
| `missing_criteria` outcome | Acceptance criteria absent/empty | Inspect task fields/content before trigger | Populate criteria and retrigger |
| `qa_result_invalid` | QA workflow payload missing required fields | Inspect n8n execution output payload shape | Fix workflow response contract and redeploy |
| `qa_unblock_required` while retrying | Task still blocked after 3-fail escalation | Check blocked indicator/status on task | Perform explicit human unblock action |
| No transition back to build on fail | Status mapping mismatch | Compare configured build status vs workspace status name | Correct status mapping/config and retry |
| Health probe returns n8n HTML | Ingress route miswired | Compare `/control-plane/health` upstream target | Fix reverse-proxy/service routing before rollout |

## 9. Runtime Gate Verification Notes (2026-04-03)

Ingress/runtime gate verification completed on April 3, 2026:

```bash
curl -s -o /tmp/cp_health.out -w "%{http_code}\n" \
  https://67.205.175.182.nip.io/control-plane/health
cat /tmp/cp_health.out
# 200
# {"status":"ok"}
```

Additional in-network reverse-proxy check:

```bash
ssh -i /Users/andreborczuk/.ssh/do-control-plane root@67.205.175.182 \
  "cd /opt/automation && docker compose exec -T caddy wget -qO- \
  http://control-plane:8090/control-plane/health"
# {"status":"ok"}
```

## 12. Phase 2 Troubleshooting Addendum

| Symptom | Likely Cause | Verification | Corrective Action |
| :--- | :--- | :--- | :--- |
| `qa_result_invalid` webhook error | QA workflow returned payload missing `result` or missing `failure_report` for `fail` | Inspect n8n/GitHub payload body captured in run logs | Return strict QA response contract: `result` plus structured `failure_report` for fails |
| QA run returns `qa_unblock_required` without dispatch | Task still marked `blocked_human_required` | Inspect task metadata/status in ClickUp | Perform explicit human unblock before re-triggering QA |
| QA run returns `missing_criteria` | Acceptance criteria absent/empty | Check `acceptance_criteria` field/content in webhook task payload | Populate criteria and retrigger |
| QA run dispatches but no status transition occurs | ClickUp schema/status mismatch on update | Inspect control-plane logs for schema mismatch and task update responses | Align configured statuses (`Build`, `Done`, `Blocked`) with workspace statuses |

## 13. Dependency Security Recheck (Phase 2 Rollout)

Before production rollout:

1. Verify GitHub Actions secrets are present and scoped:
- `OPENAI_API_KEY`
- `CONTROL_PLANE_COMPLETION_TOKEN`
2. Verify control-plane runtime token parity:
- `.env` `CONTROL_PLANE_COMPLETION_TOKEN` matches GitHub Actions secret.
3. Confirm no secrets leaked in ClickUp outcome details:
- Completion/QA comments must not contain bearer tokens, auth headers, or stack traces.
4. Confirm least-privilege credentials:
- n8n GitHub token limited to required workflow-dispatch scope.
- ClickUp token limited to task read/update/comment operations used by control-plane.

## 14. Verification Notes (2026-04-03)

Executed suites after QA-loop foundational + US1 implementation changes:

```bash
uv run pytest tests/unit/clickup_control_plane -q
# 44 passed

uv run pytest tests/contract/test_clickup_control_plane_contract.py -q
# 7 passed

uv run pytest tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py -q
# 23 passed
```

Executor/callback validation evidence:
- n8n dispatch -> GitHub Actions run: `23963801429` (`build_spec`), `23963836184` (`qa_loop`)
- post-guardfix validation run: `23964277014`
- callback endpoint observed `202 Accepted` in control-plane logs for token-authenticated completion posts.
