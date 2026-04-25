# Implementation Plan — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Source Spec: `spec.md`_  
_Artifact: `plan.md`_  
_Plan Profile: `[Skip / Lite / Full]`_

---

## Section Map

### Always Emit

- Core Plan
  - Summary
  - Plan Routing
  - Existing Coverage and Reuse
  - Handoff Contract to Sketch
  - Plan Completion Summary

### Emit Only If Triggered

- Conditional Plan Additions
  - Architecture Direction — emit for Lite/Full, or if Skip profile still needs one architecture assumption stated.
  - Technical Context — emit for Full, or when technology/runtime/tooling choice matters.
  - Runtime / State / Contract Impact — emit when state, storage, transactions, retry, idempotency, public contracts, artifact/event lifecycle, external dependencies, or trust boundaries change.
  - Artifact, Event, and Surface Impact — emit when generated artifacts, events, manifests, command outputs, public contracts, templates, docs, or operator-visible surfaces change.
  - External Ingress and Runtime Readiness — emit when external systems, credentials, webhooks, APIs, deployments, or non-repo configuration are involved.
  - Feasibility and Research Questions — emit when research is required or unknowns remain.
  - Human / Operator Boundary Check — emit when manual, external-console, credential, approval, deployment, or operator action may be required.

### Omission Rules

- Omit unused conditional sections entirely.
- Do not leave placeholder headings.
- Do not emit empty or “N/A” tables for conditional sections.
- Keep the generated plan proportional to the selected profile.
- Do not use Full profile when Skip or Lite would preserve the required decisions.

---

# 1. Core Plan

## Summary

### Feature Goal

[Describe the feature or backlog item from an architecture/planning perspective.]

### Plan Profile Decision

Selected profile: `[Skip / Lite / Full]`

Reason:
- [Why this profile is sufficient.]

### Existing Spec Coverage

- Existing spec / feature: `[ID or N/A]`
- Coverage status: `[Full / Partial / None]`
- Required spec update: `[None / Clarification / New requirement / New acceptance scenario / New spec]`

---

## Plan Routing

| Downstream Phase | Decision | Reason |
|------------------|----------|--------|
| Research | `[Skip / Required]` | [Why] |
| Plan | `[Skip / Lite / Full]` | [Why] |
| Sketch | `[Required]` | [Why; every implementation item should have at least the minimum sketch] |
| Tasking | `[Required / Attach to existing feature]` | [Why] |
| Estimate | `[Required after tasking / Reuse existing estimate]` | [Why] |

### Routing Notes

- [Any important routing note.]
- [If this item attaches to an existing feature, state where.]

---

## Existing Coverage and Reuse

| Existing Surface / Spec / Plan / Pattern | What It Already Covers | Gap / Required Change | Reuse Decision |
|------------------------------------------|-------------------------|-----------------------|----------------|
| [surface/spec/pattern] | [coverage] | [gap] | [Reuse / Extend / Replace / N/A] |

### Reuse Strategy

[Describe what is reused as-is, what is extended, and what is net-new.]

### Net-New Justification

[Explain why any net-new architecture, artifact, interface, or runtime behavior is necessary. If none, write “None.”]

---

## Handoff Contract to Sketch

### Settled by Plan

- [Decision settled by this plan.]
- [Decision settled by this plan.]

### Sketch Must Preserve

- [Architecture assumption.]
- [Reuse decision.]
- [Contract or artifact invariant.]
- [Runtime/state/failure invariant.]

### Sketch Must Determine

- [Repo-grounded surfaces.]
- [Touched files/symbols.]
- [Implementation seams.]
- [Concrete current → target behavior.]
- [Verification or test oracle.]
- [Whether the solution decomposes into one task or multiple design slices.]

### Sketch Must Not Re-Decide

- [Settled architecture choice.]
- [Settled trust boundary.]
- [Settled external dependency decision.]
- [Settled artifact/event lifecycle decision.]

---

## Plan Completion Summary

### Ready for Sketch?

- [ ] Plan profile is explicit.
- [ ] Existing spec coverage is explicit.
- [ ] Downstream phase routing is explicit.
- [ ] Reuse strategy is explicit.
- [ ] Runtime/state/contract impact is explicit or not applicable.
- [ ] Artifact/event/surface impact is explicit or not applicable.
- [ ] Human/operator boundary is explicit or not applicable.
- [ ] Open feasibility questions are isolated or marked None.
- [ ] Handoff contract to sketch is explicit.

### Suggested Next Step

`/speckit.sketch`

---

# 2. Conditional Plan Additions

<!--
Emit only the conditional sections that are triggered.
Omit all unused conditional sections from generated plan.md.
-->

## Architecture Direction

### Chosen Direction

[State the architecture direction in plain language.]

### Why This Direction

[Explain why this direction fits the spec, existing architecture, and repo constraints.]

### Architecture Delta From Existing System

[State whether this item preserves existing architecture or changes it. If changed, describe the smallest meaningful delta.]

---

## Technical Context

| Area | Decision / Direction | Notes |
|------|-----------------------|-------|
| Language / Runtime | [value] | [notes] |
| Technology Selection | [chosen tools/libraries/platforms] | [notes / evidence] |
| Storage | [value] | [notes] |
| Testing | [value] | [notes] |
| Target Platform | [value] | [notes] |
| Constraints | [value] | [notes] |
| Scale / Scope | [value] | [notes] |

---

## Runtime / State / Contract Impact

| Concern | Applies? | Decision / Impact | Notes |
|---------|----------|-------------------|-------|
| Async / background work | [Yes / No] | [decision] | [notes] |
| State authority | [Yes / No] | [decision] | [notes] |
| Storage / persistence | [Yes / No] | [decision] | [notes] |
| Transactions / rollback | [Yes / No] | [decision] | [notes] |
| Retry / idempotency | [Yes / No] | [decision] | [notes] |
| Public API / CLI / command contract | [Yes / No] | [decision] | [notes] |
| Artifact / event lifecycle | [Yes / No] | [decision] | [notes] |
| External service / dependency | [Yes / No] | [decision] | [notes] |
| Trust boundary / permissions | [Yes / No] | [decision] | [notes] |

### Required Invariants

- [Invariant the sketch/tasking/implementation must preserve.]
- [Invariant the sketch/tasking/implementation must preserve.]

---

## Artifact, Event, and Surface Impact

| Surface / Artifact / Event / Contract | Change? | Owner | Downstream Consumer | Verification |
|--------------------------------------|---------|-------|---------------------|--------------|
| [surface] | [Yes / No] | [owner] | [consumer] | [verification] |

### Manifest / Registry Impact

[State whether manifest, registry, routing, command-map, or configuration updates are expected.]

---

## External Ingress and Runtime Readiness

| Gate Item | Status | Rationale |
|-----------|--------|-----------|
| [Gate row] | [Pass / Fail] | [rationale] |

### Readiness Blocking Summary

[If any row is Fail, state what blocks implementation readiness.]

---

## Feasibility and Research Questions

### Research Decision

Research: `[Skip / Required]`

Reason:
- [Why research is or is not required.]

### Open Feasibility Questions

- [ ] **FQ-001**: [question]  
  **Probe:** [minimal proof needed]  
  **Blocking:** [what architecture element depends on it]

- [ ] **FQ-002**: [question]  
  **Probe:** [minimal proof needed]  
  **Blocking:** [what architecture element depends on it]

---

## Human / Operator Boundary Check

| Boundary | Why Human / Operator Action Is Required | Preconditions | Evidence / Verification | Downstream `[H]` Task? |
|----------|-----------------------------------------|---------------|--------------------------|------------------------|
| [boundary] | [reason] | [preconditions] | [evidence] | [Yes / No] |