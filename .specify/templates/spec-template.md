# Feature Specification: [FEATURE NAME]

**Feature Branch**: `[###-feature-name]`
**Created**: [DATE]
**Status**: Draft
**Input**: User description: "$ARGUMENTS"

## One-Line Purpose *(mandatory)*

<!--
  REQUIRED: Exactly one sentence. Subject = actor. Verb = behavior. Object = outcome.
  No implementation language. If it requires a second sentence, it is not done yet.
-->

[Single sentence: who does what to achieve what outcome]

## Consumer & Context *(mandatory)*

<!--
  REQUIRED: Exactly one sentence identifying who or what receives the output and in what
  environment (browser session, API client, batch job, pipeline stage, etc.).
  This drives architecture decisions without prescribing them.
-->

[Single sentence: who/what consumes this and in what context]

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently - e.g., "Can be fully tested by [specific action] and delivers [specific value]"]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]
2. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

### User Story 3 - [Brief Title] (Priority: P3)

[Describe this user journey in plain language]

**Why this priority**: [Explain the value and why it has this priority level]

**Independent Test**: [Describe how this can be tested independently]

**Acceptance Scenarios**:

1. **Given** [initial state], **When** [action], **Then** [expected outcome]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right edge cases.
-->

- What happens when [boundary condition]?
- How does system handle [error scenario]?

## Flowchart *(mandatory)*

<!--
  REQUIRED: Generate a Mermaid flowchart covering the happy path and every decision branch.
  Rules:
  - Every branch must correspond to at least one acceptance scenario above
  - Every acceptance scenario must appear as at least one branch
  - No orphaned branches (branches with no corresponding acceptance scenario)
  - Use flowchart TD (top-down) direction
-->

```mermaid
flowchart TD
    [START] --> [first step]
    [first step] --> [decision or outcome]
```

## Data & State Preconditions *(mandatory)*

<!--
  REQUIRED: What data must exist and in what state before this feature can execute.
  Cover: required upstream records, session/auth state, consistency constraints.
  Do NOT describe how data is stored or retrieved — only what must be true.
-->

- [Required upstream record or auth state]
- [Consistency constraint that must hold]

## Inputs & Outputs *(mandatory)*

<!--
  REQUIRED: Two-row table only. Set Format to "Caller-defined" — do not specify
  field names, types, or transport layer. That is for the technical plan.
-->

| Direction | Description | Format |
| :-- | :-- | :-- |
| Input | [what goes in] | Caller-defined |
| Output | [what comes out] | Caller-defined |

## Constraints & Non-Goals *(mandatory)*

<!--
  REQUIRED: Up to three sub-sections.
  Must NOT = hard behavioral limits the implementation cannot violate.
  Adopted dependencies = external tools/packages that deliver part of the feature's capability.
    These are IN SCOPE — they require integration work (install, configure, verify, test, document).
    Do NOT list adopted dependencies under "Out of scope" — that erases them from tasks and testing.
  Out of scope = things this feature genuinely does NOT do, even via external tools.
-->

**Must NOT**:
- [Hard limit, e.g., "Must NOT expose raw error stack traces to the consumer"]
- [Hard limit, e.g., "Must NOT block the calling thread during processing"]

**Adopted dependencies** *(include if feature uses external tools/packages to deliver capability)*:
- [External tool, e.g., "CodeGraphContext — provides graph-based code intelligence (search, callers, hierarchy). Requires: install, index build, MCP registration, verification."]

**Out of scope** *(things this feature genuinely does not do, even via external tools)*:
- [True exclusion, e.g., "Multi-repository support"]
- [True exclusion, e.g., "Cloud-hosted deployment"]

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: The content in this section represents placeholders.
  Fill them out with the right functional requirements.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]
- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g., "log all security events"]

*Example of marking unclear requirements:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]
- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

### Key Entities *(include if feature involves data)*

- **[Entity 1]**: [What it represents, key attributes without implementation]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g., "Users can complete account creation in under 2 minutes"]
- **SC-002**: [Measurable metric, e.g., "System handles 1000 concurrent users without degradation"]
- **SC-003**: [User satisfaction metric, e.g., "90% of users successfully complete primary task on first attempt"]
- **SC-004**: [Business metric, e.g., "Reduce support tickets related to [X] by 50%"]

## Definition of Done *(mandatory)*

<!--
  REQUIRED: Exactly one sentence. Describes the observable product-level state
  that means this is shipped in production — not just "ACs pass."
  Must reference production environment. Must reference any latency or quality
  threshold stated in the acceptance scenarios if one exists.
-->


[Single sentence: observable state in production that means this feature is shipped]

## Delivery Routing & Rough Size *(mandatory)*

<!--
  REQUIRED: This section routes the backlog item through the right amount of downstream process.
  This is NOT the implementation estimate. It is a rough sizing and risk screen used to decide
  whether research, plan, and full sketch are needed.

  Sizing intent:
  - XS/S/M/L/XL = process size and uncertainty, not story points.
  - Final task points belong in estimate.md after sketch + tasking/HUDs exist.

  Routing principles:
  - Research can be skipped when no external dependency, prior art, package/API choice,
    security/regulatory ambiguity, or unfamiliar technology needs investigation.
  - Plan can be skipped when existing architecture, state model, contracts, runtime flow,
    and trust boundaries already cover the item.
  - Sketch is required for every implementation item that reaches tasking, but should be
    proportional to size. XS items may use only the core sketch sections.
  - Existing-spec coverage should be preferred over creating a new spec when the backlog item
    is a delta, clarification, bug, refactor, test-only change, docs/template update, or ops task.
-->

### Item Classification

| Field | Value | Notes |
|-------|-------|-------|
| Work type | `[New feature / Existing feature delta / Bug / Refactor / Docs / Test-only / Ops]` | [Why] |
| Existing spec coverage | `[Full / Partial / None]` | [Relevant feature/spec ID or N/A] |
| Required spec action | `[None / Clarification / New requirement / New acceptance scenario / New spec]` | [Why] |

### Rough Size

T-shirt size: `[XS / S / M / L / XL]`

Reasoning:
- [One short paragraph explaining process size, uncertainty, and expected downstream complexity.]

Use this calibration:

| Size | Meaning | Typical Routing |
|------|---------|-----------------|
| XS | One obvious repo-local change, usually one seam, no new architecture or research | Research skip, Plan skip, Sketch core only |
| S | Small repo-local change using existing architecture, small contract/test detail | Research skip, Plan skip or lite, Sketch core plus any triggered sections |
| M | Multiple seams or one meaningful design decision, existing architecture mostly applies | Research skip unless unknowns, Plan lite, Sketch expanded |
| L | New or materially changed architecture, state, interface, workflow, or artifact/event lifecycle | Research as needed, Plan full, Sketch expanded with slices |
| XL | Cross-cutting, external, security/data-heavy, unclear feasibility, or likely multi-feature work | Research required, Plan full, Sketch expanded; consider splitting spec |

### Risk / Uncertainty

| Dimension | Level | Reason |
|-----------|-------|--------|
| Requirement clarity | `[Low / Medium / High]` | [Why] |
| Repo uncertainty | `[Low / Medium / High]` | [Why] |
| External dependency uncertainty | `[Low / Medium / High]` | [Why] |
| State / data / migration risk | `[Low / Medium / High]` | [Why] |
| Runtime / side-effect risk | `[Low / Medium / High]` | [Why] |
| Human/operator dependency | `[Low / Medium / High]` | [Why] |

### Phase Routing

| Downstream Phase | Decision | Reason |
|------------------|----------|--------|
| Research | `[Skip / Required]` | [Why] |
| Plan | `[Skip / Lite / Full]` | [Why] |
| Sketch | `[Required]` | [Why; every implementation item that reaches tasking needs at least the core sketch] |
| Tasking | `[Required / Attach to existing feature]` | [Why] |
| Estimate | `[Required after tasking / Reuse existing estimate]` | [Why] |

### Routing Contract

Fill this block with the same routing and risk decisions above. Downstream automation reads this block.

```json
{
  "routing": {
    "research_route": "",
    "plan_profile": "",
    "sketch_profile": "",
    "tasking_route": "",
    "estimate_route": "",
    "routing_reason": "",
    "conditional_sketch_sections": []
  },
  "risk": {
    "requirement_clarity": "",
    "repo_uncertainty": "",
    "external_dependency_uncertainty": "",
    "state_data_migration_risk": "",
    "runtime_side_effect_risk": "",
    "human_operator_dependency": ""
  }
}
```

### Existing-Spec Attachment

If this item is covered by an existing spec, state how it should attach:

- Existing feature/spec: `[ID or N/A]`
- Attach as: `[Acceptance clarification / New acceptance scenario / Task candidate / Bug against existing behavior / Refactor / Docs-template update / Duplicate]`
- New spec required? `[Yes / No]`
- Rationale: [Why]

### Routing Gate

- [ ] Work type is classified.
- [ ] Existing spec coverage is checked.
- [ ] Rough size is assigned.
- [ ] Risk/uncertainty dimensions are assigned.
- [ ] Research route is justified.
- [ ] Plan route is justified.
- [ ] Sketch is required and right-sized.
- [ ] Tasking/estimate route is justified.

## Open Questions *(include if any unresolved decisions exist)*

<!--
  List unresolved decisions that would materially change the ACs if assumed wrong.
  Format: OQ-N: [Question] Stakes: [what goes wrong if assumed incorrectly]
  Do NOT answer OQs here — surface only.
-->

- **OQ-1**: [Question] Stakes: [consequence of wrong assumption]
