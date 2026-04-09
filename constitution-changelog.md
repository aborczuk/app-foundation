# Constitution Changelog

Amendment history for `constitution.md`. Each entry records the version bump, the date, what
changed, and which dependent templates were updated. The latest entry is at the top.

Append new entries here (not to `constitution.md`) whenever the constitution is amended.

---

## 2.3.3 (2026-04-08)

**Version change**: 2.3.2 → 2.3.3 (PATCH — machine-readable pipeline source + reason-code routing + compact-first loading)

### Summary

- Added machine-readable canonical pipeline matrix at `docs/governance/pipeline-matrix.yaml`.
- Added deterministic gate reason-code catalog at `docs/governance/gate-reason-codes.yaml`.
- Added governance doc graph file at `docs/governance/doc-graph.yaml`.
- Updated command docs to prioritize compact contract loading and reason-code routing over repeated stop-message prose.

### Files updated

| File | Status |
|------|--------|
| `constitution.md` | ✅ updated (pipeline matrix source reference + compact-first loading + reason-code catalog + version bump) |
| `constitution-changelog.md` | ✅ updated (this entry) |
| `docs/governance/pipeline-matrix.yaml` | ✅ added |
| `docs/governance/gate-reason-codes.yaml` | ✅ added |
| `docs/governance/doc-graph.yaml` | ✅ added |
| `.claude/commands/speckit.plan.md` | ✅ updated (compact-first contract + reason-code routing) |
| `.claude/commands/speckit.specify.md` | ✅ updated (compact-first contract + reason-code routing) |
| `.claude/commands/speckit.implement.md` | ✅ updated (reason-code routing guidance) |
| `CLAUDE.md` | ✅ updated (compact-first loading rule) |

### SYNC IMPACT REPORT

- Canonical workflow matrix now has a machine-readable source that can be validated and consumed by scripts.
- Deterministic gate failures now route through a shared reason-code catalog to avoid repeating large remediation prose.
- Command consumption is compact-first to reduce recurring token load in routine runs.

---

## 2.3.2 (2026-04-08)

**Version change**: 2.3.1 → 2.3.2 (PATCH — plan/spec deterministic gates + lightweight prompt-size CI guard)

### Summary

- Added deterministic gates for `/speckit.specify` and `/speckit.plan` so checklist/clarification and plan-section checks can be enforced via scripts instead of prose interpretation.
- Added lightweight prompt word-cap validation script and CI step to prevent prompt-volume regressions in high-frequency governance/command docs.

### Files updated

| File | Status |
|------|--------|
| `constitution.md` | ✅ updated (gate catalog + version bump) |
| `CLAUDE.md` | ✅ updated (new deterministic spec/plan gate references) |
| `.claude/commands/speckit.specify.md` | ✅ updated (spec gates wired in command flow) |
| `.claude/commands/speckit.plan.md` | ✅ updated (plan gates wired in command flow) |
| `.github/workflows/ci.yml` | ✅ updated (prompt word-cap check step) |
| `scripts/speckit_spec_gate.py` | ✅ added |
| `scripts/speckit_plan_gate.py` | ✅ added |
| `scripts/validate_prompt_word_caps.py` | ✅ added |

### SYNC IMPACT REPORT

- Specification and plan command quality gates now have deterministic script entry points with reason-coded failures.
- CI now blocks oversized prompt-surface docs to preserve token-efficiency baseline.

---

## 2.3.1 (2026-04-08)

**Version change**: 2.3.0 → 2.3.1 (PATCH — deterministic gate enforcement + token-efficiency compression)

### Summary

- Replaced repeated gate prose with script-enforced checks for plan entry, implement entry, implement execution, and tasks format validation.
- Kept governance behavior intact while moving validation logic into deterministic scripts and reason codes.

### Files updated

| File | Status |
|------|--------|
| `constitution.md` | ✅ updated (Quality Gates reference deterministic scripts; version bump) |
| `CLAUDE.md` | ✅ updated (deterministic gate command catalog) |
| `.claude/commands/speckit.plan.md` | ✅ updated (plan checklist gate via script) |
| `.claude/commands/speckit.implement.md` | ✅ updated (implement execution gates via script) |
| `.claude/commands/speckit.tasks.md` | ✅ updated (tasks format gate via script) |
| `.claude/commands/speckit.specify.md` | ✅ updated (compressed repetitive clarification/quality prose) |
| `scripts/speckit_gate_status.py` | ✅ added |
| `scripts/speckit_implement_gate.py` | ✅ added |
| `scripts/speckit_tasks_gate.py` | ✅ added |

### SYNC IMPACT REPORT

- Constitutional requirements now point to deterministic gate scripts instead of manual counting/instruction duplication.
- Downstream command behavior remains hard-gated; token volume is reduced by centralizing validation logic.

---

## 2.1.0 (2026-04-03)

**Version change**: 2.0.0 → 2.1.0 (MINOR — principles restructured for token efficiency; no rules deleted)

### Principles removed from constitution (content migrated to authoritative skill commands)

- **Principle IV: Behavioral Contracts — Spec Authoring Rules** (dropped) — 9 spec authoring rules
  moved to `speckit.specify.md` checklist (step 9a, Requirement Completeness section). Rules are
  still enforced; enforcement is now at the correct location.
- **Principle III sub-bullet: FR-naming rule for trigger/orchestrate work** — already present in
  `speckit.specify.md` steps 7.3 and checklist line 152/165. Sub-bullet dropped from constitution;
  the spec authoring pointer ("defined in `/speckit.specify`") remains.
- **Principle V "Repo assembly model" sub-bullet** — content already in `speckit.research.md` Key
  rules. Dropped from constitution; governance rule ("ALL partial matches MUST be surfaced") folded
  into the no-server-first bullet.

### Principles merged

| Old | New | Result |
|-----|-----|--------|
| II (Reuse) + V (Reuse Over Invention) | II. Reuse at Every Scale | Code-level + architecture-level sub-headings |
| VI (Composability) + VII (SoC) | IV. Composability, Modularity, and Separation of Concerns | Two-paragraph principle |
| VIII (KISS/YAGNI) + X (DRY) | V. KISS, YAGNI, and DRY | Two-paragraph principle |
| XVI (State Safety) + XVII (Local DB ACID) | XII. State Safety and Integrity | Two sub-sections |

### Renumbering

Old → New: III→III, IX→VI, XI→VII, XII→VIII, XIII→IX, XIV→X, XV→XI, XVIII→XIII

### Sentence-level brevity changes

- I-d: dropped redundant "No implicit trust between services, processes, or external APIs —"
- V opener: was "Never design a custom, from-scratch pipeline or architecture if an existing, well-maintained framework can solve the problem."
- V examples clause: dropped dated framework examples
- VIII: dropped final sentence ("If a simpler design exists that meets the current spec, it MUST be chosen") — implied by opening
- XI logging: 4 bullets → 2 (core invariants only)
- Quality Gates "Before implementation" list: trailing prose elaborations compressed to check names
- Canonical Workflow "Never mark PASS when…" 5 bullets → 1 sentence referencing Principles X–XIII

### Quality Gates changes

"Before implementation begins" 9-item verbose list compressed to 5 concise lines; principle
references now explicit (Principles VII, XI, XII, XIII). No gate removed.

### Canonical Workflow changes

5 "Never mark PASS when…" bullets replaced with: "Never mark validation PASS when any
principle-specific invariant from Principles X–XIII is violated (see `/speckit.checkpoint`
and `/speckit.e2e-run` for gate definitions)."

### Files updated

| File | Status |
|------|--------|
| `constitution.md` | ✅ updated (rewritten — 327 lines → ~250 lines) |
| `.claude/commands/speckit.specify.md` | ✅ updated (6 spec authoring items added to checklist) |
| `.claude/commands/speckit.plan.md` | ✅ updated (III-* → I-* in Constitution Check step) |
| `constitution-changelog.md` | ✅ this entry |

### Follow-up TODOs

None. All migrated content was already partially or fully present in its destination command.

---

## 2.0.0 (2026-04-03)
Run date: 2026-04-03
Version change: 1.11.0 → 2.0.0 (MAJOR — structural reorganisation + full custom-command registry)

Modified sections:
- Core Principles — removed Principle I (Human-First Decisions) → moved to CLAUDE.md
- Core Principles — removed Principle II (AI and Planning Behavior) → moved to CLAUDE.md
- Core Principles — removed Principle III (Security First) main body → moved to CLAUDE.md;
  sub-clauses III-a…III-f retained as new Principle I (Security Details)
- Core Principles — removed Principle IV (Parsimony)
- Core Principles — all remaining principles renumbered (old V–XXI → new II–XVIII)
- File location — moved from .specify/memory/constitution.md to constitution.md (repo root)
- Custom commands — documented pre-existing commands now recognised in constitution:
  /speckit.checklist, /speckit.addtobacklog, /speckit.split,
  /speckit.constitution, /speckit.taskstoissues, /speckit.trello-sync

Root cause addressed: principles I–III (strategic/human governance) are general project
governance and belong in CLAUDE.md alongside operational directives. Parsimony duplicates
the KISS/YAGNI principle already in the constitution. The custom-command registry was
incomplete: six commands with .md skill files had no entry in the constitution.

Template consistency review:
- ✅ CLAUDE.md                                — Added Governing Principles block (I, II, III)
- ✅ constitution.md (this file)              — Moved to repo root; principles renumbered
- ✅ .specify/memory/constitution.md          — Stub redirect to repo-root constitution.md
- ✅ scripts/validate_constitution_sync.sh    — Updated path check to constitution.md
- ✅ docs/governance/doc-graph.yaml           — Updated path field
- ✅ .speckit/README.md                       — Updated path reference
- ✅ README.md                                — Updated path reference
- ✅ .claude/commands/speckit.constitution.md — Updated operating path
- ✅ .claude/commands/speckit.plan.md         — Updated Principle reference (III → I)
- ✅ .claude/commands/speckit.analyze.md      — Updated path reference

---

## 1.11.0 (2026-04-03)
Version change: 1.10.0 → 1.11.0 (MINOR — research-first pipeline split + planning governance)

Modified sections:
- VI.  Spec-First — added: core automated action MUST appear as FR before planning
- VII. Behavioral Contracts — added: boundary assumptions rule (owner + verifiability criterion)
- VIII. Reuse Over Invention — added: no-server-first evaluation gate; repo assembly model
- Quality Gates — added: research.md prerequisite before plan moves to tasks
- Canonical Workflow Pipeline — inserted /speckit.research between clarify and plan
- Rules — added: never skip /speckit.research before /speckit.plan
- Custom commands — added: /speckit.research

Root cause addressed: speckit planning pipeline systematically missed the core agent trigger,
confused boundary assumptions with out-of-scope exclusions, searched only for installable
packages (not patterns or code to copy), and never asked whether a custom server was necessary
before designing one.

Template consistency review:
- ✅ .claude/commands/speckit.research.md     — New skill created (3-agent parallel research)
- ✅ .claude/commands/speckit.specify.md      — 3 new checklist items + writing instruction
- ✅ .claude/commands/speckit.plan.md         — model:opus; step 1c; phase 0 replaced; ensemble step 2b
- ✅ .specify/templates/spec-template.md      — Added Boundary assumptions category
- ✅ .claude/settings.json                    — Added github MCP server
- ✅ .speckit/README.md                       — Added workflow chain reference

---

## 1.10.0 (2026-03-18)
Version change: 1.9.0 → 1.10.0 (MINOR — logging governance + implementation gates)

Modified sections:
- XIV. Observability and Fail Gracefully — added concrete logging governance rules
- Quality Gates — added pre-implementation logging contract/validation requirement
- Rules — added explicit prohibition on passing validation when required run-log observability signals are missing

Template consistency review:
- ✅ .claude/commands/speckit.implement.md    — per-task logging guard and checkpoint observability gate added

---

## 1.9.0 (2026-03-16)
Version change: 1.8.0 → 1.9.0 (MINOR — venue-constrained discovery)

Modified sections:
- XXI. Venue-Constrained Discovery and Live Data Request Discipline — new principle
- Quality Gates — added venue-constrained discovery requirements
- Rules — added explicit prohibition on passing validation when live requests bypass venue metadata validation

Template consistency review:
- ✅ .claude/commands/speckit.specify.md      — spec validation requires metadata-first discovery policy for venue-constrained entities
- ✅ .claude/commands/speckit.planreview.md   — plan ambiguity scan includes venue-constrained discovery gaps
- ✅ .specify/templates/plan-template.md      — technical context + constitution check updated with venue-constrained discovery model

---

## 1.8.0 (2026-03-16)
Version change: 1.7.0 → 1.8.0 (MINOR — local database ACID integrity)

Modified sections:
- XX. Local Database ACID and Transactional Integrity — new principle
- Quality Gates — added local DB transaction model and regression requirements
- Rules — added explicit prohibition on passing validation with partial local writes

Template consistency review:
- ✅ .claude/commands/speckit.specify.md      — spec quality checklist includes transaction integrity requirements
- ✅ .claude/commands/speckit.clarify.md      — clarification taxonomy includes local DB transaction ambiguity checks
- ✅ .claude/commands/speckit.plan.md         — local DB transaction design review added
- ✅ .claude/commands/speckit.planreview.md   — plan ambiguity scan includes transaction model gaps
- ✅ .claude/commands/speckit.tasks.md        — transaction guard task generation requirements added
- ✅ .claude/commands/speckit.estimate.md     — estimation warnings include missing transaction coverage
- ✅ .claude/commands/speckit.breakdown.md    — task splitting preserves transaction-integrity guards
- ✅ .claude/commands/speckit.analyze.md      — cross-artifact analysis includes transaction integrity gaps
- ✅ .claude/commands/speckit.implement.md    — transactional validation gate added
- ✅ .claude/commands/speckit.checkpoint.md   — transaction integrity pass/fail guard added
- ✅ .claude/commands/speckit.do.md           — ad-hoc workflow enforces transaction integrity guard
- ✅ .claude/commands/speckit.e2e.md          — generated E2E script requirements include ACID checks
- ✅ .claude/commands/speckit.e2e-run.md      — E2E execution fails on partial local writes
- ✅ .specify/templates/plan-template.md      — technical context + constitution check updated
- ✅ .specify/templates/tasks-template.md     — local DB transaction task patterns added

---

## 1.7.0 (2026-03-16)
Version change: 1.6.0 → 1.7.0 (MINOR — state safety and reconciliation invariants)

Modified sections:
- XIX. State Safety and Reconciliation Invariants — new principle
- Quality Gates — added state ownership/reconciliation and drift-regression requirements
- Rules — added explicit prohibition on passing validation with unresolved state drift

Template consistency review:
- ✅ .claude/commands/speckit.implement.md    — state-safety validation gate added
- ✅ .claude/commands/speckit.checkpoint.md   — state drift guard and pass/fail criteria added
- ✅ .claude/commands/speckit.tasks.md        — state-safety task generation requirements added
- ✅ .claude/commands/speckit.do.md           — ad-hoc validation includes state-safety guard
- ✅ .specify/templates/plan-template.md      — constitution check includes state-safety row
- ✅ .specify/templates/tasks-template.md     — state-safety task patterns added

---

## 1.6.0 (2026-03-15)
Version change: 1.5.1 → 1.6.0 (MINOR — async process management and event-loop safety)

Modified sections:
- XVIII. Async Process Management and Event-Loop Safety — new principle
- Quality Gates — added async process model and async lifecycle validation requirements
- Rules — added explicit prohibition on passing validation with loop/lifecycle errors

Template consistency review:
- ✅ .claude/commands/speckit.checkpoint.md   — async lifecycle validation gate added
- ✅ .claude/commands/speckit.e2e-run.md      — async lifecycle pass/fail checks added
- ✅ .claude/commands/speckit.tasks.md        — async guard task generation requirements added
- ✅ .claude/commands/speckit.plan.md         — async process-model planning requirements added
- ✅ .claude/commands/speckit.analyze.md      — async lifecycle gap detection added
- ✅ .specify/templates/plan-template.md      — async process model + constitution row added
- ✅ .specify/templates/tasks-template.md     — async lifecycle/regression/cleanup task patterns added

---

## 1.5.1 (2026-03-15)
Version change: 1.5.0 → 1.5.1 (PATCH — behavioral contracts error shape requirement)

Modified sections:
- VII. Behavioral Contracts — added Error Shape and Rules requirement for contract patterns
- Quality Gates — added pre-implementation gate for Error Shape and Rules in changed contracts

Template consistency review:
- ✅ No template changes required (governance rule applies directly to contract artifacts)

---

## 1.4.1 (2026-03-12)
Version change: 1.4.0 → 1.4.1 (PATCH — per-task atomic commits in implement)

Modified commands:
- /speckit.implement — Added per-task atomic commits and per-phase push gates:
  - After each task is validated and marked [X], immediately commit (local only)
  - Commit message format: "T0XX <description>"
  - After phase checkpoint passes, ask human to push to remote
  - tasks.md included in each commit to track progress atomically

Template consistency review:
- ✅ .claude/commands/speckit.e2e.md         — New command file created
- ✅ .claude/commands/speckit.e2e-run.md     — New command file created
- ✅ .claude/commands/speckit.do.md          — New command file created
- ✅ .claude/commands/speckit.implement.md   — Layer 3 added, step 9 updated, per-task commits added
- ✅ .specify/templates/tasks-template.md    — No changes needed
- ✅ .specify/templates/plan-template.md     — No changes needed

---

## 1.4.0 (2026-03-12)
Version change: 1.3.0 → 1.4.0 (MINOR — E2E pipeline + ad-hoc task pipeline)

Modified sections:
- Canonical Workflow Pipeline — restructured into three subsections:
  1. Full Feature Pipeline (added /speckit.e2e and /speckit.e2e-run steps)
  2. Ad-Hoc Task Pipeline (new — /speckit.do)
  3. Validation Commands (new — /speckit.checkpoint and /speckit.e2e-run as standalone)
- Rules — added: "Never skip /speckit.e2e before /speckit.implement"
- Custom commands — added: /speckit.e2e, /speckit.e2e-run, /speckit.do

New commands:
- /speckit.e2e       — Generates E2E testing pipeline artifacts (e2e.md + script)
- /speckit.e2e-run   — Executes E2E testing pipeline (preflight | USn | full | verify)
- /speckit.do        — Ad-hoc guardrailed task: add to tasks.md, implement, commit + push

Modified commands:
- /speckit.implement — Added Layer 3 (E2E validation via /speckit.e2e-run after user story phases);
                       replaced hardcoded e2e_paper.sh reference with generic /speckit.e2e-run
