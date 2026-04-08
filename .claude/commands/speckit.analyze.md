---
description: Perform a non-destructive cross-artifact consistency and quality analysis across spec.md, plan.md, and tasks.md after task generation.
handoffs:
  - label: Generate E2E Artifacts (if missing)
    agent: speckit.e2e
    prompt: Generate E2E testing pipeline artifacts for this feature
    send: false
  - label: Implement Project
    agent: speckit.implement
    prompt: Start the implementation in phases
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Identify inconsistencies, duplications, ambiguities, and underspecified items across the three core artifacts (`spec.md`, `plan.md`, `tasks.md`) before implementation. This command MUST run only after `/speckit.solution` has successfully produced a complete `tasks.md`.

## Operating Constraints

**STRICTLY READ-ONLY**: Do **not** modify any files. Output a structured analysis report. Offer an optional remediation plan (user must explicitly approve before any follow-up editing commands would be invoked manually).

**Constitution Authority**: The project constitution (`constitution.md`) is **non-negotiable** within this analysis scope. Constitution conflicts are automatically CRITICAL and require adjustment of the spec, plan, or tasks—not dilution, reinterpretation, or silent ignoring of the principle. If a principle itself needs to change, that must occur in a separate, explicit constitution update outside `/speckit.analyze`.

## Execution Steps

### 1. Initialize Analysis Context

Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` once from repo root and parse JSON for FEATURE_DIR and AVAILABLE_DOCS. Derive absolute paths:

- SPEC = FEATURE_DIR/spec.md
- PLAN = FEATURE_DIR/plan.md
- TASKS = FEATURE_DIR/tasks.md

Abort with an error message if any required file is missing (instruct the user to run missing prerequisite command).
For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

### 1a. Checklist Readiness Gate (MANDATORY — hard block)

- Check whether `FEATURE_DIR/checklists/requirements.md` exists.
- If `FEATURE_DIR/checklists/` exists, scan all checklist files and count incomplete items (`- [ ]`).
- **If `requirements.md` is missing OR any checklist item is incomplete**: **STOP immediately** and report checklist status (including incomplete counts) with this guidance:
  - `"/speckit.analyze cannot proceed until specification checklists are complete."`
  - `"Complete all checklist items in FEATURE_DIR/checklists/ (including requirements.md), then re-run /speckit.analyze."`
- Do **not** continue to artifact analysis while this gate fails.

### 1b. External Ingress + Runtime Readiness Gate (MANDATORY when ingress applies)

- Inspect `plan.md` for `## External Ingress + Runtime Readiness Gate`.
- Detect whether ingress/webhook/callback/public endpoint behavior is in scope using `spec.md`, `plan.md`, and `tasks.md`.
- If ingress applies:
  - ERROR if the gate section is missing.
  - ERROR if any gate row is blank.
  - Treat any `❌ Fail` row as a **CRITICAL** blocker for implementation readiness.
- If ingress does not apply:
  - Gate may be `N/A`, but rationale must be explicit.

### 2. Load Artifacts (Progressive Disclosure)

Load only the minimal necessary context from each artifact:

**From spec.md:**

- Overview/Context
- Functional Requirements
- Non-Functional Requirements
- User Stories
- Edge Cases (if present)

**From plan.md:**

- Architecture/stack choices
- Data Model references
- Phases
- Technical constraints
- Async process model/lifecycle notes (if present)
- Local DB transaction model notes (if present)

**From tasks.md:**

- Task IDs
- Descriptions
- Phase grouping
- Parallel markers [P]
- Referenced file paths

**From constitution:**

- Load `constitution.md` for principle validation

### 3. Build Semantic Models

Create internal representations (do not include raw artifacts in output):

- **Requirements inventory**: Each functional + non-functional requirement with a stable key (derive slug based on imperative phrase; e.g., "User can upload file" → `user-can-upload-file`)
- **User story/action inventory**: Discrete user actions with acceptance criteria
- **Task coverage mapping**: Map each task to one or more requirements or stories (inference by keyword / explicit reference patterns like IDs or key phrases)
- **Constitution rule set**: Extract principle names and MUST/SHOULD normative statements

### 4. Detection Passes (Token-Efficient Analysis)

Focus on high-signal findings. Limit to 50 findings total; aggregate remainder in overflow summary.

#### A. Duplication Detection

- Identify near-duplicate requirements
- Mark lower-quality phrasing for consolidation

#### B. Ambiguity Detection

- Flag vague adjectives (fast, scalable, secure, intuitive, robust) lacking measurable criteria
- Flag unresolved placeholders (TODO, TKTK, ???, `<placeholder>`, etc.)

#### C. Underspecification

- Requirements with verbs but missing object or measurable outcome
- User stories missing acceptance criteria alignment
- Tasks referencing files or components not defined in spec/plan

#### D. Constitution Alignment

- Any requirement or plan element conflicting with a MUST principle
- Missing mandated sections or quality gates from constitution

#### E. Coverage Gaps

- Requirements with zero associated tasks
- Tasks with no mapped requirement/story
- Non-functional requirements not reflected in tasks (e.g., performance, security)

#### F. Inconsistency

- Terminology drift (same concept named differently across files)
- Data entities referenced in plan but absent in spec (or vice versa)
- Task ordering contradictions (e.g., integration tasks before foundational setup tasks without dependency note)
- Conflicting requirements (e.g., one requires Next.js while other specifies Vue)

#### G. Async Lifecycle Gaps

- For async/event-loop/background-worker integrations, flag missing lifecycle coverage (start/ready/timeout-cancel/shutdown/cleanup)
- Flag absence of running-loop regression tests for async integration paths
- Flag validation plans that can PASS without proving no orphan processes/tasks remain

#### H. State Safety Gaps

- For live-vs-local state integrations, flag missing source-of-truth ownership and reconciliation checkpoints
- Flag workflows where logged lifecycle transitions have no corresponding persisted state transition requirements
- Flag missing stale/orphan drift regression tests and validation gates that can PASS with unresolved active-state drift

#### I. Local DB Transaction Integrity Gaps

- For local DB lifecycle/risk/financial mutations, flag missing explicit transaction boundaries
- Flag missing rollback/no-partial-write regression tests and idempotent retry expectations
- Flag validation gates that can PASS while persistence errors are swallowed or local lifecycle states are impossible

#### J. External Ingress Readiness Gaps

- Flag ingress/webhook/callback features where the plan omits the External Ingress + Runtime Readiness Gate
- Flag blank or unresolved gate rows without actionable blocking tasks (for example, missing `T000` readiness checkpoint)
- Flag task order where webhook registration/public URL setup occurs before readiness checkpoint completion
- **Async return path coverage**: For each external service in the Architecture Flow that is called outbound, check whether the integration is synchronous or asynchronous. If asynchronous, verify that tasks.md contains tasks covering all three of: (1) the callback endpoint implementation, (2) the callback auth mechanism, (3) the callback payload contract. Any async integration in plan.md with no corresponding callback tasks in tasks.md is CRITICAL — the return path exists in the plan but has no implementation coverage

#### K. Artifact Token Efficiency

- Flag prose paragraphs in spec.md or plan.md that could be tables (lists of fields, comparisons, acceptance scenarios, gate statuses)
- Flag content duplicated across artifacts — same constraint or rationale stated in both spec.md and plan.md, or both plan.md and quickstart.md
- Flag filler phrasing: "This feature will...", "The purpose of this section is to...", "It is important that..." with no informational content beyond the requirement itself
- Flag sections with a single sub-item that could be merged into the parent or an adjacent section
- Flag repeated examples illustrating the same concept more than once

Severity for token efficiency findings is always LOW — they never block implementation but should be offered as remediation suggestions.

### 5. Severity Assignment

Use this heuristic to prioritize findings:

- **CRITICAL**: Violates constitution MUST, missing core spec artifact, or requirement with zero coverage that blocks baseline functionality
- **CRITICAL**: Missing or failed External Ingress + Runtime Readiness Gate when ingress/webhook/callback behavior is in scope
- **HIGH**: Duplicate/conflicting requirement, ambiguous security/performance attribute, untestable acceptance criterion, missing async lifecycle/test coverage, missing state-safety/reconciliation coverage for live-vs-local integrations, or missing local DB transaction integrity coverage
- **MEDIUM**: Terminology drift, missing non-functional task coverage, underspecified edge case
- **LOW**: Style/wording improvements, minor redundancy not affecting execution order

### 6. Produce Compact Analysis Report

Output a Markdown report (no file writes) with the following structure:

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| A1 | Duplication | HIGH | spec.md:L120-134 | Two similar requirements ... | Merge phrasing; keep clearer version |

(Add one row per finding; generate stable IDs prefixed by category initial.)

**Coverage Summary Table:**

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|

**Constitution Alignment Issues:** (if any)

**Unmapped Tasks:** (if any)

**Metrics:**

- Total Requirements
- Total Tasks
- Coverage % (requirements with >=1 task)
- Ambiguity Count
- Duplication Count
- Critical Issues Count

### 7. Provide Next Actions

At end of report, output a concise Next Actions block:

- If CRITICAL issues exist: Recommend resolving before `/speckit.implement`
- If only LOW/MEDIUM: User may proceed, but provide improvement suggestions
- Provide explicit command suggestions: e.g., "Run /speckit.specify with refinement", "Run /speckit.plan to adjust architecture", "Manually edit tasks.md to add coverage for 'performance-metrics'"

### 8. Emit pipeline event

Emit `analysis_completed` to `.speckit/pipeline-ledger.jsonl`:
```json
{"event": "analysis_completed", "feature_id": "NNN", "phase": "solution", "critical_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
```

### 9. Offer Remediation

Ask the user: "Would you like me to suggest concrete remediation edits for the top N issues?" (Do NOT apply them automatically.)

## Operating Principles

### Context Efficiency

- **Minimal high-signal tokens**: Focus on actionable findings, not exhaustive documentation
- **Progressive disclosure**: Load artifacts incrementally; don't dump all content into analysis
- **Token-efficient output**: Limit findings table to 50 rows; summarize overflow
- **Deterministic results**: Rerunning without changes should produce consistent IDs and counts

### Analysis Guidelines

- **NEVER modify files** (this is read-only analysis)
- **NEVER hallucinate missing sections** (if absent, report them accurately)
- **Prioritize constitution violations** (these are always CRITICAL)
- **Use examples over exhaustive rules** (cite specific instances, not generic patterns)
- **Report zero issues gracefully** (emit success report with coverage statistics)

## Context

$ARGUMENTS
