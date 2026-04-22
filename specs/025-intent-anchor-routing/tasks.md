# Tasks: Read-Code Anchor Output Simplification

## Format: `[ID] [P?] [H?] [USN?] Description — file:symbol`

## Path Conventions

- Use repository-relative paths.
- Anchor each task to the primary file/symbol it changes.
- Keep task ordering aligned to the sketch: ranking/shortlist first, follow-up body helper second, docs and verification third.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the repo and phase state are ready for implementation.

- [ ] T000 Validate the solution-review handoff and readiness gate before implementation work begins — `specs/025-intent-anchor-routing/plan.md:Open Feasibility Questions`
- [ ] T001 Confirm the current read-code seam and existing helper entrypoints that the implementation will extend — `scripts/read_code.py:read_code_context`

**Checkpoint**: The solution review is green, the feature scope is still bounded, and the current helper seams are understood.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared confidence/ranking contract that all user stories depend on.

- [ ] T002 Introduce a normalized composite confidence score on a `0-100` scale and widen semantic retrieval to `top_k = 20` — `scripts/read_code.py:_vector_anchor_rank`
- [ ] T003 Refactor the anchor formatter to produce a ranked shortlist of 5 candidates instead of a single forced anchor — `scripts/read_code.py:_vector_query_line_num`
- [ ] T004 Add top-candidate body selection logic so the highest-confidence candidate returns its indexed body inline when confidence is at least `90/100` — `scripts/read_code.py:read_code_context`

**Checkpoint**: The helper can produce a bounded shortlist and a top-body payload using the normalized score contract.

---

## Phase 3: User Story 1 - Ranked Shortlist and Inline Top Body (Priority: P1) 🎯 MVP

**Goal**: `read_code_context` returns a shortlist of candidates with normalized confidence, and the top candidate body comes back inline when it clears the threshold.

**Independent Test**: A semantic query returns 5 candidates, each with confidence, and the top candidate includes its body when confidence is at least `90/100`.

### Implementation for User Story 1

- [ ] T005 [US1] Update `read_code_context` output formatting to render the shortlist and the inline top-body payload together — `scripts/read_code.py:read_code_context`
- [ ] T006 [US1] Add deterministic tie-break handling so shortlist ordering stays stable for the same input and index snapshot — `scripts/read_code.py:_vector_anchor_rank`
- [ ] T007 [US1] Add regression coverage for shortlist size, confidence normalization, and top-body gating — `tests/integration/test_read_code_python_migration.py:read_code_context`

---

## Phase 4: User Story 2 - Bounded Follow-Up Body Helper (Priority: P2)

**Goal**: The agent can ask for the body of a non-top shortlisted candidate later, without introducing a new sprawling command family.

**Independent Test**: Given a shortlisted candidate that is not the top result, the helper can return that candidate's body through a bounded follow-up path.

### Implementation for User Story 2

- [ ] T008 [US2] Add a bounded internal helper path for selecting a non-top shortlist candidate and returning its indexed body — `scripts/read_code.py:candidate_body_helper`
- [ ] T009 [US2] Add regression coverage for the non-top candidate follow-up path and bounded retry behavior — `tests/integration/test_read_code_python_migration.py:read_code_context`

---

## Phase 5: User Story 3 - Agent Rules and Quickstart (Priority: P3)

**Goal**: Agents can find the read-code rules before attempting large reads and know how to use the shortlist/body contract.

**Independent Test**: The agent-facing docs clearly explain the shortlist, confidence threshold, top-body behavior, and the bounded follow-up helper.

### Implementation for User Story 3

- [X] T010 [US3] Update `AGENTS.md` with the read-code rule source, the top-5 shortlist, the `90/100` cutoff, and the bounded follow-up helper rule — `AGENTS.md:read-code rules`
- [X] T011 [US3] Update the feature quickstart with shortlist/body examples and the follow-up helper explanation — `specs/025-intent-anchor-routing/quickstart.md:What This Feature Is`

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Validate the user-facing contract and keep the helper surface elegant.

- [X] T012 [P] [US3] Align `scripts/read-code.sh` help text and usage guidance with the new shortlist/body contract — `scripts/read-code.sh:read_code_context`
- [X] T013 [P] [US3] Confirm the solution-review and tasking artifacts remain consistent with the sketch contract after implementation edits — `specs/025-intent-anchor-routing/solutionreview.md:Final Decision`

---

## Dependencies & Execution Order

### Phase Dependencies

1. Phase 1 must complete before any implementation work starts.
2. Phase 2 must complete before Phase 3 and Phase 4 because they depend on the shared confidence/shortlist contract.
3. Phase 3 can begin once the shortlist formatter is in place.
4. Phase 4 depends on the shortlist contract from Phase 2.
5. Phase 5 can run after the user story work stabilizes.

### User Story Dependencies

- User Story 1 depends on the normalized confidence and shortlist formatter tasks.
- User Story 2 depends on User Story 1's shortlist contract.
- User Story 3 depends on the settled behavior of the helper so the docs match reality.

### Within Each User Story

- Implement the main seam first.
- Add regression coverage second.
- Keep task scope narrow and file-anchored.

### Parallel Opportunities

- T006 and T007 can run in parallel after T005 stabilizes the formatting contract.
- T010 and T011 can run in parallel after the behavior is settled.

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Normalize the confidence score.
2. Return a top-5 shortlist.
3. Inline the body for the top candidate at `90/100` or above.

### Incremental Delivery

1. Add the bounded follow-up body helper.
2. Add the agent-facing docs.
3. Polish the shell help text and review consistency.

### Parallel Team Strategy

1. One person can work on ranking and shortlist formatting.
2. One person can work on the bounded follow-up helper.
3. One person can update docs and quickstart text once the contract is stable.

## Notes

- The sketch explicitly forbids adding a new command family; keep the helper surface small.
- Numeric line windows remain intact and useful for exact-context reads.
- Any implementation that changes the public behavior must preserve the bounded shortlist and the normalized confidence cutoff.
