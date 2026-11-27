# Feature Specification: Consolidate Edit Validation

## Consumer & Context *(mandatory)*

Coding agents and repository maintainers need one predictable validation experience that permits temporarily inconsistent multi-file work, avoids repeated validation and discovery refreshes, produces a trustworthy final quality decision, and preserves safe commit-time safeguards when governed workflow evidence is unavailable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workflow MUST track the repository paths affected by each edit so that validation and discovery-freshness decisions cover the relevant change set.
- **FR-002**: Saving an intermediate edit MUST NOT automatically run technical validators or synchronously refresh discovery data.
- **FR-003**: Coding agents MUST be able to sequence, inspect, and revise authorized multi-file changes without mandatory validation between intermediate edits.
- **FR-004**: The workflow MUST provide optional intermediate validation that applies the same pass, failure, and evidence rules used by final validation.
- **FR-005**: Task closeout MUST confirm that every applicable targeted test, lint check, static type check, and required documentation check succeeds before allowing handoff.
- **FR-006**: Task closeout MUST NOT offer a skip option or alternate path that bypasses a mandatory technical check.
- **FR-007**: Successful validation evidence MAY be reused only when the relevant content, validator configuration, dependencies, and test selection are unchanged.
- **FR-008**: A change to relevant content, validator configuration, dependencies, or test selection MUST invalidate the affected validation evidence.
- **FR-009**: For one unchanged validated state, the governed workflow MUST invoke each applicable mandatory validator no more than once.
- **FR-010**: An edit MUST mark each affected discovery backend and scope as stale without forcing an immediate refresh.
- **FR-011**: An authoritative read that depends on stale discovery state MUST refresh the affected scope before returning results, or fail without presenting stale results as authoritative.
- **FR-012**: Repeated authoritative reads against unchanged, current discovery state MUST NOT trigger another refresh.
- **FR-013**: Task closeout MUST verify and, when necessary, refresh every affected repository-discovery data source before handoff succeeds.
- **FR-014**: Commit-time safeguards MUST remain active for direct Git activity outside the governed task workflow.
- **FR-015**: A commit-time validation or refresh MAY be skipped only when evidence proves that the exact staged or committed content and relevant configuration already satisfy that safeguard.
- **FR-016**: Missing, stale, unverifiable, or mismatched commit evidence MUST cause the existing commit-time safeguard to run.
- **FR-017**: Workflow documentation MUST identify one unambiguous owner and execution point for edit tracking, optional validation, mandatory final validation, on-demand freshness, final freshness, and commit fallback safeguards.
- **FR-018**: Existing bounded-read rules, discovery entry points, governance gates, audit trails, continuous-integration checks, and behavioral and semantic quality checks MUST remain effective.
- **FR-019**: Regression coverage MUST include intermediate-edit behavior, optional and final validation, direct-commit safeguards, freshness detection, and a temporarily inconsistent multi-file change that passes all final checks after consistency is restored.
- **FR-020**: The workflow MUST produce comparable before-and-after measurements for validator invocations, refresh invocations, validation elapsed time, task completion time, and acceptance-test success rate on equivalent tasks.

### Key Entities

- **Changed-path set**: The bounded collection of repository paths affected since the last proven state.
- **Validation evidence**: Proof of successful technical checks tied to the relevant content, configuration, dependencies, test selection, and validator identity.
- **Discovery freshness state**: The current, stale, or unverifiable status of an affected discovery backend and scope.
- **Commit evidence**: Proof that a commit safeguard already succeeded against the exact staged or committed state and relevant configuration.
- **Task closeout decision**: The permitted or rejected handoff based on mandatory validation, discovery freshness, governance, and quality checks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A regression scenario with temporarily inconsistent multi-file edits records zero automatic technical-validator failures during intermediate edits and passes mandatory final validation after consistency is restored.
- **SC-002**: For an unchanged successful governed task, each applicable mandatory technical validator runs no more than once for the validated state.
- **SC-003**: Repeated authoritative reads against unchanged, current content cause zero duplicate refreshes for every supported discovery backend.
- **SC-004**: In regression coverage, 100% of authoritative reads that encounter stale discovery state either refresh before returning results or fail without labeling stale results authoritative.
- **SC-005**: In regression coverage, 100% of closeout attempts containing a failing targeted test, lint error, type error, missing required documentation, or unverifiable affected discovery state are rejected.
- **SC-006**: In regression coverage, direct commits with missing or mismatched evidence execute the applicable safeguards, while exact matching evidence causes no duplicate validator or refresh invocation.
- **SC-007**: Before-and-after benchmark results report validator invocations, refresh invocations, validation elapsed time, task completion time, and acceptance-test success rate for equivalent implementation tasks without reducing acceptance-test success.
- **SC-008**: A review of active workflow documentation finds no contradictory ownership or timing rules for edit tracking, intermediate validation, final validation, discovery refresh, or commit safeguards.

## Definition of Done *(mandatory)*

The feature is complete in the production repository workflow when coding agents can assemble temporarily inconsistent multi-file edits without automatic technical validation, every successful closeout passes mandatory quality and discovery-freshness checks, unchanged proven work is not repeated, direct Git activity retains its safeguards, and all measurable outcomes above are demonstrated by regression and benchmark evidence.

## Open Questions *(include if any unresolved decisions exist)*

- **OQ-001**: Must reusable validation evidence match only changed content and validator configuration, or the complete dependency and execution environment? **Stakes**: A boundary that is too narrow risks accepting invalid evidence; one that is too broad preserves redundant work.
- **OQ-002**: Which discovery operations count as authoritative reads and therefore require freshness enforcement before returning results? **Stakes**: An incomplete list can expose stale results, while an overly broad list can reintroduce unnecessary refreshes.
- **OQ-003**: Which representative implementation tasks and baseline runs will be used for before-and-after measurements? **Stakes**: Without a shared comparison set, efficiency gains may not be comparable or may mask acceptance-quality regressions.
