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

### IV. Verification First (NON-NEGOTIABLE)
Changes to code or markdown-based process artifacts MUST be backed by deterministic verification
before they are treated as complete. This includes command docs, templates, scaffold scripts,
pipeline scripts, and feature code.

- **Test-first workflow changes**: If a change alters a markdown process, command contract,
  template, scaffold, or deterministic gate, update or add the corresponding smoke test before
  relying on the change.
- **Code changes require validation**: Changes to code MUST include the relevant automated test,
  smoke test, or deterministic gate that proves the change works as intended.
- **Process completeness**: A change is not complete until the relevant deterministic test or
  smoke test passes for the updated behavior.

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
python scripts/speckit_tasks_gate.py validate-format --tasks-file <FEATURE_DIR/tasks.md> --json
python scripts/speckit_spec_gate.py <checklist-status|extract-clarifications|validate-clarification-questions> ...
python scripts/speckit_plan_gate.py <research-prereq|spec-core-action|plan-sections|design-artifacts> ...
```
`plan` verifies requirements checklist completeness. `implement` verifies `e2e.md`, matching E2E script, `estimates.md`, and checklist status summary.
`speckit_implement_gate.py` verifies execution-time gates deterministically during `/speckit.implement`.
`speckit_tasks_gate.py` verifies tasks checklist syntax and phase/story label consistency.
`speckit_spec_gate.py` verifies specification checklist and clarification-question formatting.
`speckit_plan_gate.py` verifies plan preconditions and plan artifact/section completeness.
Gate reason-code catalog: `docs/governance/gate-reason-codes.yaml` (use reason codes for remediation routing).

**Compact-first command loading:**
- Load `## Compact Contract (Load First)` in speckit command docs first.
- Load `## Expanded Guidance (Load On Demand)` only when a deterministic gate fails or deeper rationale is requested.

All other quality checks remain command-specific (`/speckit.*`).

## Distributed Governance Model

Macro-principles (Human-First, Planning, Security) and SDLC Pipeline live in `CLAUDE.md` and this document. Deep implementation rules are sharded into 17 Domains (see section below).

## Authorized Taxonomy (The 17 Domains)

17 domains in `.claude/domains/` govern implementation rules: API integration, data modeling, storage, caching, client/UI, edge delivery, compute, networking, environment, observability, resilience, testing, identity, security, build pipeline, ops governance, code patterns.

> **CRITICAL RULE**: Do NOT read domain files globally. Query only domains explicitly tagged for your task's Domain Tags via `/speckit.checklist`.

## Canonical Workflow Pipeline

Machine-readable source of truth: `docs/governance/pipeline-matrix.yaml`.

Authoritative order is hard-gated by artifact prerequisites and ledger events. Minimal phase chain:
`/speckit.specify` → `/speckit.clarify` → `/speckit.research` → `/speckit.plan` → `/speckit.solution` → `/speckit.e2e` → `/speckit.implement` → `/speckit.checkpoint`/`/speckit.e2e-run` → `scripts/offline_qa.py` → `/speckit.close`.

Key enforcement invariants:
- `HARD_BLOCK_ARTIFACTS`: missing prerequisite artifacts block command entry.
- `FEASIBILITY_FIRST`: unresolved plan feasibility questions block solution phase.
- `QA_FIRST_CLOSE`: tasks cannot close without `offline_qa_passed`.

Behavioral state machine diagram remains in `.claude/constitution-workflow.md`.
Validation entrypoints remain `/speckit.checkpoint` and `/speckit.e2e-run`.

## Governance

This constitution supersedes all other practices. Amendments require updating this file with
version bump and rationale, and appending a SYNC IMPACT REPORT entry to
`constitution-changelog.md` (repo root). All specs, plans, task lists, automated pipelines, and
agent processes must comply with these principles.

Strategic governance principles (Human-First, Planning Behavior, Security First) are maintained
in `CLAUDE.md` under **Governing Principles**.

**Version**: 2.3.4 | **Ratified**: 2026-04-04 | **Last Amended**: 2026-04-13 (Verification First principle + testing-first workflow requirement for code and markdown-process changes)
