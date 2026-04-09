# Specification Quality Checklist: [FEATURE NAME]

**Purpose**: Validate specification completeness and quality before proceeding to planning  
**Created**: [DATE]  
**Feature**: [Link to spec.md]

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

## Requirement Completeness

- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous
- [ ] Success criteria are measurable
- [ ] Success criteria are technology-agnostic (no implementation details)
- [ ] All acceptance scenarios are defined
- [ ] Acceptance criteria are defined before the flowchart — behavior drives structure
- [ ] Every flowchart branch corresponds to at least one acceptance criterion (no orphaned branches)
- [ ] Every open question states its stakes — an OQ without stated consequence is not worth listing
- [ ] One-line purpose survives the elevator test (does not require a second sentence to be complete)
- [ ] Acceptance criteria cover at minimum: happy path, empty/zero state, auth/permission failure
- [ ] Edge cases cover at minimum: max volume, dependency unavailability, malformed input
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified
- [ ] If scope exclusions reference external tools/packages ("covered by X"), those tools have been verified as installable and functional — not just referenced by name
- [ ] If the feature's purpose is to trigger or orchestrate automated work (an agent run, a CLI command, a CI pipeline), the specific tool/command/agent that executes that work is named in at least one Functional Requirement — it is NOT left implicit inside a boundary assumption or adopted dependency
- [ ] Boundary assumptions each name their owner and a verifiability criterion — not just "X exists"
- [ ] If local state mirrors live external state, source-of-truth ownership and drift/fallback/fail behavior are explicit
- [ ] If local persisted state mutations are in scope, transaction boundaries + rollback/idempotency behavior are explicit
- [ ] If venue-constrained entities are in scope, metadata-first valid-object discovery and validated live-data request policy are explicit

## Feature Readiness

- [ ] All functional requirements have clear acceptance criteria
- [ ] User scenarios cover primary flows
- [ ] Feature meets measurable outcomes defined in Success Criteria
- [ ] No implementation details leak into specification
- [ ] Scope exclusions that delegate to external tools cannot be interpreted as PASS unless those tools have been verified as installable and runnable
- [ ] If the feature triggers automated work, validation cannot PASS while the executing tool/agent/command is unnamed in FRs — "evaluated by external workflow" is not sufficient
- [ ] Stateful external integrations cannot be interpreted as PASS with unresolved active-state drift
- [ ] Local DB mutation paths cannot be interpreted as PASS with partial writes or ambiguous commit outcomes
- [ ] Venue-constrained live-data integrations cannot be interpreted as PASS with synthetic non-validated object requests

## Notes

- Items marked incomplete require spec updates before `/speckit.clarify` or `/speckit.plan`
