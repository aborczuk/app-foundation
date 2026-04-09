# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]
**Technology Direction**: [What category of solution is needed — describe the requirement, NOT a library name. e.g., "async broker connectivity library (Python asyncio, IBKR API)", "relational storage with ACID guarantees". Specific library selection belongs in Technology Selection below, after /speckit.feasibilityspike confirms choices.]
**Technology Selection**: TBD — filled by `/speckit.feasibilityspike` after probes confirm each choice. Format: "[category]: [library] [version] — confirmed by [FQ-NNN]"
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]
**Async Process Model**: [event loops/background tasks/processes, ownership, timeout/cancel/shutdown policy, and forbidden sync-in-async boundaries or N/A]
**State Ownership/Reconciliation Model**: [for live-vs-local state: source-of-truth per lifecycle field, reconcile checkpoints, drift handling policy, or N/A]
**Local DB Transaction Model**: [for local persisted state: transaction boundaries, rollback policy, idempotent retries, and no-partial-write guarantees, or N/A]
**Venue-Constrained Discovery Model**: [for venue-constrained integrations: metadata source, valid-object discovery flow, validated live-data request boundary, and discovery-failure policy, or N/A]
**Implementation Skills**: [Identify any registered workflow skills to invoke before implementing dependent tasks — e.g., SDK-specific scaffolders, code generators, or N/A (Constitution V: Reuse, VIII: Reuse Over Invention)]

## External Ingress + Runtime Readiness Gate *(mandatory)*

*GATE: Must pass before implementation. Re-validate in `/speckit.analyze`.*

Use this section for features that receive external callbacks/webhooks/events (or can become externally reachable in test/prod). If not applicable, mark all rows `N/A` with rationale.

| Check | Status | Notes |
|-------|--------|-------|
| Ingress strategy selected (`local tunnel`, `staging`, or `production`) and owner documented | | |
| Endpoint contract path defined (example: `/control-plane/clickup/webhook`) and expected method/auth documented | | |
| Runtime entrypoint readiness evidence captured (boot command + local probe command + observed result) | | |
| Secret lifecycle defined for ingress auth (source, storage, rotation owner) | | |
| External dependency readiness captured (upstream webhook registration path + downstream route readiness) | | |
| Evidence links recorded (commands/log snippets/screenshots/URLs) | | |

**Hard rule**: Any `❌ Fail` here blocks implementation readiness. `/speckit.tasks` MUST emit a `T000` gate task when any row is unresolved or when readiness must be proven in execution.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design (after security review step).*

<!--
  FORMAT RULES:
  - One row per principle that applies to this feature.
  - For principles with labeled sub-clauses in the constitution (e.g., III-a through III-f),
    use one sub-row per sub-clause. A single consolidated row for a multi-clause principle
    is NOT acceptable — each labeled clause must be verified independently.
  - Status: ✅ Pass | ❌ Fail | ⚠️ Conditional (mitigation required) | N/A
  - Any ❌ Fail blocks the plan. Any ⚠️ Conditional requires a mitigation note in Complexity Tracking.
  - Sub-clause labels come from the constitution. If the constitution adds or changes sub-clauses,
    update this table accordingly — do not invent sub-clauses not present in the constitution.
-->

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Human-First | | |
| II. AI Planning | | |
| III-a. Security: no secrets in code/logs/committed files | | |
| III-b. Security: secrets from env vars at runtime | | |
| III-c. Security: least privilege | | |
| III-d. Security: zero-trust boundaries identified | | |
| III-e. Security: external inputs validated | | |
| III-f. Security: errors don't expose internals | | |
| IV. Parsimony | | |
| V. Reuse | | |
| VI. Spec-First | | |
| VIII. Reuse Over Invention | | |
| IX. Composability | | |
| X. SoC | | |
| XIV. Observability | | |
| XV. TDD | | |
| XVIII. Async Process Management | | |
| XIX. State Safety and Reconciliation | | |
| XX. Local DB ACID and Transactional Integrity | | |
| XXI. Venue-Constrained Discovery | | |

## Behavior Map Sync Gate *(mandatory)*

*GATE: Must be filled before `/speckit.tasks` generation.*

| Check | Status | Notes |
|-------|--------|-------|
| Runtime/config/operator-flow impact assessed (`src/csp_trader/`, `config*.yaml`, runbooks/scripts) | | |
| If impacted, update target identified: `specs/001-auto-options-trader/behavior-map.md` | | |

## Architecture Flow *(mandatory)*

<!--
  REQUIRED: Generate a Mermaid flowchart after data-model.md is complete (Phase 1).
  Must cover all three layers in a single diagram:
  - Components: every module/service/agent listed in Project Structure
  - Data flow: edges labeled with the data or event being passed between components
  - States: key entity states and transitions from data-model.md

  Rules:
  - Every component in Project Structure MUST appear in this diagram
  - Every entity state defined in data-model.md MUST appear as a node or annotation
  - For async/background components, include lifecycle edges (start/ready/timeout-cancel/shutdown)
  - Use flowchart TD (top-down) direction
  - Label every edge with the data/event being passed
  - This diagram is a Constitution quality gate — plan cannot move to tasks without it
  - ASYNC RETURN PATH RULE: Every external service node MUST have both an outbound edge AND a labeled return path edge. A node with only an outbound edge is automatically flagged as a Feasibility Question by /speckit.planreview.
-->

```mermaid
flowchart TD
    [ComponentA] -->|[data/event]| [ComponentB]
    [ComponentB] -->|[entity: state → state]| [ComponentC]
```

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Open Feasibility Questions

<!--
  Populated by /speckit.planreview domain coverage scan.
  Cleared by /speckit.feasibilityspike after all probes pass.
  /speckit.solution hard-blocks if any item below is unchecked.

  Format per question:
  - [ ] **FQ-NNN**: [question text]
        Probe: [specific test to run to answer this]
        Blocking: [which architecture component or Technology Selection depends on this]
-->

*None — /speckit.planreview has not yet run, or all questions were confirmed by /speckit.feasibilityspike.*

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
