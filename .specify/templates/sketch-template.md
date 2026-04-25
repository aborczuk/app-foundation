# Sketch Blueprint — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Source Plan: `plan.md`_  
_Artifact: `sketch.md`_

---

## Section Map

### Always Emit

- Core Sketch
  - Coverage
  - Current → Target
  - Primary Seam
  - Required Edit / Solution
  - Verification
  - Constraints / Preserve
  - Implementation Directive
  - Design-to-Tasking Contract
  - Sketch Completion Summary

### Emit Only If Triggered

- Conditional Sketch Additions
  - Repo Grounding — emit when multiple surfaces/symbols are involved, the seam is non-obvious, or tasking needs repo-grounded symbol context.
  - Contract / Artifact / Event Impact — emit when public interfaces, artifacts, events, manifests, schemas, CLI/API output, command docs, templates, or generated files change.
  - Runtime / State / Failure Notes — emit when state, lifecycle, retry, rollback, idempotency, migration, async, ordering, or side effects matter.
  - Human / Operator Boundaries — emit when manual, external-console, credential, approval, deployment, or operator action is required.
  - Design Gaps and Repo Contradictions — emit when bounded repo reads reveal missing seams, unsupported assumptions, contradictions, or blocking issues.
  - Decomposition-Ready Design Slices — emit when the work requires multiple implementation tasks.

### Omission Rules

- Omit unused conditional sections entirely.
- Do not leave placeholder headings.
- Do not emit empty or “N/A” tables for conditional sections.
- Every generated sketch must include the core implementation bridge.
- Do not use decomposition slices for one-task work unless needed to preserve safety-critical detail.
- If current behavior cannot be verified from bounded repo reads, mark the sketch blocked instead of guessing.

---

# 1. Core Sketch

## Coverage

### Existing Spec / Feature

- Existing spec / feature: `[ID or N/A]`
- Coverage status: `[Full / Partial / None]`
- Relationship to existing work: `[New feature / Existing feature delta / Bug / Refactor / Docs / Test-only / Ops]`

### Source Requirement / Backlog Item

[Restate the backlog item or requirement being solved.]

### Scope Boundary

In scope:
- [Item]

Out of scope:
- [Item]

---

## Current → Target

### Current Behavior

[Describe what exists today, based on the spec, plan, and bounded repo reads.]

If current behavior was not verified from repo reads, write exactly:

`BLOCKED: current behavior not validated from repo reads.`

### Target Behavior

[Describe what must be true after implementation.]

### Behavior Delta

[Describe the smallest meaningful change from current to target.]

---

## Primary Seam

### Main Edit Surface

- `[file:symbol or artifact path]` — [why this is the primary seam]

### Secondary Surfaces

- `[file:symbol or artifact path]` — [why affected]
- `[file:symbol or artifact path]` — [why affected]

If none, write:

- None.

---

## Required Edit / Solution

[Describe the concrete solution. This must say what to change, not only where to change it.]

Required solution detail must identify applicable items from this list:

- branch or condition to change
- function, parser, schema, command, template, manifest, or return envelope to change
- new reason code, field, payload key, output, event, or artifact state
- allowed side effects
- forbidden side effects
- behavior to preserve
- test oracle

Invalid examples:
- “Harden behavior.”
- “Normalize the contract.”
- “Update the docs.”
- “Wire implementation.”
- “Add tests.”

Valid example shape:
- “In `[file:symbol]`, detect `[condition]` before `[side effect]`, return `[result shape]`, and preserve `[existing behavior]`.”

---

## Verification

### Required Test / Check

- Test file or command: `[path or command]`
- Scenario: [Given / When / Then summary]
- Assertion: [Exact expected result, event, artifact state, or output]

### Regression Check

- [Existing behavior that must still pass.]

### Deterministic Oracle

- [Observable condition that proves success.]

---

## Constraints / Preserve

- [Invariant or behavior that must not change.]
- [Compatibility path that must remain valid.]
- [Side effect that must not occur on blocked/error paths.]

---

## Implementation Directive

### Current Repo Behavior

[What bounded repo reads show the current symbol/path/artifact does today.]

If not verified, write exactly:

`BLOCKED: current behavior not validated from repo reads.`

### Target Behavior

[What must be true after implementation.]

### Concrete Edit Mechanics

- [Branch, condition, parser, schema, return envelope, manifest field, command-doc section, template block, or side-effect path expected to change.]

### Contract / Data Changes

- [Reason code, field, payload shape, manifest key, emitted event, CLI/API output, artifact state, or template output that must change or be preserved.]

### Side Effects Allowed

- [Writes, appends, generated artifacts, sidecars, subprocess execution, or external calls permitted after validation.]

### Side Effects Forbidden

- [Writes, appends, generated artifacts, sidecars, subprocess execution, or external calls forbidden on blocked/error paths.]

### Preserve Behavior

- [Compatibility path, legacy route, valid success case, idempotency behavior, operator-visible output, or existing test behavior that must remain unchanged.]

### Test Oracle

- [Exact scenario and assertion shape downstream tasking must carry into the HUD.]

---

## Design-to-Tasking Contract

Tasking must follow these rules:

- Every implementation task must trace to this sketch.
- No task may introduce scope, seams, symbols, interfaces, artifacts, or events absent from this sketch without explicit rationale.
- `file:symbol` annotations in tasks must trace back to this sketch.
- Acceptance artifacts must derive from the verification intent in this sketch.
- Tasking must preserve declared dependencies and invariants.
- Tasking must not create tasks against surfaces explicitly marked preserve-as-is unless a rationale is recorded.
- Every non-`[H]` task must produce a HUD implementation ticket with current behavior, target behavior, required edits, touched symbols, tests, constraints, dependencies, and done criteria.

---

## Sketch Completion Summary

### Ready for Tasking?

- [ ] Existing spec coverage is explicit.
- [ ] Current behavior is verified or explicitly blocked.
- [ ] Target behavior is explicit.
- [ ] Primary seam is explicit.
- [ ] Required edit / solution is concrete.
- [ ] Verification oracle is explicit.
- [ ] Constraints and preserve-as-is behavior are explicit.
- [ ] Contract/artifact/event impact is included or not applicable.
- [ ] Runtime/state/failure impact is included or not applicable.
- [ ] Human/operator boundary is included or not applicable.
- [ ] Multi-task work is decomposed into design slices when needed.
- [ ] Every slice has an implementation directive when slices exist.
- [ ] No blocking repo contradiction remains unresolved.

### Suggested Next Step

`/speckit.tasking`

---

# 2. Conditional Sketch Additions

<!--
Emit only the conditional sections that are triggered.
Omit all unused conditional sections from generated sketch.md.
-->

## Repo Grounding

### Primary Surfaces

| Surface | Current Role | Planned Change | Symbols | Reuse / Modify / Create | Verification Concern |
|---------|--------------|----------------|---------|--------------------------|----------------------|
| [file/artifact/module] | [role today] | [change] | [symbols] | [Reuse / Modify / Create] | [concern] |

### Secondary / Blast-Radius Surfaces

| Surface | Why Affected | Risk | Required Regression Check |
|---------|--------------|------|---------------------------|
| [surface] | [reason] | [risk] | [check] |

### Caller / Callee / Dependency Notes

- [Important relationship.]
- [Important relationship.]

---

## Contract / Artifact / Event Impact

| Contract / Artifact / Symbol / Event | Current Shape | Target Shape | Owner | Failure Shape / Invariant | Verification |
|--------------------------------------|---------------|--------------|-------|---------------------------|--------------|
| [surface] | [current] | [target] | [owner] | [failure/invariant] | [verification] |

### Manifest / Registry / Template Notes

- [Manifest, registry, routing, scaffold, or template impact.]

---

## Runtime / State / Failure Notes

| Concern | Applies? | Design Decision | Verification / Rollback Note |
|---------|----------|-----------------|------------------------------|
| State authority | [Yes / No] | [decision] | [note] |
| Lifecycle transition | [Yes / No] | [decision] | [note] |
| Retry / replay / duplicate handling | [Yes / No] | [decision] | [note] |
| Rollback / migration | [Yes / No] | [decision] | [note] |
| Async / cancellation / timeout | [Yes / No] | [decision] | [note] |
| Side-effect ordering | [Yes / No] | [decision] | [note] |

### Forbidden Failure Modes

- [Failure mode implementation must prevent.]
- [Failure mode implementation must prevent.]

---

## Human / Operator Boundaries

| Boundary | Why Human / Operator Action Is Required | Preconditions | Evidence / Verification | Downstream `[H]` Task? |
|----------|-----------------------------------------|---------------|--------------------------|------------------------|
| [boundary] | [reason] | [preconditions] | [evidence] | [Yes / No] |

---

## Design Gaps and Repo Contradictions

### Missing Seams

- [Gap.]

### Unsupported Assumptions

- [Assumption.]

### Plan vs Repo Contradictions

- [Contradiction.]

### Blocking Design Issues

- [Blocking issue.]

If any blocking issue exists, tasking must not proceed until resolved.

---

## Decomposition-Ready Design Slices

### Slice SK-01: [Slice Name]

**Objective**  
[What this slice accomplishes.]

**Primary Seam**  
`[file:symbol or artifact path]`

**Touched Files**  
- `[path/to/file.ext]`

**Touched Symbols**  
- `[file.py:symbol_name]`

**Likely Net-New Files**  
- `[path/to/new_file.ext]`
- If none, write: None.

**Reuse / Modify / Create Classification**  
[Reuse / Modify / Create]

**Dependencies on Other Slices**  
- [Dependency, or None.]

**Constraints / Invariants**  
- [Constraint.]

**Primary Verification Intent**  
[What downstream validation must prove for this slice.]

**Implementation Directive**

- **Current repo behavior**: [What this slice’s seam does today.]
- **Target behavior**: [What must be true after this slice.]
- **Concrete edit mechanics**: [Branch/condition/schema/return envelope/template/artifact path to change.]
- **Contract / data changes**: [Fields/events/reason codes/payloads/artifact states.]
- **Side effects allowed**: [Allowed side effects.]
- **Side effects forbidden**: [Forbidden side effects.]
- **Preserve behavior**: [Behavior to preserve.]
- **Test oracle**: [Scenario and assertion shape.]

---

### Slice SK-02: [Slice Name]

**Objective**  
[What this slice accomplishes.]

**Primary Seam**  
`[file:symbol or artifact path]`

**Touched Files**  
- `[path/to/file.ext]`

**Touched Symbols**  
- `[file.py:symbol_name]`

**Likely Net-New Files**  
- `[path/to/new_file.ext]`
- If none, write: None.

**Reuse / Modify / Create Classification**  
[Reuse / Modify / Create]

**Dependencies on Other Slices**  
- [Dependency, or None.]

**Constraints / Invariants**  
- [Constraint.]

**Primary Verification Intent**  
[What downstream validation must prove for this slice.]

**Implementation Directive**

- **Current repo behavior**: [What this slice’s seam does today.]
- **Target behavior**: [What must be true after this slice.]
- **Concrete edit mechanics**: [Branch/condition/schema/return envelope/template/artifact path to change.]
- **Contract / data changes**: [Fields/events/reason codes/payloads/artifact states.]
- **Side effects allowed**: [Allowed side effects.]
- **Side effects forbidden**: [Forbidden side effects.]
- **Preserve behavior**: [Behavior to preserve.]
- **Test oracle**: [Scenario and assertion shape.]

_Add more slices only when required._