# Solution Review — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Review Artifact: `solutionreview.md`_

## 1. Setup

- Reviewer:
- Date:
- Feature:
- Required inputs:
  - `sketch.md`
  - `spec.md`
  - `plan.md`
- Optional inputs:
  - `research.md`
  - `spike.md`
  - `data-model.md`
  - `quickstart.md`
  - `contracts/*`
  - `catalog.yaml`
  - `command-manifest.yaml`
- Notes:

## 2. Gate checks

- `sketch.md` present:
- `spec.md` present:
- `plan.md` present:
- `Open Feasibility Questions` empty:
- Hard block reasons:
- Gate status:

## 3. Load review context

- Required artifacts reviewed:
  - `sketch.md`
  - `spec.md`
  - `plan.md`
- Optional artifacts reviewed:
  - `research.md`
  - `spike.md`
  - `data-model.md`
  - `quickstart.md`
  - `contracts/*`
  - `catalog.yaml`
  - `command-manifest.yaml`
- Downstream command contracts reviewed:
  - `speckit.tasking.md`
  - `speckit.analyze.md`
  - `speckit.solution.md`
### CodeGraphContext Findings

- CodeGraph queries run:
- HUDs / exact symbols reviewed:
- Stable surfaces confirmed:
- Blast-radius surfaces confirmed:
- Missing or ambiguous coverage:
- Notes:

## 4. Hard completeness check on sketch structure

- Required sketch sections present:
- Missing sections:
- Notes:

## 5. Spec-to-sketch traceability review (mandatory)

- Traceable requirements:
- Gaps:
- Notes:

## 6. Plan-to-sketch fidelity review (mandatory)

- Preserved plan decisions:
- Divergences:
- Notes:

## 7. Solution narrative and construction strategy review (mandatory)

- Coherent solution story:
- Build order:
- Notes:

## 8. Repo grounding and touched-surface review (mandatory)

- Touched files, symbols, and seams:
- Blast radius:
- Codegraph/HUD refs used:
- Notes:

## 9. Command / script / manifest review (mandatory)

- Commands affected:
- Scripts affected:
- Manifest artifacts / events affected:
- Notes:

## 10. Symbol strategy and interface review (mandatory)

- Major symbols / interfaces:
- Contracts:
- Exact symbol/HUD refs:
- Notes:

## 11. Reuse strategy review (mandatory)

- Reused surfaces:
- Net-new justifications:
- Notes:

## 12. Blast-radius and risk-surface review (mandatory)

- Direct surfaces:
- Indirect surfaces:
- Notes:

## 13. State / lifecycle / failure model review (mandatory)

- Lifecycle / failure behaviors:
- Retry / replay / rollback:
- Notes:

## 14. Human-task and operator-boundary review (mandatory)

- Human / operator gates:
- Notes:

## 15. Verification-strategy review (mandatory)

- Test strategy:
- Validation strategy:
- Notes:

## 16. Domain guardrail review (mandatory)

- Domain MUST rules:
- Notes:

## 17. Design-to-tasking contract review (mandatory)

- Tasking-ready seams:
- Gaps that would force invention:
- Notes:

## 17b. Narrative and reuse gate rubric (mandatory)

- Narrative gate:
- Reuse gate:
- Notes:

## 18. Cross-slice DRY and coherence review (mandatory)

- DRY / coherence across slices:
- Notes:

## 19. Write `solutionreview.md`

- Output path:
- Generated from template:
- Notes:

## 20. Emit pipeline event

- Event:
- Required fields:
- Notes:

## 21. Decision rule

- Critical count:
- High count:
- Decision:
- Suggested next step:
- Notes:

## 22. Report

### Executive Summary

**Review Status:** `[PASS | PASS WITH FIXES | BLOCKED]`
**Critical Findings:** `[N]`
**High Findings:** `[N]`
**Medium Findings:** `[N]`
**Low Findings:** `[N]`

### Summary

[One concise paragraph explaining whether `sketch.md` is strong enough to act as the authoritative pre-task LLD artifact for `/speckit.tasking`, what the main strengths are, and what the main blocking issues are if any.]

### Gate Rubric

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

### Findings Taxonomy

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
- `codegraph-grounding`

### Findings Table

| Finding ID | Severity | Category | Sketch Section | Summary | Why It Matters | Required Remediation | Blocking? |
|------------|----------|----------|----------------|---------|----------------|----------------------|-----------|
| SR-001 | [CRITICAL/HIGH/MEDIUM/LOW] | [category] | [section name] | [short finding summary] | [why downstream phases are affected] | [specific required fix] | [yes/no] |

_Add one row per finding._

### Findings by Review Dimension

#### Completeness

[Review whether required sketch sections exist and are materially filled in.]

#### Narrative and Construction Strategy

[Review whether the sketch tells a coherent build story and implementation path.]

#### Traceability to Spec and Plan

[Review whether the sketch preserves requirements, constraints, and approved plan decisions.]

#### Repo Grounding and Touched Surfaces

[Review whether touched files, symbols, seams, and blast radius are concrete enough, using the codegraph/HUD evidence recorded in step 3.]

#### Symbol, Interface, and Contract Quality

[Review whether public symbols, interfaces, signatures, and contracts are explicit enough, with exact symbol/HUD references where applicable.]

#### Reuse Strategy

[Review whether reuse-first reasoning is explicit and justified.]

#### Manifest / Pipeline Alignment

[Review whether command/script/manifest implications are explicit and consistent.]

#### State / Lifecycle / Failure Model

[Review whether lifecycle, retry, replay, failure, fallback, and recovery behavior is adequate.]

#### Human / Operator Boundaries

[Review whether `[H]`-relevant boundaries are clearly identified.]

#### Verification Strategy

[Review whether downstream tasking and acceptance generation have enough verification intent.]

#### Domain Guardrails

[Review whether touched domains’ MUST rules are preserved.]

#### Cross-Slice Coherence and DRY

[Review whether slices are coherent, non-duplicative, and task-decomposable.]

### Required Remediation

#### CRITICAL

- [List every CRITICAL remediation item]

#### HIGH

- [List every HIGH remediation item]

#### MEDIUM / LOW

- [List important non-blocking improvements]

### Downstream Risk Assessment

#### Risk to `/speckit.tasking`

[Explain whether tasking would be forced to invent seams, interfaces, files, symbols, or sequencing.]

#### Risk to `/speckit.analyze`

[Explain whether later drift analysis is likely to show spec/plan/sketch/task mismatches.]

#### Risk to `/speckit.implement`

[Explain whether implementation would likely drift or require architecture decisions not captured in sketch.]

### Final Decision

**Decision:** `[PASS | PASS WITH FIXES | BLOCKED]`

#### Decision Rationale

[Short rationale explaining the decision in plain language.]

#### Next Step

- If `BLOCKED`: `/speckit.sketch`
- If `PASS` or `PASS WITH FIXES`: `/speckit.tasking`

## Artifact Scaffolding (Phase 5)

To ensure deterministic template consistency, `/speckit.solutionreview` invokes the pipeline scaffold helper:

```bash
uv run python .specify/scripts/pipeline-scaffold.py speckit.solutionreview
```

This scaffold:
- Populates `FEATURE_DIR/solutionreview-template.md` if missing (from `.specify/templates/solutionreview-template.md`)
- Ensures the review artifact has the correct structure for downstream parsing
- Enforces deterministic naming and section headers

The scaffold is idempotent: re-running it updates only sections marked for auto-fill, preserving review content.

## Behavior rules

- Read-only on `sketch.md` and supporting artifacts; write only `solutionreview.md`
- Never auto-edit `sketch.md`
- CRITICAL findings block solution progression
- Do not reduce this review to symbol, reuse, or DRY only; validate the full sketch contract
- Prefer explicit blocking findings over vague warnings when downstream tasking would otherwise guess
