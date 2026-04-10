---
description: Review `sketch.md` as a pre-task quality gate. Validates that the sketch is a complete, repo-grounded LLD contract before `/speckit.tasking` decomposes it into tasks. Sub-agent of `/speckit.solution`; callable standalone.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

`/speckit.solutionreview` is the **quality gate between sketch and tasking**.

Its job is to determine whether `sketch.md` is strong enough to act as the authoritative pre-task LLD artifact for the rest of the pipeline. It must verify that the sketch:

- is grounded in the actual codebase and pipeline surface,
- preserves the decisions already made in `plan.md`,
- defines a coherent solution narrative and construction strategy,
- identifies touched files/symbols/seams clearly enough for task decomposition,
- captures the domain MUST constraints that tasking and implementation must preserve,
- defines a valid contract for `/speckit.tasking`,
- does not leave major architecture or implementation-shaping questions implicit.

CRITICAL findings block progression to `/speckit.tasking`.

## Pipeline role

This command sits inside the sketch-first flow:

- `speckit.sketch` → produces `sketch.md`
- `speckit.solutionreview` → validates `sketch.md`
- `speckit.tasking` → decomposes approved `sketch.md` into `tasks.md`, then runs estimate/breakdown stabilization and generates HUDs + acceptance tests
- `speckit.analyze` → later verifies `spec -> plan -> sketch -> tasks` consistency

Review the sketch as a **contract** for these downstream phases, not as a general brainstorming artifact.

## Review outcome requirements

A passing `solutionreview` means:

1. `sketch.md` is complete enough that `/speckit.tasking` does not need to invent major structure
2. `sketch.md` is consistent with `spec.md` and `plan.md`
3. the proposed solution is grounded in actual repo surfaces, not abstract intent
4. touched files, symbols, seams, and boundaries are specific enough for decomposition
5. manifest/pipeline/runtime implications are explicit where relevant
6. human-task boundaries, verification intent, and domain MUST rules are explicit
7. no CRITICAL design ambiguity remains that would likely produce bad tasks or implementation drift

If any of these fail materially, tasking must be blocked.

## Outline

### 1. Setup

Run from repo root:

```bash
.specify/scripts/bash/check-prerequisites.sh --json
```

Parse:

- `FEATURE_DIR`
- `AVAILABLE_DOCS`

### 2. Gate checks

Require:

- `FEATURE_DIR/sketch.md`
- `FEATURE_DIR/spec.md`
- `FEATURE_DIR/plan.md`

If `sketch.md` is missing: **STOP** with  
`No sketch blueprint found. Run /speckit.sketch first.`

If `plan.md` contains unresolved `## Open Feasibility Questions`, **STOP** and route to `/speckit.feasibilityspike`.

### 3. Load review context

Read required artifacts:

- `sketch.md`
- `spec.md`
- `plan.md`

Read optional artifacts if present:

- `research.md`
- `spike.md`
- `data-model.md`
- `quickstart.md`
- `contracts/*`
- `catalog.yaml`
- `command-manifest.yaml`

Read downstream command contracts if present:

- `speckit.tasking.md`
- `speckit.analyze.md`
- `speckit.solution.md`

The review must judge the sketch against the actual downstream consumers of the artifact.

### 4. Hard completeness check on sketch structure

Verify that `sketch.md` contains all required sections.

At minimum, require:

1. **Feature Solution Frame**
2. **Solution Narrative**
3. **Construction Strategy**
4. **Acceptance Traceability**
5. **Work-Type Classification**
6. **Current-System Inventory**
7. **Command / Script Surface Map**
8. **CodeGraphContext Findings**
9. **Blast Radius**
10. **Reuse / Modify / Create Matrix**
11. **Manifest Alignment Check**
12. **Architecture Flow Delta**
13. **Component and Boundary Design**
14. **Interface, Symbol, and Contract Notes**
15. **State / Lifecycle / Failure Model**
16. **Non-Functional Design Implications**
17. **Human-Task and Operator Boundaries**
18. **Verification Strategy**
19. **Domain Guardrails**
20. **LLD Decision Log**
21. **Design Gaps and Repo Contradictions**
22. **Design-to-Tasking Contract**
23. **Decomposition-Ready Design Slices**

If a required section is missing, empty, or clearly placeholder-level, raise at least HIGH severity; use CRITICAL if the missing section blocks meaningful task decomposition.

### 5. Spec-to-sketch traceability review (mandatory)

Review whether the sketch actually realizes the feature described by `spec.md`.

Check:

- every major user story or requirement cluster has a visible design anchor,
- acceptance traceability is concrete rather than generic,
- explicit constraints and non-goals from `spec.md` are preserved,
- no major requirement is silently dropped,
- no major new scope appears in sketch without explicit rationale.

Severity guidance:

- **CRITICAL**: requirement missing from design entirely, or sketch introduces major unsupported scope
- **HIGH**: requirement only weakly mapped or ambiguity likely to affect decomposition
- **MEDIUM**: traceability exists but is too vague in one area

### 6. Plan-to-sketch fidelity review (mandatory)

Review whether the sketch faithfully refines the plan rather than re-planning it.

Check:

- the sketch preserves plan-level architecture decisions,
- `Architecture Flow Delta` is used correctly instead of silently replacing the plan’s Architecture Flow,
- manifest/runtime/integration implications are consistent with the plan,
- sketch does not re-open decisions already settled by plan or feasibility spike,
- sketch identifies real repo contradictions when plan assumptions do not match codebase reality.

Severity guidance:

- **CRITICAL**: sketch silently diverges from the approved plan in a way that would affect tasking/implementation
- **HIGH**: plan fidelity is ambiguous in a major area
- **MEDIUM**: minor drift or insufficiently explicit delta

### 7. Solution narrative and construction strategy review (mandatory)

Validate that the sketch tells a coherent build story.

Check:

- the solution narrative clearly explains what is being built and how it comes together,
- the construction strategy describes the major implementation moves in a sane order,
- the design slices align with that construction strategy,
- tasking could derive coherent tasks from this construction path rather than a pile of disconnected audits.

This is a major focus area. A sketch that is only an inventory/checklist without a build thesis should not pass cleanly.

Severity guidance:

- **CRITICAL**: no coherent construction path; tasking would likely produce fragmented or misordered tasks
- **HIGH**: narrative exists but major implementation sequencing is unclear
- **MEDIUM**: coherent but could be clearer

### 8. Repo grounding and touched-surface review (mandatory)

Validate that the sketch is grounded in actual repository reality.

Check:

- Current-System Inventory is concrete and useful,
- CodeGraphContext findings identify stable surfaces,
- primary implementation surfaces are clearly distinguished from blast-radius-only surfaces,
- touched files and touched symbols are specific enough for decomposition,
- line-number dependence is avoided,
- net-new files or symbols are explicitly identified where needed.

Severity guidance:

- **CRITICAL**: the sketch is not grounded enough for tasking to generate trustworthy `file:symbol` tasks
- **HIGH**: important surfaces are vague or missing
- **MEDIUM**: mostly grounded, but one area is weak

### 9. Command / script / manifest review (mandatory)

Because this pipeline is command- and manifest-driven, validate that the sketch models that surface adequately.

Check:

- the Command / Script Surface Map is present and meaningful,
- relevant manifest-owned artifacts/events are represented,
- Manifest Alignment Check identifies affected commands/artifacts/events where relevant,
- no downstream command would be forced to infer ownership or routing changes,
- command/script dependencies are not left implicit.

Severity guidance:

- **CRITICAL**: the feature depends on command/script/manifest changes but sketch does not model them
- **HIGH**: manifest alignment is incomplete or ambiguous
- **MEDIUM**: mostly sufficient with smaller gaps

### 10. Symbol strategy and interface review (mandatory)

Validate that symbol and contract design is strong enough for tasking and implementation.

Check:

- major touched symbols or net-new symbols are named,
- public symbol signatures are recorded where required,
- interfaces/contracts are explicit enough for decomposition,
- typed boundaries and error/result expectations are meaningful,
- no major public API shape is deferred to implementation without justification.

Severity guidance:

- **CRITICAL**: major public symbol/interface shape is missing, making decomposition unsafe
- **HIGH**: symbol targets exist but are too unstable/vague
- **MEDIUM**: mostly strong, minor ambiguity remains

### 11. Reuse strategy review (mandatory)

Validate the sketch’s reuse-first discipline as an explicit gate.

Check:

- reuse / modify / create choices are justified,
- reuse is evaluated across code modules, scripts, commands, templates, manifest-owned artifacts, and existing pipeline seams,
- net-new construction is only used where reuse/extension is truly inadequate,
- broad custom architecture is not introduced where a narrower extension path exists,
- the sketch makes the reuse thesis visible enough that tasking does not default to unnecessary new construction.

Severity guidance:

- **CRITICAL**: major net-new design is introduced with no serious reuse evaluation
- **HIGH**: reuse is acknowledged but weakly justified in a major area
- **MEDIUM**: reuse rationale exists but should be strengthened

### 12. Blast-radius and risk-surface review (mandatory)

Validate the sketch’s blast-radius modeling.

Check:

- direct vs indirect surfaces are clearly distinguished,
- regression-sensitive neighbors are named,
- rollout/compatibility or operator impact is captured where relevant,
- major high-risk boundaries are identified,
- tasking could derive proper verification and dependency sequencing from this.

Severity guidance:

- **CRITICAL**: major impact boundary omitted
- **HIGH**: blast radius present but misses a likely regression-sensitive surface
- **MEDIUM**: mostly good, minor omissions

### 13. State / lifecycle / failure model review (mandatory)

Where applicable, validate that the sketch has made lifecycle and failure behavior explicit.

Check:

- state authority is defined,
- lifecycle transitions are meaningful,
- retry/cancel/replay/out-of-order behavior is addressed where relevant,
- degraded modes / fallback behavior are explicit where needed,
- rollback/recovery/operator intervention expectations are present when the feature needs them.

Severity guidance:

- **CRITICAL**: a lifecycle-heavy or failure-sensitive feature lacks an adequate state/failure model
- **HIGH**: key recovery or replay behavior is unspecified
- **MEDIUM**: mostly good, one important case underspecified

### 14. Human-task and operator-boundary review (mandatory)

Validate whether human/operator requirements are identified clearly enough for later `[H]` task placement.

Check:

- human-task boundaries are explicit where true human work is required,
- review checkpoints are distinguished from real operator actions,
- preconditions and consumed artifacts/evidence are identified,
- failure/escalation behavior is explicit if the human step is skipped or delayed.

Severity guidance:

- **HIGH**: sketch clearly implies human work but does not model it
- **MEDIUM**: boundaries exist but are not crisp enough for tasking

### 15. Verification-strategy review (mandatory)

Validate that the sketch gives tasking enough verification intent.

Check:

- regression-sensitive areas are named,
- lifecycle/duplicate/retry realities are reflected where relevant,
- unit/contract/integration verification seams are visible,
- deterministic oracle opportunities are called out where known,
- the verification strategy is sufficient for tasking to generate acceptance artifacts without inventing design facts.

Severity guidance:

- **CRITICAL**: verification intent is too weak to support safe tasking
- **HIGH**: a major validation surface is missing
- **MEDIUM**: mostly good, one area thin

### 16. Domain guardrail review (mandatory)

For each touched domain, validate that the sketch has preserved domain MUST rules and not only generic prose.

Always review at least:

- Domain 12 — Testing & quality gates
- Domain 13 — Identity & access control
- Domain 14 — Security controls
- Domain 16 — Ops & governance
- Domain 17 — Code patterns

Also review additional touched domains as indicated by the sketch.

Check:

- touched domains are correctly identified,
- MUST constraints are carried into the design,
- forbidden shortcuts are not implicitly taken,
- Domain 17 requirements for public signatures / layer boundaries / code patterns are preserved where relevant,
- security/trust-boundary obligations are explicit where relevant.

Severity guidance:

- **CRITICAL**: domain MUST violation likely or explicit
- **HIGH**: important domain rule missing from design
- **MEDIUM**: domain coverage exists but is uneven

### 17. Design-to-tasking contract review (mandatory)

Validate that the sketch defines a real contract for `tasking`.

Check:

- every design slice appears task-decomposable,
- the contract forbids tasking from inventing major seams/symbols/artifacts,
- `[H]` task origins are constrained,
- `file:symbol` expectations are traceable to the sketch,
- acceptance artifact generation has a clear upstream basis,
- large-task breakdown would preserve design-slice and safety intent.

This is a core gate.

Severity guidance:

- **CRITICAL**: tasking would be forced to invent major solution structure
- **HIGH**: contract exists but is missing an important safeguard
- **MEDIUM**: mostly sound, smaller ambiguity remains

### 17b. Narrative and reuse gate rubric (mandatory)

Before finalizing the review, explicitly score the sketch against the following gate checklist.

For each row, mark one of:

- `PASS`
- `PASS WITH NOTES`
- `FAIL`

Any `FAIL` on a tasking-critical row must produce at least one `CRITICAL` or `HIGH` finding.

| Gate | What must be true | Status | Notes |
|------|-------------------|--------|-------|
| Narrative clarity | The sketch clearly explains what is being built, why this is the chosen realization, and how the feature comes together as a coherent solution. | PASS / PASS WITH NOTES / FAIL | |
| Construction clarity | The construction strategy gives a sensible build order that tasking can preserve without inventing sequencing. | PASS / PASS WITH NOTES / FAIL | |
| Reuse strategy | The sketch explicitly demonstrates reuse-first reasoning across code, scripts, templates, commands, and manifest-owned artifacts. Net-new choices are justified. | PASS / PASS WITH NOTES / FAIL | |
| Spec traceability | Major requirements and constraints from `spec.md` map to concrete design elements. | PASS / PASS WITH NOTES / FAIL | |
| Plan fidelity | The sketch refines the approved plan without silently re-planning or diverging from it. | PASS / PASS WITH NOTES / FAIL | |
| Repo grounding | Touched files, symbols, seams, and blast radius are concrete enough for decomposition. | PASS / PASS WITH NOTES / FAIL | |
| Interface/symbol clarity | Public symbols, interfaces, contracts, and typed boundaries are explicit enough for tasking. | PASS / PASS WITH NOTES / FAIL | |
| Manifest / pipeline alignment | Command/script/manifest implications are explicit where relevant. | PASS / PASS WITH NOTES / FAIL | |
| Human/operator boundaries | Required human steps or operator boundaries are explicit and taskable. | PASS / PASS WITH NOTES / FAIL | |
| Verification intent | The sketch defines enough verification intent for downstream acceptance/test generation. | PASS / PASS WITH NOTES / FAIL | |
| Domain guardrails | Touched domain MUST rules are preserved in the design. | PASS / PASS WITH NOTES / FAIL | |
| Tasking contract | `/speckit.tasking` can derive tasks without inventing architecture or scope. | PASS / PASS WITH NOTES / FAIL | |

Narrative clarity and reuse strategy are non-optional gates. A sketch that is technically detailed but lacks a clear build narrative, or that chooses net-new work without explicit reuse-first reasoning, must not receive a clean pass.

### 18. Cross-slice DRY and coherence review (mandatory)

Review the design slices as a set.

Check:

- duplicated helper/composition patterns across slices,
- repeated net-new seams that should be unified,
- inconsistent symbol naming or ownership,
- contradictory construction logic across slices,
- decomposition slices that are too broad, too narrow, or not implementation-real.

Severity guidance:

- **HIGH**: duplication or incoherence likely to distort tasking
- **MEDIUM**: consolidation recommended
- **LOW**: minor cleanup opportunity

### 19. Write `solutionreview.md`

Write a review report with:

- executive summary,
- findings table,
- per-finding severity,
- affected sketch section(s),
- remediation guidance,
- explicit decision:
  - **BLOCKED** if `critical_count > 0`
  - **PASS WITH FIXES** if `critical_count == 0` but high findings remain
  - **PASS** if no critical findings and no materially risky high findings

Required findings table columns:

- Finding ID
- Severity
- Category
- Sketch Section
- Summary
- Why It Matters
- Required Remediation
- Blocking? (`yes/no`)

Valid `Category` values:

- completeness
- narrative-clarity
- construction-strategy
- traceability
- plan-fidelity
- repo-grounding
- symbol-strategy
- reuse-strategy
- manifest-alignment
- blast-radius
- lifecycle-failure-model
- human-boundary
- verification-strategy
- domain-guardrail
- tasking-contract
- cross-slice-dry

### 20. Emit pipeline event

Append:

```json
{"event": "solutionreview_completed", "feature_id": "NNN", "phase": "solution", "critical_count": N, "high_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
```

to `.speckit/pipeline-ledger.jsonl`.

### 21. Decision rule

- If `critical_count > 0`: hard-block tasking and route back to `/speckit.sketch`
- If `critical_count == 0`: allow progression to `/speckit.tasking`
- If `critical_count == 0` but `high_count > 0`: tasking may proceed only if the remaining HIGH findings do not force tasking to invent architecture or violate domain MUST rules; otherwise treat as effectively blocked and call it out explicitly

### 22. Report

Report:

- path to `solutionreview.md`,
- counts by severity,
- blocked vs pass status,
- top remediation items,
- suggested next step:
  - `/speckit.sketch` if blocked
  - `/speckit.tasking` if passed

## Artifact Scaffolding (Phase 5)

To ensure deterministic template consistency, `/speckit.solutionreview` invokes the pipeline scaffold helper:

```bash
python .specify/scripts/pipeline-scaffold.py speckit.solutionreview
```

This scaffold:
- Populates `FEATURE_DIR/solutionreview-template.md` if missing (from `.specify/templates/solutionreview-template.md`)
- Ensures the review artifact has the correct structure for downstream parsing
- Enforces deterministic naming and section headers

The scaffold is **idempotent**: re-running it updates only sections marked for auto-fill, preserving your review content.

## Behavior rules

- Read-only on `sketch.md` and supporting artifacts; write only `solutionreview.md`
- Never auto-edit `sketch.md`
- CRITICAL findings block solution progression
- Do not reduce this review to symbol/reuse/DRY only; validate the full sketch contract
- Prefer explicit blocking findings over vague warnings when downstream tasking would otherwise guess
- Judge the sketch against the actual downstream consumers in this pipeline, not against generic SDLC ideals alone