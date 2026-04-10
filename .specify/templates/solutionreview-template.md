# Solution Review — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Review Artifact: `solutionreview.md`_

## Executive Summary

**Review Status:** `[PASS | PASS WITH FIXES | BLOCKED]`  
**Critical Findings:** `[N]`  
**High Findings:** `[N]`  
**Medium Findings:** `[N]`  
**Low Findings:** `[N]`

### Summary

[One concise paragraph explaining whether `sketch.md` is strong enough to act as the authoritative pre-task LLD artifact for `/speckit.tasking`, what the main strengths are, and what the main blocking issues are if any.]

---

## Gate Rubric

For each gate, mark one of:

- `PASS`
- `PASS WITH NOTES`
- `FAIL`

Any `FAIL` on a tasking-critical row should correspond to at least one finding in the Findings Table.

| Gate | What must be true | Status | Notes |
|------|-------------------|--------|-------|
| Narrative clarity | The sketch clearly explains what is being built, why this is the chosen realization, and how the feature comes together as a coherent solution. | [STATUS] | [NOTES] |
| Construction clarity | The construction strategy gives a sensible build order that tasking can preserve without inventing sequencing. | [STATUS] | [NOTES] |
| Reuse strategy | The sketch explicitly demonstrates reuse-first reasoning across code, scripts, templates, commands, and manifest-owned artifacts. Net-new choices are justified. | [STATUS] | [NOTES] |
| Spec traceability | Major requirements and constraints from `spec.md` map to concrete design elements. | [STATUS] | [NOTES] |
| Plan fidelity | The sketch refines the approved plan without silently re-planning or diverging from it. | [STATUS] | [NOTES] |
| Repo grounding | Touched files, symbols, seams, and blast radius are concrete enough for decomposition. | [STATUS] | [NOTES] |
| Interface/symbol clarity | Public symbols, interfaces, contracts, and typed boundaries are explicit enough for tasking. | [STATUS] | [NOTES] |
| Manifest / pipeline alignment | Command/script/manifest implications are explicit where relevant. | [STATUS] | [NOTES] |
| Human/operator boundaries | Required human steps or operator boundaries are explicit and taskable. | [STATUS] | [NOTES] |
| Verification intent | The sketch defines enough verification intent for downstream acceptance/test generation. | [STATUS] | [NOTES] |
| Domain guardrails | Touched domain MUST rules are preserved in the design. | [STATUS] | [NOTES] |
| Tasking contract | `/speckit.tasking` can derive tasks without inventing architecture or scope. | [STATUS] | [NOTES] |

---

## Findings Taxonomy

All findings in this review must use one of the following `Category` values:

- `completeness`
- `narrative-clarity`
- `construction-strategy`
- `traceability`
- `plan-fidelity`
- `repo-grounding`
- `symbol-strategy`
- `reuse-strategy`
- `manifest-alignment`
- `blast-radius`
- `lifecycle-failure-model`
- `human-boundary`
- `verification-strategy`
- `domain-guardrail`
- `tasking-contract`
- `cross-slice-dry`

---

## Findings Table

| Finding ID | Severity | Category | Sketch Section | Summary | Why It Matters | Required Remediation | Blocking? |
|------------|----------|----------|----------------|---------|----------------|----------------------|-----------|
| SR-001 | [CRITICAL/HIGH/MEDIUM/LOW] | [category] | [section name] | [short finding summary] | [why downstream phases are affected] | [specific required fix] | [yes/no] |

_Add one row per finding. Keep IDs stable and sequential._

---

## Findings by Review Dimension

### Completeness

[Review whether required sketch sections exist and are materially filled in.]

### Narrative and Construction Strategy

[Review whether the sketch tells a coherent build story and implementation path.]

### Traceability to Spec and Plan

[Review whether the sketch preserves requirements, constraints, and approved plan decisions.]

### Repo Grounding and Touched Surfaces

[Review whether touched files, symbols, seams, and blast radius are concrete enough.]

### Symbol, Interface, and Contract Quality

[Review whether public symbols, interfaces, signatures, and contracts are explicit enough.]

### Reuse Strategy

[Review whether reuse-first reasoning is explicit and justified.]

### Manifest / Pipeline Alignment

[Review whether command/script/manifest implications are explicit and consistent.]

### State / Lifecycle / Failure Model

[Review whether lifecycle, retry, replay, failure, fallback, and recovery behavior is adequate.]

### Human / Operator Boundaries

[Review whether `[H]`-relevant boundaries are clearly identified.]

### Verification Strategy

[Review whether downstream tasking and acceptance generation have enough verification intent.]

### Domain Guardrails

[Review whether touched domains’ MUST rules are preserved.]

### Cross-Slice Coherence and DRY

[Review whether slices are coherent, non-duplicative, and task-decomposable.]

---

## Required Remediation

### CRITICAL

- [List every CRITICAL remediation item]

### HIGH

- [List every HIGH remediation item]

### MEDIUM / LOW

- [List important non-blocking improvements]

---

## Downstream Risk Assessment

### Risk to `/speckit.tasking`

[Explain whether tasking would be forced to invent seams, interfaces, files, symbols, or sequencing.]

### Risk to `/speckit.analyze`

[Explain whether later drift analysis is likely to show spec/plan/sketch/task mismatches.]

### Risk to `/speckit.implement`

[Explain whether implementation would likely drift or require architecture decisions not captured in sketch.]

---

## Final Decision

**Decision:** `[PASS | PASS WITH FIXES | BLOCKED]`

### Decision Rationale

[Short rationale explaining the decision in plain language.]

### Next Step

- If `BLOCKED`: `/speckit.sketch`
- If `PASS` or `PASS WITH FIXES`: `/speckit.tasking`