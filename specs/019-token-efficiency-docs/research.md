# Research: Deterministic Pipeline Driver with LLM Handoff

Investigation of prior art, integration patterns, and existing code/packages that could reduce scope.

---

## Zero-Custom-Server Assessment

What no-server integration options exist? For each, which FRs does it cover?

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| Local-first deterministic orchestrator (current repo pattern) | FR-001, FR-002, FR-003, FR-005, FR-006, FR-009, FR-010, FR-012, FR-013, FR-015, FR-016, FR-017, FR-021, FR-024, FR-025, FR-026 | Use local scripts + manifest + append-only ledgers; route by exit code and reason codes; emit minimal human-facing status and sidecar diagnostics. | FR-004 handoff contract standardization, FR-018 timeout policy normalization, FR-019 compensation policy formalization, FR-020 correlation-id propagation, FR-022 explicit approval checkpoints still need unified orchestrator wiring. |
| GitHub Actions orchestration with `concurrency` + environment protection | FR-014, FR-018, FR-022, FR-024 (partial) | Workflow/job-level concurrency groups enforce single in-flight pipelines; environment required reviewers provide human approval checkpoints without custom server. | Does not natively provide repository-local ledger sequencing semantics (FR-005/FR-010/FR-012/FR-013/FR-019/FR-020) unless custom glue is added. |
| Hosted workflow engine (Temporal Cloud style, worker still local process) | FR-013, FR-018, FR-019, FR-020 (pattern-level) | Durable execution model can improve retries/recovery/correlation; can be used as control-plane backend without operating own server. | Still requires workflow/worker code and integration complexity; does not replace spec/plan/task artifact governance directly. |

---

## Repo Assembly Map

Assemble pieces from multiple repositories to cover all FRs. Each row = one repo/file that covers one or more FRs.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| local: app-foundation | `scripts/pipeline_ledger.py` | FR-005, FR-010, FR-012, FR-013, FR-017, FR-019 (partial) | Existing feature-level state/event validation logic; primary base for orchestrator event guarantees. |
| local: app-foundation | `scripts/task_ledger.py` | FR-005, FR-012, FR-013, FR-015, FR-019 (partial) | Task-scoped sequencing/idempotency behavior and auto-index hooks can be adapted for driver-level flow control. |
| local: app-foundation | `command-manifest.yaml`, `.specify/command-manifest.yaml` | FR-006, FR-009, FR-015 | Existing allowlist/event declaration model is directly reusable as driver routing source of truth. |
| local: app-foundation | `scripts/speckit_gate_status.py`, `scripts/speckit_implement_gate.py`, `scripts/speckit_tasks_gate.py` | FR-002, FR-003, FR-010, FR-016, FR-017 | Existing deterministic gate envelope conventions and reason-code style should be normalized into one schema contract. |
| pytransitions/transitions | `transitions/core.py` | FR-001, FR-007, FR-011, FR-016 | Mature state-machine primitive for explicit phase transitions; useful for orchestrator transition graph. |
| jd/tenacity | `tenacity/__init__.py` (retry primitives) | FR-013, FR-018, FR-019 | Reusable retry/backoff policy wrapper for deterministic command execution and transient-failure handling. |
| tox-dev/filelock | `src/filelock/_api.py` | FR-014 | File lock primitive maps directly to clarified `.speckit/locks/<feature_id>.lock` requirement. |
| python-jsonschema/jsonschema | `jsonschema/validators.py` | FR-016, FR-017 | Deterministic schema validation for script envelopes and sidecar payloads. |
| pydantic/pydantic | `pydantic` models (package-level) | FR-003, FR-016, FR-017, FR-026 | Strict typed envelope models and backward-compatible schema-version parsing. |
| pydantic/pydantic-ai | `pydantic_ai` package modules | FR-004 (partial), FR-026 (partial) | Strong candidate for typed LLM handoff contracts and structured drill-down assistant flows; should be isolated from deterministic orchestration core. |

**After assembly**: which FRs remain uncovered and require net-new code?
- **FR-004**: standardized LLM handoff contract generator tied to pipeline state.
- **FR-008**: final policy balancing full JSON for code consumers vs stdout-minimal human output needs dedicated envelope rules.
- **FR-020**: end-to-end correlation-id propagation across all scripts/ledger writes.
- **FR-023**: deterministic one-time verbose rerun semantics for `exit_code=2`.
- **FR-024/FR-025/FR-026**: strict human-facing 3-line contract + sidecar drill-down interface.

---

## Package Adoption Options

Installable packages only (verified via `pip index versions`, `npm view`, or `gh api repos/`). Unverified entries belong in Repo Assembly Map.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| transitions | 0.9.3 | FR-001, FR-007, FR-011, FR-016 | 2 | Verified via `python3 -m pip index versions transitions` |
| tenacity | 9.1.2 | FR-013, FR-018, FR-019 | 1 | Verified via `python3 -m pip index versions tenacity` |
| filelock | 3.19.1 | FR-014 | 1 | Verified via `python3 -m pip index versions filelock` |
| pydantic | 2.12.5 | FR-003, FR-016, FR-017, FR-026 | 2 | Verified via `python3 -m pip index versions pydantic` |
| jsonschema | 4.25.1 | FR-016, FR-017 | 2 | Verified via `python3 -m pip index versions jsonschema` |
| pydantic-ai | 0.8.1 | FR-004 (partial), FR-026 (partial) | 4 | Verified via `python3 -m pip index versions pydantic-ai`; repo health: `pydantic/pydantic-ai` (stars 16201, pushed 2026-04-09) |

---

## Conceptual Patterns

Non-code synthesis from web research. Standard approaches, common patterns, known mistakes.

- **Pattern**: Concurrency-group single-flight orchestration — Use workflow/job concurrency keys with cancel-in-progress to prevent overlapping runs per feature/branch. — covers: FR-014, FR-018 — requires custom server: no
  - Source: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/control-the-concurrency-of-workflows-and-jobs

- **Pattern**: Environment required-reviewer approval gate — Use deployment protection rules to enforce explicit human approval for sensitive irreversible steps. — covers: FR-022 — requires custom server: no
  - Source: https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/deployments-and-environments

- **Pattern**: Trace/log correlation via stable context IDs — Include trace/span correlation metadata in logs/diagnostics for deterministic drill-down and cross-step debugging. — covers: FR-020, FR-026 — requires custom server: no
  - Source: https://opentelemetry.io/docs/specs/otel/logs/

- **Pattern**: Idempotent consumer / processed-message identity — Persist processed IDs and reject duplicates to keep retries safe and deterministic. — covers: FR-013, FR-019 — requires custom server: no
  - Source: https://microservices.io/patterns/communication-style/idempotent-consumer.html

- **Pattern**: Deterministic workflow logic constraints — Keep orchestration logic deterministic (no non-deterministic side effects in decision path) to preserve replay safety and predictable retries. — covers: FR-013, FR-018, FR-019 — requires custom server: optional
  - Source: https://www.nuget.org/packages/Temporalio/1.1.0

---

## Architecture Candidates

| Candidate | Constraint | FR coverage summary | Net-new code required | Maintenance surface |
|-----------|------------|---------------------|-----------------------|---------------------|
| A: No custom server (recommended) | Local deterministic CLI only; no hosted control plane additions | Covers FR-001..FR-026 via existing scripts/ledgers + new local orchestrator modules | Orchestrator command, envelope validator, lock handling, status-line renderer, handoff template bridge | Low; contained to repo scripts/docs/tests |
| B: Minimal service | Add thin HTTP service for approvals/callback coordination only | Covers FRs but adds network ingress/secret/runtime lifecycle requirements not required by current scope | Candidate A work plus service bootstrap, auth boundaries, deployment runbooks | Medium; ongoing service operations |
| C: Full service orchestration backend | Dedicated orchestration service with remote workers/state | Technically covers FRs with additional execution abstraction | Significant net-new state machine service, persistence and deployment stack | High; persistent infra + security burden |

**Decision**: Candidate A selected. FR coverage is complete without adding a network service, and it best satisfies token-efficiency and low-maintenance goals.

---

## Dependency Security

| Dependency | Target version floor | CVE posture | Rationale |
|------------|----------------------|-------------|-----------|
| `pydantic` | `>=2.0,<3.0` (repo baseline) | No blocker identified during research pass | Typed contract validation already in repo stack; avoids introducing new parser surface |
| `jsonschema` | `>=4.25.1` (optional) | No blocker identified during research pass | Optional secondary validator only; not required for MVP |
| `transitions` | `>=0.9.3` (optional) | No blocker identified during research pass | Useful for explicit state graphs, but MVP can use deterministic table routing |
| `tenacity` | `>=9.1.2` (optional) | No blocker identified during research pass | Retry helper for non-deterministic subprocess failure edges; optional in first increment |
| `filelock` | `>=3.19.1` (optional) | No blocker identified during research pass | Clarified lock semantics can be implemented with this package or equivalent file-lock primitive |
| `pydantic-ai` | `>=0.8.1` (future scope) | No blocker identified during research pass | Keep isolated to LLM handoff/drill-down surfaces; do not couple deterministic routing core |

---

## Search Tools Used

Log which tools and queries ran. Used to diagnose shallow results in future debugging.

- Agent A (Code Discovery): local repository inspection (`command-manifest.yaml`, ledger/gate scripts), scoped CodeGraph helper reads (`scripts/read-code.sh`), GitHub repo metadata checks via `gh repo view`.
- Agent B (Package Discovery): `python3 -m pip index versions` for `transitions`, `tenacity`, `pydantic`, `jsonschema`, `filelock`; PyPI/Web verification fallback.
- Agent C (Conceptual Patterns): Web research on GitHub Actions concurrency + approvals, OpenTelemetry log-trace correlation, idempotent-consumer pattern, deterministic workflow constraints.

---

## Unanswered Questions

Anything still unknown after all research.

None for plan stage. Deferred enhancements are tracked as non-blocking follow-ups:
- Evaluate whether dual-validator mode (`pydantic` + `jsonschema`) adds material value over `pydantic`-only MVP.
- Evaluate provider-neutral approval adapters after GitHub-native/manual approval flow lands.
- Evaluate `pydantic-ai` only for non-routing LLM assist surfaces after deterministic core is stable.
