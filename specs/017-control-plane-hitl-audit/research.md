# Research: Phase 3 HITL Pause/Resume + Lifecycle Auditability

Date: 2026-04-04  
Spec: [spec.md](spec.md)

## Zero-Custom-Server Assessment

Question:
- Can this phase be delivered with only hosted wiring (no custom server process)?

Assessment:
- Partial yes: ClickUp + n8n + GitHub Actions can run portions of trigger/execute/report loops.
- Full no for this phase: FR-002/003/004/007 require task-scoped pause-pointer state, replay-safe resume binding, and cancellation semantics tightly coupled to existing local advisory lock state.
- Existing control-plane service already implements those guarantees and is the smallest-change path.

Decision:
- Continue with existing control-plane service as the policy/state owner.
- Keep hosted systems (n8n/ClickUp) as execution and operator surfaces.

## Repo Assembly Map

Primary components assembled for this phase:
- `src/clickup_control_plane/app.py`: webhook/completion ingress, status/outcome writes, callback token checks.
- `src/clickup_control_plane/service.py`: orchestration decisions (resume, manual cancel, policy gates).
- `src/clickup_control_plane/state_store.py`: dedupe keys, active-run lock, paused-run pointer, transactional persistence semantics.
- `src/clickup_control_plane/dispatcher.py`: n8n dispatch and `/control-plane/cancel-run` transport.
- `src/clickup_control_plane/clickup_client.py`: operator-visible outcome templates and status updates.
- `tests/contract/test_clickup_control_plane_contract.py`: inbound/outbound contract envelope assertions.
- `tests/integration/clickup_control_plane/test_webhook_to_dispatch_flow.py`: end-to-end webhook -> decision -> dispatch/cancel -> lifecycle assertions.
- `tests/unit/clickup_control_plane/*.py`: schema/state/dispatcher/outcome unit invariants.

## Package Adoption Options

| Option | Installability | Coverage Fit | Decision |
| :----- | :------------- | :----------- | :------- |
| `n8n` | Verified (`npm view n8n version` -> `2.14.2`) | Execution runtime only; not policy/state engine | Adopted runtime (already in use) |
| `clickup-sdk` | Verified dry-run install | Thin API wrapper; low FR fit and downgrades `httpx` | Rejected |
| `pyclickup` | Verified dry-run install | Thin API wrapper; no lifecycle safety semantics | Rejected |
| `n8n-nodes-clickup` (claimed) | Not installable (`404`) | N/A | Rejected |
| Temporal | Verified active repo | Strong orchestration but high migration cost from current stack | Rejected for this phase |

## Conceptual Patterns

Patterns applied:
- Event-driven intake with explicit dedupe and one-active-run locking.
- HITL pause/resume using persisted paused-run pointer keyed by task/run.
- Operator override as first-class cancel signal (controlled -> non-controlled status transition).
- Fail-safe outcome reporting with sanitized operator-facing messages and stable reason codes.
- Transaction-first state mutation discipline (commit or rollback, no partial lifecycle writes).

## Prior Art

### Candidate 1: n8n core platform

- Name: n8n
- URL: https://github.com/n8n-io/n8n
- Language: TypeScript
- License: NOASSERTION (per repo metadata)
- Maintenance status: Active
- Installability verification:
  - `gh api repos/n8n-io/n8n --jq ...` -> `n8n-io/n8n|NOASSERTION|2026-04-03T23:10:37Z`
  - `npm view n8n version` -> `2.14.2`

FR coverage estimate:
- Covers runtime execution substrate for pause/resume/cancel webhook paths.
- Does not provide project-specific ClickUp policy checks, dedupe/lock guarantees, or operator outcome rendering.
- Coverage against 017 FRs: ~45%.

Decision:
- Adopted as execution runtime (already in architecture), not as policy/state owner.

### Candidate 2: Temporal

- Name: Temporal
- URL: https://github.com/temporalio/temporal
- Language: Go
- License: MIT
- Maintenance status: Active
- Installability verification:
  - `gh api repos/temporalio/temporal --jq ...` -> `temporalio/temporal|MIT|2026-04-04T01:55:13Z`

FR coverage estimate:
- Strong orchestration primitives for pause/resume/cancel.
- Requires net-new platform and migration away from existing n8n-centric workflow model.
- Coverage against 017 FRs: ~60% functionally, but high integration cost.

Decision:
- Reject for this phase (violates parsimony/reuse goals by adding new orchestration platform).

### Candidate 3: ClickUp API v2 demo repository

- Name: clickup-APIv2-demo
- URL: https://github.com/clickup/clickup-APIv2-demo
- Language: TypeScript
- License: NOASSERTION
- Maintenance status: Low-to-moderate (demo)
- Installability verification:
  - `gh api repos/clickup/clickup-APIv2-demo --jq ...` -> `clickup/clickup-APIv2-demo|NOASSERTION|2024-09-27T17:28:12Z`

FR coverage estimate:
- Helpful reference for API calls and webhook payload handling.
- Not a production policy/state framework.
- Coverage against 017 FRs: ~20%.

Decision:
- Reference only; do not adopt.

### Candidate 4: `clickup-sdk` (PyPI)

- Name: clickup-sdk
- URL: https://pypi.org/project/clickup-sdk/
- Language: Python
- License: Not evaluated deeply in this pass
- Maintenance status: Unclear
- Installability verification:
  - `uv pip install --dry-run clickup-sdk` -> resolves `clickup-sdk==0.1.6`; would downgrade `httpx` to `0.27.2`

FR coverage estimate:
- Thin API helper only.
- Does not satisfy dedupe/transaction/lifecycle invariants required by this feature.
- Coverage against 017 FRs: ~25%.

Decision:
- Reject due to low value and dependency friction.

### Candidate 5: `pyclickup` (PyPI)

- Name: pyclickup
- URL: https://pypi.org/project/pyclickup/
- Language: Python
- License: MIT
- Maintenance status: Unclear
- Installability verification:
  - `uv pip install --dry-run pyclickup` -> resolves `pyclickup==0.1.4`

FR coverage estimate:
- Basic wrapper for ClickUp API.
- No built-in pause/resume/cancel orchestration safety semantics for this system.
- Coverage against 017 FRs: ~20%.

Decision:
- Reject.

### Candidate 6: `n8n-nodes-clickup` package claim

- Name: n8n-nodes-clickup
- URL: npm registry lookup
- Installability verification:
  - `npm view n8n-nodes-clickup version` -> `404 Not Found`

Decision:
- Reject immediately (not installable on npm).

## Build vs Adopt Conclusion

No single external tool covers >=70% of 017 FRs with acceptable integration risk in this codebase.

Chosen approach:
- Reuse existing `clickup_control_plane` service + state store + dispatcher.
- Keep n8n as execution runtime.
- Implement HITL pause/resume/cancel lifecycle behavior in existing module boundaries.

## Key Technical Decisions

### Decision: Keep operator response convention as comment prefix `HITL_RESPONSE:`

Rationale:
- Already implemented and covered by integration tests.
- Human-readable and easy to enforce with lightweight validation.

Alternatives considered:
- Custom field-only responses (harder operator ergonomics).
- Free-form comment parsing with no prefix (ambiguous and unsafe).

### Decision: Persist paused-run pointer in local SQLite

Rationale:
- Required to safely bind operator response events to the correct paused run.
- Supports idempotent replay handling and cleanup on terminal completion/cancel.

Alternatives considered:
- In-memory paused state (unsafe across restarts).
- ClickUp-only state for paused context (no atomic lock coupling).

### Decision: Manual status move out of controlled statuses is an immediate cancel signal

Rationale:
- Directly satisfies FR-007 and human-first control requirement.
- Avoids silent continuation after operator override.

Alternatives considered:
- Ignore manual moves and keep running (rejected as operator-hostile).
- Soft warning without cancellation (rejected; ambiguous state).

## Dependency Security

Research snapshot date: 2026-04-04

| Dependency | Planned Baseline | Security Notes |
| :--------- | :--------------- | :------------- |
| `fastapi` | `>=0.115.0` | No blocker identified in this planning pass; keep pinned floor and monitor advisories before release |
| `uvicorn` | `>=0.30.0` | No blocker identified in this planning pass |
| `httpx` | `>=0.28.1` | Keep existing baseline; avoid wrapper choices that force downgrade (`clickup-sdk` dry-run downgraded to `0.27.2`) |
| `pydantic` | `>=2.0,<3.0` | No blocker identified in this planning pass |
| `aiosqlite` | `>=0.20,<1.0` | No blocker identified in this planning pass |
| `pytest` | `>=8.4.0` | Dev/test dependency; no blocker identified in this planning pass |
| `pytest-asyncio` | `>=0.24.0` | Dev/test dependency; no blocker identified in this planning pass |

Action:
- Re-run dependency/advisory check at merge time against locked versions and record outcome in PR notes.
