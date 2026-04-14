# Plan Review — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Review Artifact: `plan-review.md`_

## Executive Summary

**Review Status:** `[PASS | PASS WITH NOTES | FAIL]`  
**Questions Asked:** `[N]`  
**Open Feasibility Questions:** `[0 | N]`

### Summary

[One paragraph summarizing whether the plan is technically precise enough to proceed to sketch, what the biggest resolved ambiguities were, and whether any blocking feasibility questions remain.]

---

## Catalog Cross-Reference

| Service / External Node | In Architecture Flow | In catalog.yaml | Constraint Match | Required Action | Notes |
|-------------------------|----------------------|-----------------|------------------|-----------------|-------|
| [Service] | [Yes / No] | [Yes / No] | [✅ / ⚠️ / ❌] | [None / Add FQ / Add task / Fix plan] | [Notes] |

### Catalog Notes

- [Any important catalog-related note]
- [Any service that needs a catalog-entry task later]

---

## Ambiguity Findings

| Finding ID | Category | Severity | Location | Question / Gap | Recommended Resolution | Story Point Impact | Status |
|------------|----------|----------|----------|----------------|------------------------|-------------------|--------|
| PR-001 | [Technical Context / Architecture / State Safety / Contract / Research / Traceability / Behavior Map / Risk] | [LOW / MEDIUM / HIGH / CRITICAL] | [plan.md section / artifact] | [Gap description] | [Recommended answer] | [+N pts] | [Resolved / Deferred / Blocking] |

_Add one row per material ambiguity._

---

## Domain Coverage

| Domain | Touched | Core Principles Addressed | Gaps Found |
|--------|---------|---------------------------|------------|
| 01 API & integration | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 02 Data modeling | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 03 Data storage | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 04 Caching & performance | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 05 Client/UI | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 06 Edge & delivery | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 07 Compute & orchestration | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 08 Networking | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 09 Environment & config | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 10 Observability | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 11 Resilience | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 12 Testing | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 13 Identity & access | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 14 Security controls | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 15 Build & deployment | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 16 Ops & governance | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |
| 17 Code patterns | [Yes / No] | [✅ / ⚠️ / ❌] | [Gap or None] |

### Domain Coverage Notes

- [Any hard-block domain issue]
- [Any deferred domain risk]

---

## Pipeline Architecture Review

### Repeated Architectural Unit Recognition

**Status:** `[PASS | PASS WITH NOTES | FAIL]`  
**Assessment:** [Does the plan define the repeated unit clearly enough?]

### Pipeline Architecture Model

**Status:** `[PASS | PASS WITH NOTES | FAIL]`  
**Assessment:** [Does the plan define deterministic stage boundaries and ownership clearly enough?]

### Artifact / Event Contract Architecture

**Status:** `[PASS | PASS WITH NOTES | FAIL]`  
**Assessment:** [Does the plan define producers, consumers, and contract boundaries clearly enough?]

### Architecture Review Notes

- [Important note]
- [Important note]

---

## Handoff-to-Sketch Review

### Status

`[PASS | PASS WITH NOTES | FAIL]`

### Settled by Plan

- [Architecture decision 1]
- [Architecture decision 2]
- [Architecture decision 3]

### Sketch Must Preserve

- [Boundary / contract / architecture rule]
- [Boundary / contract / architecture rule]

### Sketch May Extend

- [Repo-grounded refinement area]
- [Repo-grounded refinement area]

### Handoff Gaps

- [Gap 1]
- [Gap 2]

---

## Resolved Clarifications

| Clarification ID | Question | Accepted Answer | Files Updated | Impact |
|------------------|----------|-----------------|--------------|--------|
| C-001 | [Question asked] | [Accepted answer] | [path(s)] | [Effect on plan / contracts / risk] |

---

## Open Feasibility Questions

### Status

`[Empty | Non-empty]`

### Count

`[N]`

| FQ ID | Service / Capability | Probe | Blocking Component |
|-------|----------------------|-------|--------------------|
| FQ-001 | [Service / capability] | [Minimal test to run] | [Dependent component] |

---

## Final Status

### Files Updated

- `[path/to/file]`
- `[path/to/file]`

### Deferred Items

- [Deferred ambiguity and why]
- [Deferred risk and why]

### Risks to Sketch / Task Generation

- [Risk 1]
- [Risk 2]

### Recommended Next Step

- If Open Feasibility Questions are non-empty: `/speckit.feasibilityspike`
- If Open Feasibility Questions are empty: `/speckit.solution`