# Combined Plan - 048-composio-clickup-trigger-sync

_Feature: `048`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: l
- risk_level: medium
- reason: Use repo-local evidence to salvage parser/mapping logic, replace the old direct ClickUp transport with Composio, keep ledger-owned execution unchanged, and remove dead transport code after migration.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "api integration": "The active ClickUp transport path is changing from repo-local direct API usage to Composio-managed operations.",
      "code patterns": "The plan should salvage transport-neutral parsing/mapping logic and avoid reimplementing proven repo-side rules.",
      "data modeling": "The ClickUp projection must carry acceptance criteria, story relationship, parallel capability, estimate, and stable repo-to-ClickUp mappings.",
      "ops governance": "The implementation must keep `tasks.md` and the ledgers as source of truth while removing dead direct-transport code after migration.",
      "resilience": "Sync failures, trigger failures, and drift must preserve repo authority and remain retryable instead of corrupting task execution state.",
      "security": "External ClickUp triggers must not bypass ledger gating or allow accidental status edits to start unauthorized work.",
      "testing": "The migration needs deterministic coverage for sync, trigger gating, closeout reflection, and legacy-path removal."
    },
    "relevant": [
      "api integration",
      "data modeling",
      "resilience",
      "testing",
      "security",
      "ops governance",
      "code patterns"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "medium",
    "human_operator_dependency": "medium",
    "overall": "medium",
    "repo_uncertainty": "medium",
    "requirement_clarity": "low",
    "runtime_side_effect_risk": "medium",
    "state_data_migration_risk": "medium"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": true,
    "expanded_design_notes": true,
    "external_research": false,
    "net_new_surface": false,
    "strategy_reason": "Use repo-local evidence to salvage parser/mapping logic, replace the old direct ClickUp transport with Composio, keep ledger-owned execution unchanged, and remove dead transport code after migration."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [],
    "duplicate_reason": "",
    "risk_level": "medium",
    "tshirt_size": "l"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/src/mcp_clickup/artifact_parser.py`

stderr:
```text
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 393/393 [00:00<00:00, 7876.83it/s]
/Users/andreborczuk/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
```

### Term: composio

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/.speckit/runtime/tasking/codex-home/skills/.system/imagegen/scripts/image_gen.py`

stderr:
```text
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 393/393 [00:00<00:00, 7921.46it/s]
/Users/andreborczuk/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
```

### Term: clickup

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/src/clickup_control_plane/app.py`

stderr:
```text
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 393/393 [00:00<00:00, 11335.18it/s]
/Users/andreborczuk/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
```

### Term: trigger

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/src/mcp_codebase/indexer.py`

stderr:
```text
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 393/393 [00:00<00:00, 8069.52it/s]
/Users/andreborczuk/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
```

### Term: sync

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/edit_code.py`

stderr:
```text
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]
Loading weights: 100%|██████████| 393/393 [00:00<00:00, 7642.80it/s]
/Users/andreborczuk/.local/share/uv/python/cpython-3.12-macos-aarch64-none/lib/python3.12/multiprocessing/resource_tracker.py:279: UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
  warnings.warn('resource_tracker: There appear to be %d '
```

## Relevant Domains

### api integration
- Why it matters: The active ClickUp transport path is changing from repo-local direct API usage to Composio-managed operations.
- Required checklist prompts:
  - [ ] Does the integration discover the valid set via metadata first?
  - [ ] Are error response formats defined for all failure modes?
  - [ ] Are rate limiting requirements quantified with specific thresholds?
  - [ ] For each async external service: does the callback endpoint exist, is auth enforced on it, and is the incoming payload validated before processing?
  - [ ] Does every outbound call define explicit timeout behavior?
  - [ ] Is retry behavior defined per operation, including max attempts and backoff policy?
  - [ ] For any retried or replayable write, is idempotency explicitly enforced?
  - [ ] Are duplicate, delayed, stale, or out-of-order callbacks/responses handled safely?
  - [ ] Does ambiguous or partial external state block downstream side effects until reconciliation?
  - [ ] Are request/response and callback contracts versioned with compatibility expectations documented?
  - [ ] Is a correlation ID propagated across outbound requests and inbound callbacks/events?
  - [ ] Are non-idempotent operations explicitly marked, with duplicate-prevention behavior defined?
  - [ ] Is callback/webhook authentication explicitly defined and enforced before payload processing?
  - [ ] For any workflow/webhook integration (e.g., n8n), are the required secret(s)/token(s) explicitly named in the integration contract and enforced at the boundary (and not hardcoded)?
  - [ ] Are inbound and outbound payloads validated against explicit schemas rather than parsed loosely?
  - [ ] Is the source of truth for externally produced status/result state explicitly identified?

### data modeling
- Why it matters: The ClickUp projection must carry acceptance criteria, story relationship, parallel capability, estimate, and stable repo-to-ClickUp mappings.
- Required checklist prompts:
  - [ ] Does every field have an explicit source of truth or owner?
  - [ ] Are nullable or optional fields explicitly justified?
  - [ ] Are finite-state fields represented with enums or constrained literals instead of free text?
  - [ ] Are derived fields clearly separated from authoritative stored fields?
  - [ ] Are money, price, quantity, and ratio values modeled with precision-safe types and explicit units?
  - [ ] Does this schema change define compatibility and migration expectations?
  - [ ] Are immutable identity fields separated from mutable operational fields?
  - [ ] Is validation performed at ingress/egress boundaries rather than deferred downstream?
  - [ ] Are mirrored or copied fields documented with reconciliation expectations?
  - [ ] Is this schema scoped to a clear purpose instead of acting as a catch-all model?
  - [ ] Are inbound API/tool/integration payloads validated by Pydantic (or an explicitly approved equivalent) before use?
  - [ ] Are persisted-record reads decoded/validated into a schema model before domain/service logic uses them?
  - [ ] Are outbound integration payloads produced from validated schema models rather than hand-built dicts?

### resilience
- Why it matters: Sync failures, trigger failures, and drift must preserve repo authority and remain retryable instead of corrupting task execution state.
- Required checklist prompts:
  - [ ] Does the system fail gracefully?
  - [ ] Is there clear observability for failure points?
  - [ ] Are retry mechanisms in place for non-critical transient errors?
  - [ ] Does ambiguous state block side effects?
  - [ ] Are degraded modes explicitly defined?
  - [ ] Are dependency exhaustion scenarios handled (timeouts, rate limits, saturation)?
  - [ ] Are retry storms prevented (bounded retries, backoff, circuit breaker)?
  - [ ] Are recovery steps documented and testable?
  - [ ] Are partial-write scenarios prevented (transactions/idempotency) during failure?
  - [ ] Is there a safe manual intervention/runbook path for stuck states?
  - [ ] Are RTO/RPO expectations stated for critical flows/state?
  - [ ] For each critical dependency, is fallback behavior explicitly defined (fail closed/open/degraded/block)?
  - [ ] Are recovery steps validated in a deterministic test or procedural drill?

### testing
- Why it matters: The migration needs deterministic coverage for sync, trigger gating, closeout reflection, and legacy-path removal.
- Required checklist prompts:
  - [ ] Does a deterministic pass/fail oracle exist for this?
  - [ ] If yes, is it implemented as an automated gate (not manual confirmation)?
  - [ ] Are E2E tests run on real infrastructure where critical paths require it (not mocks)?
  - [ ] Is TDD methodology used (test written first) or explicitly justified if not?
  - [ ] Are tests deterministic (no timing races / hidden randomness / external nondeterminism)?
  - [ ] Are flaky tests tracked with an owner and expiry if temporarily quarantined?
  - [ ] Does every bug fix include a regression test targeting the bug class?
  - [ ] Are state transitions (including retries/duplicates/out-of-order) tested where applicable?
  - [ ] Is there at least one reality-check integration test for critical paths?
  - [ ] Are any gate waivers documented with rationale and expiry?
  - [ ] If E2E gates exist, is the E2E environment production-like or are differences explicitly documented?
  - [ ] Are fixtures/test accounts representative of real edge cases and permission models?

### security
- Why it matters: External ClickUp triggers must not bypass ledger gating or allow accidental status edits to start unauthorized work.
- Required checklist prompts:
  - [ ] Does this pull a secret/token from an environment variable (not code, logs, or committed files)?
  - [ ] Is input validation applied to all untrusted data?
  - [ ] Do all inbound webhook endpoints require authentication (no unauthenticated triggers), and are required secrets/tokens sourced from environment variables (not code or logs)?
  - [ ] Does the error message hide internal system secrets and internals?
  - [ ] Are token scopes/IAM permissions explicitly justified (least privilege)?
  - [ ] Are dependencies scanned for known vulnerabilities where applicable?
  - [ ] For new trust boundaries/integrations/privileged capabilities, was a threat model performed and documented?
  - [ ] Are threat mitigations reflected in tests/checklists (not only in prose)?

### ops governance
- Why it matters: The implementation must keep `tasks.md` and the ledgers as source of truth while removing dead direct-transport code after migration.
- Required checklist prompts:
  - [ ] Does a complete specification (WHAT) exist before implementation?
  - [ ] Has a reuse-first approach been seriously evaluated?
  - [ ] Is versioned documentation included with the feature?
  - [ ] Is there an Architecture Flow diagram for the change?
  - [ ] Is component ownership clear?
  - [ ] Are runbooks present/updated for critical operations?
  - [ ] Is incident response/on-call responsibility defined for critical systems?
  - [ ] Are escalation and communication paths defined (where applicable)?
  - [ ] Is there an ADR (or equivalent) for major architectural decisions?
  - [ ] Are learnings fed back into specs/tests/checklists?
  - [ ] Are any rule exceptions documented with rationale and expiry?

### code patterns
- Why it matters: The plan should salvage transport-neutral parsing/mapping logic and avoid reimplementing proven repo-side rules.
- Required checklist prompts:
  - [ ] Does every new public symbol have its signature (not just a comment) defined in the sketch before the task is implemented?
  - [ ] Are all new modules placed in the correct layer (domain, service, or adapter)? No cross-layer placement?
  - [ ] Does any single function in the sketch exceed 40 lines? If yes, split into smaller sub-tasks first.
  - [ ] Are there any circular imports introduced by this sketch?
  - [ ] Is any business logic (conditionals, decision-making) present in an adapter or file-IO layer? (prohibited)
  - [ ] Is any external IO (database, API, file system) called from domain or service layers? (prohibited)
  - [ ] Do all public functions have complete type hints (parameters and return type)?
  - [ ] Do all service-layer functions return typed objects, not raw dicts or tuples?
  - [ ] Are state transitions explicit and confined to named operations?
  - [ ] Are side effects isolated from decision logic?
  - [ ] Are public failure modes represented with meaningful typed errors/results?
  - [ ] Are public symbols documented (docstrings with inputs/outputs/errors and examples where non-trivial)?
  - [ ] Is formatting/lint enforcement configured as a gate (not advisory)?
  - [ ] Are error-handling conventions consistent within a module boundary (or explicitly documented if mixed)?

## Summary

Pivot the active ClickUp sync path to Composio while preserving the repository as the sole execution authority.

- Reuse the transport-neutral pieces of the existing `src/mcp_clickup` subsystem where they are already solving the right problem: spec/task parsing, projection shaping, mapping continuity, and reconciliation rules.
- Do not keep the old direct ClickUp client/CLI as the active runtime path. Composio becomes the managed transport layer for create/update/read operations.
- Keep `tasks.md`, the task ledger, and existing implement gating as the source of truth for what may start and what is complete.
- Add ClickUp publication only after tasking/breakdown stabilization has settled the task graph.
- Add ClickUp-triggered execution only through a repo-side ready-for-implement gate that resolves mapping first and then reuses existing ledger-owned implement selection.
- Reflect successful closeout back to ClickUp as a post-closeout side effect.
- Remove dead direct-transport code after the Composio path reaches parity and has deterministic coverage.

## Internal Research

- `.codex/config.toml` already registers `mcp_servers.composio`, so the managed bridge exists in the operator runtime, but the repository does not yet contain repo-local orchestration that uses it for ClickUp sync or triggers.
- `src/mcp_clickup/artifact_parser.py` already parses spec directories and `tasks.md` into `SpecArtifact`, `TaskGroup`, and `Task` records, but today it only captures task id/title and not the richer projection fields required by this spec (acceptance criteria, user story, parallel flag, estimate, artifact links).
- `src/mcp_clickup/sync_engine.py` already contains idempotent folder/list/task/subtask creation patterns and mapping update behavior. That logic is worth preserving conceptually, but it is currently bound to the direct ClickUp client surface.
- `src/mcp_clickup/__main__.py` is a standalone CLI that depends on `CLICKUP_API_TOKEN`, `CLICKUP_SPACE_ID`, and `.speckit/clickup-manifest.json`; that makes it a legacy transport/runtime entrypoint rather than an active Speckit phase hook.
- `scripts/speckit_implement_step.py` selects the next task from the task ledger and `tasks.md`, then starts or resumes only ledger-eligible work. This is the existing start gate that ClickUp requests must reuse rather than replace.
- `.claude/commands/speckit.implement.md` makes the task gate and ledger authoritative for completion, so ClickUp "done" reflection must happen after successful closeout rather than acting as an independent completion decision.
- The current repo evidence is sufficient to plan the migration without a separate research artifact: the main unknown is implementation effort, not product direction.

## Architecture Strategy

Treat the new path as a transport migration plus orchestration hook-in, not as a replacement of repo authority.

Use three layers:

1. Projection layer
   - Input: stabilized repo artifacts (`spec.md`, `plan.md`, `tasks.md`, ledger/mapping state)
   - Output: one canonical feature projection and task projection set
   - Responsibility: extract acceptance criteria, story relationship, parallel capability, estimate, and artifact links while keeping repo identifiers canonical

2. Transport adapter layer
   - Input: canonical projections and mapping state
   - Output: ClickUp-side create/update/read operations through Composio
   - Responsibility: perform managed transport operations, surface failures cleanly, and avoid leaking transport concerns into task/ledger logic

3. Orchestration hook layer
   - Input: phase completion, ClickUp ready-for-implement requests, and successful closeout events
   - Output: sync invocation, trigger evaluation, and done reflection
   - Responsibility: place sync after stabilization, evaluate trigger eligibility through existing ledger rules, and reflect done state after closeout

This architecture is necessary because the repo already has correct authority boundaries for task selection and completion. The migration should change transport and operator interaction, not source-of-truth ownership.

## Expanded Design Notes

Sync timing:

- The first ClickUp publication should happen only after estimate/breakdown stabilization has settled and task registration is complete.
- The sync should be treated as a deterministic post-stabilization step in the solution/tasking path rather than an ad hoc side command.
- If sync fails, the phase should surface the failure explicitly instead of silently pretending ClickUp is current.

Trigger behavior:

- Only a dedicated ClickUp `ready-for-implement` status transition should count as a start request.
- The trigger handler must resolve the ClickUp item back to one repo feature/task mapping before consulting the ledger.
- Eligibility must be decided by the existing task ledger rules; ClickUp cannot force parallelism, dependency bypass, or task order changes.
- Rejected requests must write a reason back to ClickUp so the operator can correct the state without inspecting repo internals.

Mapping and drift:

- Prefer reusing the current `.speckit/clickup-manifest.json` concept if it can be extended cleanly for the new Composio path.
- Mapping continuity matters more than preserving the old transport code. The migration should keep external IDs stable for already-synced work whenever possible.
- Drift detection must treat repo state as authoritative; ClickUp mismatches should produce repair/retry signals, not repo rewrites.

Closeout reflection:

- The repo should mark ClickUp done only after normal closeout succeeds.
- A failed ClickUp done update must not roll back the repo task; it should become a retryable post-closeout sync problem.

Legacy cleanup:

- Keep legacy direct-transport code only long enough to preserve or migrate useful parser/mapping logic.
- Remove unused direct ClickUp client/CLI/docs/tests once the Composio path has parity coverage and no active workflow calls the old path.

## Design Slices

### Slice PL-01 - Extract a transport-neutral ClickUp projection model
- Estimate: medium
- Implementation Directive: Refactor the reusable parts of `src/mcp_clickup/{__init__.py,artifact_parser.py,manifest.py}` into a canonical projection/mapping seam that can read stabilized repo artifacts and produce feature/task projections containing title, acceptance criteria, story relationship, parallel capability, estimate, artifact links, and stable repo-to-ClickUp identifiers without depending on the old direct ClickUp transport.

### Slice PL-02 - Replace direct ClickUp sync transport with Composio
- Estimate: high
- Implementation Directive: Introduce a Composio-backed ClickUp adapter and rewire the sync orchestration to create or update feature lists and mapped tasks from the canonical projection after stabilization, preserving idempotent mapping updates, retry-safe failure reporting, and explicit drift handling while removing the old direct transport from the active runtime path.

### Slice PL-03 - Gate ClickUp start requests through the existing implement authority
- Estimate: high
- Implementation Directive: Add a repo-side trigger path for the dedicated `ready-for-implement` status that resolves the mapped ClickUp task back to feature/task identifiers, evaluates eligibility through the existing task-ledger and implement-selection logic, starts the normal implement flow only for eligible tasks, and writes explicit rejection reasons back to ClickUp for ineligible or ambiguous requests.

### Slice PL-04 - Reflect closeout and retire dead direct-transport code
- Estimate: medium
- Implementation Directive: After successful implement closeout, update the mapped ClickUp task to done through Composio, add deterministic retry/reporting for post-closeout transport failures, and remove direct ClickUp transport code, docs, and tests that are no longer used once the new path has parity coverage.

## Plan Completion Summary

Selected depth: medium-risk architectural migration with repo-local planning only.

Why this was enough:

- The spec is clarified on the three decisions that would have materially changed the architecture: trigger mechanism, projection depth, and mapping continuity.
- The repository already contains the legacy ClickUp sync seams and the current implement authority seams, so a separate research artifact would repeat local evidence rather than reduce uncertainty.
- The remaining work is implementation decomposition: preserve useful parser/mapping logic, swap transport to Composio, wire trigger/closeout hooks, and then remove dead direct-transport code.

What the next phase should do:

- Decompose the four slices into executable tasks that keep `tasks.md` and the ledgers authoritative.
- Keep transport replacement and legacy cleanup sequenced so deletion happens only after Composio parity is verified.
- Make task contracts explicit about which old `mcp_clickup` logic is reused versus removed.
