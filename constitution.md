<!-- Amendment history: see constitution-changelog.md (repo root) -->

# analytics-platform Pipeline Constitution

## Core Principles

### I. Security Details
Each of the following sub-clauses MUST be verified individually in the Constitution Check:

- **I-a. No secrets in code/logs/committed files**: Credentials, tokens, and secrets MUST
  never appear in source code, log output (including HTTP request URLs with query params),
  or any committed file.
- **I-b. Secrets from env vars at runtime**: All secrets MUST be loaded exclusively from
  environment variables at runtime — never from config files, defaults, or hardcoded values.
- **I-c. Least privilege**: Every credential and component permission MUST be scoped to the
  minimum access required. Token scopes, IAM roles, and API permissions MUST be explicitly
  justified against what the feature actually needs.
- **I-d. Zero-trust boundaries identified**: Every trust boundary between components MUST be
  identified in the Architecture Flow diagram. All cross-boundary inputs are untrusted until verified.
- **I-e. External inputs validated**: All inputs arriving from outside the system (tool
  arguments, file paths, API responses, env vars) MUST be validated before use. Path traversal,
  injection, and malformed-input scenarios MUST be addressed.
- **I-f. Errors don't expose internals**: Error messages returned to callers MUST NOT include
  raw API responses, stack traces, credential fragments, or internal system state. Wrap with
  context; surface only what the caller needs to act.

### II. Reuse at Every Scale
Never write new code or design custom architecture where an existing solution already fits.

- **Code-level**: Before writing new code, check whether an existing utility, library, or pattern
  in the codebase already solves the problem. New dependencies and new architectural patterns
  require explicit justification.
- **Architecture-level**: Never design custom where an existing, well-maintained framework fits.
  Custom code carries a permanent maintenance, security, and testing burden. Prefer standard
  frameworks unless no viable option exists. Every build-custom decision MUST be explicitly
  justified against available alternatives.
  - **No-server-first evaluation (MANDATORY)**: Before designing any custom service, evaluate
    whether the feature's requirements can be met by wiring existing hosted services (GitHub
    Actions, n8n community nodes, ClickUp automations, Zapier, Make.com) using only
    tokens/credentials — no custom HTTP server required. This evaluation is performed in `/speckit.research`.

### III. Spec-First (NON-NEGOTIABLE)
Every feature begins with a completed spec. No implementation begins before the spec is reviewed
and approved. The spec owns the WHAT. The plan owns the HOW. They must not contradict.

Spec authoring rules and behavioral contract requirements are defined in `/speckit.specify`.

## Quality Gates

Use deterministic scripts for entry gates; avoid manual counting.

**Markdown reads (>100 lines):**
```bash
source scripts/read-markdown.sh
read_markdown_section <file_path> <section_heading>
```
Example: `read_markdown_section specs/020-analytics-platform/plan.md "External Ingress"`.

**Speckit entry gates:**
```bash
python scripts/speckit_gate_status.py --mode plan --feature-dir <FEATURE_DIR> --json
python scripts/speckit_gate_status.py --mode implement --feature-dir <FEATURE_DIR> --json
python scripts/speckit_implement_gate.py <task-preflight|validate-task-evidence|validate-offline-qa-payload|phase-gate> ...
```
`plan` verifies requirements checklist completeness. `implement` verifies `e2e.md`, matching E2E script, `estimates.md`, and checklist status summary.
`speckit_implement_gate.py` verifies execution-time gates deterministically during `/speckit.implement`.
All other quality checks remain command-specific (`/speckit.*`).

## Distributed Governance Model

Macro-principles (Human-First, Planning, Security) and SDLC Pipeline live in `CLAUDE.md` and this document. Deep implementation rules are sharded into 17 Domains (see section below).

## Authorized Taxonomy (The 17 Domains)

17 domains in `.claude/domains/` govern implementation rules: API integration, data modeling, storage, caching, client/UI, edge delivery, compute, networking, environment, observability, resilience, testing, identity, security, build pipeline, ops governance, code patterns.

> **CRITICAL RULE**: Do NOT read domain files globally. Query only domains explicitly tagged for your task's Domain Tags via `/speckit.checklist`.

## Canonical Workflow Pipeline

The following is the authoritative, **hard-gated** step order for every new feature. My behavior
is physically blocked by the existence of specific artifacts at each gate. 

### Full Feature Pipeline Matrix

| ID | Command | Input Prerequisite | Output Artifact | Audit Event |
| :--- | :--- | :--- | :--- | :--- |
| **01** | `/speckit.specify` | None (Request) | `spec.md` | `backlog_registered` |
| **02** | `/speckit.clarify` | `spec.md` | Updated `spec.md` | `discovery_completed` |
| **03** | `/speckit.research` | `spec.md` | **`research.md`** | `discovery_completed` |
| **04** | `/speckit.plan` | **`research.md`** | `plan.md` | `plan_started` |
| **05** | `/speckit.planreview` | `plan.md` | Updated `plan.md` (Open FQs section populated) | `planreview_completed` |
| **05a** | `/speckit.feasibilityspike` | `plan.md` (FQs section) | Updated `plan.md` (Technology Selection filled) + `spike.md` | `feasibility_spike_completed` |
| **05b** | *(plan phase complete)* | — | — | `plan_approved` |
| **06** | `/speckit.solution` | **`plan.md`** (FQs must be empty) | `tasks.md`, `estimates.md`, HUDs, acceptance tests | `solution_approved` |
| **06a** | `/speckit.tasking` *(sub-agent)* | `plan.md` + design artifacts | `tasks.md` | `tasking_completed` |
| **06b** | `/speckit.sketch` *(sub-agent)* | `tasks.md` + codebase | `estimates.md` (sketches), HUDs, `.speckit/acceptance-tests/` | `sketch_completed` |
| **06c** | `/speckit.estimate` *(sub-agent)* | `tasks.md` | `estimates.md` (scores) | `estimation_completed` |
| **06d** | `/speckit.solutionreview` *(sub-agent)* | all solution artifacts | `solutionreview.md` | `solutionreview_completed` |
| **07** | `/speckit.breakdown` | `tasks.md` (Size > 5) | Split `tasks.md` | `discovery_completed` |
| **09** | `/speckit.analyze` | `research`, `plan`, `tasks` | Consistency Report | `quality_guards_passed` |
| **10** | `/speckit.e2e` | `plan`, `tasks` | **`e2e.md`**, `scripts/e2e_*.sh` | `quality_guards_passed` |
| **11** | `/speckit.implement` | **`e2e.md`**, `tasks.md` | Code, `task-ledger.jsonl` | `task_started` |
| **12** | `/speckit.checkpoint` | Task in-progress | Test Output | `tests_passed` |
| **13** | `/speckit.e2e-run` | `scripts/e2e_*.sh` | Validation Verdict | `tests_passed` |
| **14** | `scripts/offline_qa.py` | Implementation diff | **`offline_qa_passed`** | `offline_qa_passed` |
| **15** | `/speckit.close` | **`offline_qa_passed`** | N/A | `task_closed` |

### The Physical State Machine

See [constitution-workflow.md](./.claude/constitution-workflow.md) for the Mermaid state diagram showing all phase dependencies and artifact flow.

### Validation Commands (invoke anytime)

```
/speckit.checkpoint [phase]  — Validate a phase checkpoint by running the software.
/speckit.e2e-run [section]   — Execute E2E pipeline (preflight | USn | full | verify).
```

**Enforcement Rules**:
- **Hard-Block Rule (v2.2.1)**: Behavior is physically constrained by artifact existence. Missing prerequisite (e.g., `research.md`) blocks dependent command (e.g., `/speckit.plan`).
- **Feasibility-First Rule (v2.3.0)**: Architecture assumptions never committed without probe. `/speckit.planreview` auto-writes Feasibility Questions to plan.md; `/speckit.feasibilityspike` proves all before `/speckit.solution` may run.
- **QA-First Rule (v2.2.1)**: No task may close in ledger without preceding `offline_qa_passed` event.

**Command-Specific Behaviors**:
- `/speckit.breakdown` is idempotent: exits cleanly if no 8/13-point tasks exist.
- `/speckit.solutionreview` CRITICAL findings block `solution_approved` — no exceptions. Affected sketches must be revised and solutionreview re-run.
- `/speckit.addtobacklog` is for ad-hoc tasks only. If change represents new requirement, run `/speckit.specify` to update spec afterward.
- Steps before `/speckit.plan` (specify, clarify) may iterate multiple times before proceeding.

**Quality Gates**:
- Never rely on human verification when a deterministic automated oracle is available.
- Never mark validation PASS when any principle-specific invariant from Principles X–XIII is violated (see `/speckit.checkpoint` and `/speckit.e2e-run`).

**Custom commands** (project-specific):

| Command | Purpose | Role |
|---------|---------|------|
| `/speckit.research` | Prior art, no-server eval, repo assembly map → research.md | Prerequisite for /speckit.plan |
| `/speckit.breakdown` | Split 8/13-pt tasks into ≤5-pt pieces | Part of tasking |
| `/speckit.e2e` | Generate E2E pipeline script and tests | Pre-flight gate |
| `/speckit.e2e-run` | Execute E2E validation suite | Verification phase |
| `/speckit.feasibilityspike` | Prove Open FQs before LLD | Blocks /speckit.solution |
| `/speckit.solution` | Orchestrate LLD (tasking → sketch → estimate → review) | Top-level LLD command |
| `/speckit.tasking` | Produce tasks.md from plan + artifacts | Sub-agent of solution |
| `/speckit.sketch` | Generate sketches, HUDs, acceptance tests | Sub-agent of solution |
| `/speckit.solutionreview` | DRY, compliance, test review, optimization | Sub-agent of solution |
| `/speckit.checklist` | Domain-specific task checklist | Task planning |
| `/speckit.addtobacklog` | Add ad-hoc task with fit check | Backlog management |
| `/speckit.split` | Split XL/L specs into independent phases | Feature scoping |
| `/speckit.constitution` | Update constitution.md + sync templates | Governance |
| `/speckit.taskstoissues` | Convert tasks.md → GitHub issues | Integration |
| `/speckit.trello-sync` | Sync tasks.md to Trello board | Integration |

## Governance

This constitution supersedes all other practices. Amendments require updating this file with
version bump and rationale, and appending a SYNC IMPACT REPORT entry to
`constitution-changelog.md` (repo root). All specs, plans, task lists, automated pipelines, and
agent processes must comply with these principles.

Strategic governance principles (Human-First, Planning Behavior, Security First) are maintained
in `CLAUDE.md` under **Governing Principles**.

**Version**: 2.3.0 | **Ratified**: 2026-04-04 | **Last Amended**: 2026-04-06 (Feasibility-First + LLD restructure)
