# Sketch Blueprint — [FEATURE_NAME]

_Date: [DATE]_  
_Feature: `[FEATURE_ID]`_  
_Source Plan: `plan.md`_  
_Artifact: `sketch.md`_

## Feature Solution Frame

### Core Capability

[Describe the capability or change surface being implemented.]

### Current → Target Transition

[Describe what exists today, what the approved plan intends, and what changes in the target state.]

### Dominant Execution Model

[Describe the main control model.]

### Main Design Pressures

- [Constraint / pressure 1]
- [Constraint / pressure 2]
- [Constraint / pressure 3]

---

## Solution Narrative

[Explain what is being built, what is being reused, what is being introduced, and how the solution comes together.]

---

## Construction Strategy

1. [First major construction move]
2. [Second major construction move]
3. [Third major construction move]
4. [Additional moves as needed]

### Construction Notes

- [Sequencing note]
- [Dependency note]
- [Risk note]

---

## Acceptance Traceability

| Story / Requirement / Constraint | Design Element(s) That Satisfy It | Reuse / Modify / Create | Verification / Migration Note |
|----------------------------------|-----------------------------------|-------------------------|-------------------------------|
| [FR / Story / Constraint] | [Design anchor] | [Reuse / Modify / Create] | [Note] |

---

## Work-Type Classification

| Capability / Story Area | Work Type(s) | Dominant Pattern in Repo | Reuse-First / Extension-First / Net-New | Special Constraints |
|-------------------------|--------------|---------------------------|-----------------------------------------|--------------------|
| [Area] | [Types] | [Pattern] | [Mode] | [Constraints] |

---

## Current-System Inventory

| Surface | Type | Role Today | Relationship to Feature | Condition | Primary Seam or Blast Radius Only |
|---------|------|------------|--------------------------|-----------|-----------------------------------|
| [Name / file / module / artifact] | [module/script/template/config/etc.] | [What it does] | [How feature uses or affects it] | [Reusable / Extension-friendly / Brittle / Mismatched] | [Primary / Blast radius] |

---

## Command / Script Surface Map

| Name | Owning File / Script / Template | Pipeline Role | Classification | Inputs | Outputs / Artifacts | Events | Extension Seam | Planned Change |
|------|---------------------------------|---------------|----------------|--------|----------------------|--------|----------------|----------------|
| [Command / script / manifest entry] | [Owner] | [Role] | [Deterministic / Human / External / Hybrid] | [Inputs] | [Outputs] | [Events] | [Seam] | [Reuse / Wrap / Modify / New] |

---

## CodeGraphContext Findings

### Seed Symbols

- `[file.py:symbol_name]` — [why it is a seed]
- `[file.py:symbol_name]` — [why it is a seed]

### Primary Implementation Surfaces

| File | Symbol(s) | Why This Surface Is Primary | Planned Change Type |
|------|-----------|-----------------------------|---------------------|
| [file] | [symbols] | [reason] | [Reuse / Modify / Create] |

### Secondary Affected Surfaces

| File / Surface | Why It Is Affected | Type of Impact |
|----------------|--------------------|----------------|
| [file / surface] | [reason] | [Blast radius / regression / observability / rollout / operator / docs] |

### Caller / Callee / Dependency Notes

- [Important relationship]
- [Important relationship]

### Missing Seams or Contradictions

- [Contradiction between plan and repo reality]
- [Missing seam that the design depends on]

---

## Blast Radius

### Direct Implementation Surfaces

- [Surface 1]
- [Surface 2]

### Indirect Affected Surfaces

- [Surface 1]
- [Surface 2]

### Regression-Sensitive Neighbors

- [Neighbor 1]
- [Neighbor 2]

### Rollout / Compatibility Impact

- [Impact 1]
- [Impact 2]

### Operator / Runbook / Deployment Impact

- [Impact 1]
- [Impact 2]

---

## Reuse / Modify / Create Matrix

### Reuse Unchanged

- [Component / file / script / artifact]

### Modify / Extend Existing

- [Component / file / script / artifact]

### Compose from Existing Pieces

- [Composed solution element]

### Create Net-New

- [New seam / module / interface / artifact]

### Reuse Rationale

[Explain why this mix is the best realization of the approved plan in the actual repo.]

---

## Manifest Alignment Check

| Affected Command / Phase | Existing Manifest Coverage? | New Artifact Needed? | New Event / Field Needed? | Handoff / Event Flow Impact | Status |
|--------------------------|-----------------------------|----------------------|---------------------------|-----------------------------|--------|
| [Command / phase] | [Yes / No / Partial] | [artifact or N/A] | [event/field or N/A] | [impact] | [Aligned / Needs update / Blocking] |

### Manifest Alignment Notes

- [Important note]

---

## Architecture Flow Delta

Choose one:

- **No Architecture Flow delta**
- **Architecture Flow refined**

### Delta Summary

[If no delta, state that the plan-level Architecture Flow remains correct. If refined, describe only what changed.]

### Added / Refined Nodes, Edges, or Boundaries

| Change | Why Needed at LLD Level | Must Preserve in Tasking / Implementation |
|--------|--------------------------|-------------------------------------------|
| [Node / edge / boundary change] | [reason] | [constraint] |

---

## Component and Boundary Design

| Component / Boundary | Responsibility | Owning or Likely Touched File(s) | Likely Touched Symbol(s) | Reuse / Modify / Create | Inbound Dependencies | Outbound Dependencies |
|----------------------|----------------|----------------------------------|--------------------------|-------------------------|---------------------|----------------------|
| [Component] | [responsibility] | [files] | [symbols] | [mode] | [deps] | [deps] |

### Control Flow Notes

- [Important control-flow detail]

### Data Flow Notes

- [Important data-flow detail]

---

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

| Interface / Contract | Purpose | Owner | Validation Point | Failure / Error Shape |
|----------------------|---------|-------|------------------|-----------------------|
| [Interface / schema / contract] | [purpose] | [owner] | [where validated] | [error/result shape] |

### New or Changed Public Symbols

| Symbol | Exact Intended Signature | Layer / Module | Responsibility | Notes |
|--------|---------------------------|----------------|----------------|------|
| [symbol] | `[exact signature]` | [layer/module] | [responsibility] | [notes] |

### Ownership Boundaries

- [Boundary 1]
- [Boundary 2]

---

## State / Lifecycle / Failure Model

### State Authority

| State / Field / Lifecycle Area | Authoritative Source | Reconciliation Rule | Notes |
|--------------------------------|----------------------|---------------------|------|
| [state area] | [source of truth] | [rule] | [notes] |

### Lifecycle / State Transitions

| Transition | Allowed? | Trigger | Validation / Guard | Failure Handling |
|------------|----------|---------|--------------------|------------------|
| [A -> B] | [Yes / No] | [trigger] | [guard] | [handling] |

### Retry / Replay / Ordering / Cancellation

- Retry behavior: [description]
- Duplicate / replay handling: [description]
- Out-of-order handling: [description]
- Cancellation / timeout behavior: [description]

### Degraded Modes / Fallbacks / Recovery

- [Degraded mode 1]
- [Fallback rule 1]
- [Recovery expectation 1]

---

## Non-Functional Design Implications

| Concern | Design Implication | Affected Surface(s) | Notes |
|---------|--------------------|---------------------|-------|
| [Latency / throughput / concurrency / observability / security / rollout / config] | [implication] | [surfaces] | [notes] |

---

## Human-Task and Operator Boundaries

| Boundary | Why Human / Operator Action Is Required | Preconditions | Artifact / Evidence Consumed | Downstream `[H]` Implication | Failure / Escalation Path |
|----------|-----------------------------------------|---------------|------------------------------|------------------------------|---------------------------|
| [Boundary] | [reason] | [preconditions] | [artifact/evidence] | [tasking implication] | [path] |

---

## Verification Strategy

### Unit-Testable Seams

- [Seam 1]

### Contract Verification Needs

- [Need 1]

### Integration / Reality-Check Paths

- [Path 1]

### Lifecycle / Retry / Duplicate Coverage Needs

- [Need 1]

### Deterministic Oracles (if known)

- [Oracle 1]

### Regression-Sensitive Areas

- [Area 1]

---

## Domain Guardrails

| Domain | Why Touched | MUST Constraints | Forbidden Shortcuts | Invariants to Preserve |
|--------|-------------|------------------|---------------------|------------------------|
| [Domain number + name] | [why] | [constraints] | [shortcuts] | [invariants] |

---

## LLD Decision Log

| Subject | Status | Rationale | Downstream Implication | May Tasking Proceed? |
|---------|--------|-----------|------------------------|----------------------|
| [decision subject] | [Decided / Assumed / Deferred / Blocked / Needs manifest update / Needs human confirmation] | [rationale] | [implication] | [Yes / No / Conditional] |

---

## Design Gaps and Repo Contradictions

### Missing Seams

- [Gap 1]

### Unsupported Assumptions

- [Assumption 1]

### Plan vs Repo Contradictions

- [Contradiction 1]

### Blocking Design Issues

- [Blocking issue 1]

---

## Design-to-Tasking Contract

Tasking must follow these rules:

- Every decomposition-ready design slice must produce at least one task unless an explicit omission rationale is recorded.
- No task may introduce scope, seams, symbols, interfaces, or artifacts absent from this sketch without explicit rationale.
- `[H]` tasks may only come from identified human/operator boundaries or explicit external dependency constraints.
- `file:symbol` annotations in tasks must trace back to symbol targets or symbol-creation notes in this sketch.
- Acceptance artifacts must derive from the verification intent and acceptance traceability in this sketch.
- Large-point tasks that require later breakdown must preserve the originating design slice and its safety invariants.

### Additional Tasking Notes

- [Additional rule or note]

---

## Decomposition-Ready Design Slices

### Slice [N]: [Slice Name]

**Objective**  
[What this slice accomplishes.]

**Touched Files**  
- `[path/to/file.ext]`

**Touched Symbols**  
- `[file.py:symbol_name]`

**Likely Net-New Files**  
- `[path/to/new_file.ext]`

**Primary Seam**  
[Primary seam]

**Blast-Radius Neighbors**  
- `[neighbor surface]`

**Reuse / Modify / Create Classification**  
[Reuse / Modify / Create]

**Required Public Symbols / Interfaces**  
- `[symbol or interface]`

**Major Constraints**  
- [Constraint 1]

**Dependencies on Other Slices**  
- [Dependency 1]

**Likely Verification / Regression Concern**  
[What downstream verification must pay special attention to.]

_Add as many slices as needed._

---

## Sketch Completion Summary

### Review Readiness

- [ ] The solution narrative is clear
- [ ] The construction strategy is coherent
- [ ] Acceptance traceability is complete
- [ ] Touched files and symbols are concrete enough for tasking
- [ ] Reuse / modify / create choices are explicit
- [ ] Manifest alignment is explicit where relevant
- [ ] Human-task boundaries are explicit where relevant
- [ ] Verification intent is sufficient for downstream artifact generation
- [ ] Domain MUST rules are preserved
- [ ] No blocking design contradiction remains unresolved

### Suggested Next Step

`/speckit.solutionreview`