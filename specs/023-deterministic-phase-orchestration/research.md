# Research: Deterministic Phase Orchestration Boundary

Investigation of prior art, integration patterns, and existing code/packages that could reduce scope.

---

## Zero-Custom-Server Assessment

What no-server integration options exist? For each, which FRs does it cover?

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| GitHub Actions environment protection with required reviewers | FR-002, FR-003, FR-004, FR-005 | Workflow jobs pause for manual approval before proceeding; approval/rejection is first-class in GitHub environments. | FR-006 through FR-014 are not covered for repo-specific command/output contracts and ledger sequencing. |
| n8n wait/approval workflows (Wait node + webhook resume) | FR-002, FR-003, FR-004, FR-010 | Flow pauses and resumes on explicit external signal, enabling approval-style handoffs without custom server logic. | FR-001, FR-006 through FR-009, FR-011 through FR-014 require deterministic in-repo orchestration and validation/event semantics. |
| ClickUp automation webhooks | FR-002, FR-010 | No-code trigger/action automation can signal external systems and handoff state by webhook conditions. | Does not provide deterministic validate-before-emit guarantees (FR-007, FR-008, FR-009, FR-013) or producer-only command contract enforcement (FR-006). |

---

## Repo Assembly Map

Assemble pieces from multiple repositories to cover all FRs. Each row = one repo/file that covers one or more FRs.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| aborczuk/app-foundation | `scripts/pipeline_driver.py` | FR-001, FR-002, FR-003, FR-004, FR-005, FR-007, FR-010, FR-011, FR-014 | Existing orchestration spine already has step routing, runtime contract checks, and approval breakpoint seam; adapt instead of rewrite. |
| aborczuk/app-foundation | `scripts/pipeline_driver_state.py` | FR-002, FR-011, FR-012 | Current state resolution + lock/idempotency primitives can be extended for stricter phase boundary semantics. |
| aborczuk/app-foundation | `scripts/pipeline_ledger.py` | FR-008, FR-009, FR-011, FR-013 | Ledger append + sequence validation is already deterministic; should remain event-authority emitter after validation pass. |
| PrefectHQ/prefect | `src/prefect/flow_engine.py` | FR-001, FR-007, FR-011 | Large, mature flow engine with explicit state transitions/retry handling patterns; reference architecture only, not direct drop-in. Maintenance signal: ~22.2k stars, last push 2026-04-17T23:05:28Z. |
| temporalio/sdk-python | `temporalio/workflow.py` | FR-001, FR-011, FR-012 | Durable deterministic workflow/runtime model with replay and explicit workflow semantics; useful pattern source for deterministic progression. Maintenance signal: ~1.0k stars, last push 2026-04-17T22:41:00Z. |
| pytransitions/transitions | `transitions/core.py` | FR-001, FR-002, FR-010 | Lightweight state-machine primitives for explicit transitions and guarded triggers; viable if we need stricter transition encoding. Maintenance signal: ~6.5k stars, last push 2026-04-15T04:18:17Z. |
| cft0808/edict | `edict/backend/app/models/outbox.py` | FR-009, FR-013 | Concrete transactional outbox implementation pattern for validate-then-emit reliability; reference for emission safety controls. |

**After assembly**: which FRs remain uncovered and require net-new code?
- **FR-006**: Producer-only command-doc contract enforcement is repo-specific governance behavior and requires new local implementation.
- **FR-008**: Existing code has blocked/error paths but needs explicit contract changes to guarantee "no completion event on validation fail" across all migrated phases.
- **FR-014**: Requires explicit phase-contract documentation + enforcement wiring naming the pipeline driver command as the canonical executor.

---

## Package Adoption Options

Installable packages only (verified via `pip index versions`, `npm view`, or `gh api repos/`). Unverified entries belong in Repo Assembly Map.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| `transitions` | 0.9.3 | FR-001, FR-002, FR-010 | 2 | PyPI verified via `python3 -m pip index versions transitions` |
| `questionary` | 2.1.1 | FR-003, FR-004, FR-005 | 1 | PyPI verified via `python3 -m pip index versions questionary` |
| `temporalio` | 1.18.2 | FR-001, FR-011, FR-012 | 4 | PyPI verified via `python3 -m pip index versions temporalio` |
| `prefect` | 3.4.25 | FR-001, FR-007, FR-011 | 4 | PyPI verified via `python3 -m pip index versions prefect` |

---

## Conceptual Patterns

Non-code synthesis from web research. Standard approaches, common patterns, known mistakes.

- **Pattern**: Validate-then-emit via Transactional Outbox — Persist state mutation and outbound event intent atomically, then publish from outbox relay to avoid dual-write drift — covers: FR-007, FR-008, FR-009, FR-013 — requires custom server: yes (or background worker).
  - Source: https://learn.microsoft.com/en-us/azure/architecture/best-practices/transactional-outbox-cosmos
- **Pattern**: Durable human approval gate before execution — Pause workflow until explicit approve/reject signal, then resume deterministic path — covers: FR-002, FR-003, FR-004, FR-005, FR-010 — requires custom server: no (supported in managed workflow platforms).
  - Source: https://docs.github.com/actions/managing-workflow-runs/reviewing-deployments
- **Pattern**: Deterministic workflow state + replay/retry semantics — Use explicit workflow state transitions and deterministic replay constraints to enforce idempotent retries and traceable progression — covers: FR-001, FR-011, FR-012 — requires custom server: depends on chosen runtime (local or managed).
  - Source: https://github.com/temporalio/sdk-python
- **Pattern**: Task-scoped retry and transactional work units in orchestration — Retries and transactional semantics should be attached to small deterministic units, not monolithic phase blobs — covers: FR-007, FR-011 — requires custom server: no (library/runtime feature).
  - Source: https://docs.prefect.io/v3/concepts/tasks

---

## Search Tools Used

Log which tools and queries ran. Used to diagnose shallow results in future debugging.

- Agent A (Code Discovery):
  - Local semantic/code discovery: `uv run cgc find pattern -- "resolve_phase_state"`, `-- "enforce_approval_breakpoint"`, `-- "validate_sequence"`
  - GitHub repository discovery: `gh search repos "workflow orchestration"`, `gh search repos "PrefectHQ/prefect"`, `gh search repos "temporalio/sdk-python"`, `gh search repos "pytransitions/transitions"`
  - GitHub code discovery (pattern-level, not literal project terms): `gh search code "transactional outbox" --language=python`, `gh search code workflow orchestration language:python`, `gh search code questionary confirm language:python`
  - WebFetch on source files: Prefect `flow_engine.py`, Temporal `workflow.py`, Transitions `core.py`
- Agent B (Package Discovery):
  - Installability verification via PyPI index: `python3 -m pip index versions temporalio`, `transitions`, `questionary`, `prefect`
  - GitHub metadata checks via API: `gh api repos/<owner>/<repo> --jq '.stargazers_count'`
- Agent C (Conceptual Patterns):
  - Web searches for transactional outbox, approval gates, and deterministic orchestration/retry patterns
  - Source fetch from Microsoft Learn, GitHub Docs, Prefect docs, and Temporal SDK docs

---

## Unanswered Questions

Anything still unknown after all research. These become [NEEDS CLARIFICATION] in plan.md.

- Should phase-start permission be synchronous terminal input only, or also support deferred asynchronous approvals with timeout/escalation policy?
- For validate-before-emit, do we require a formal outbox-style persistence buffer, or is strict post-validation ledger append sufficient for this repository's reliability targets?
- Which command phases should migrate first to the producer-only contract boundary (all at once vs. phased rollout)?
