# Effort Estimate: Read-Code Anchor Output Simplification

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|--------|--------|-------------|-----------|
| T000 | 1 | Validate the solution-review handoff and readiness gate before implementation work begins | Single-file check of existing plan/review state; no code changes. |
| T001 | 1 | Confirm the current read-code seam and existing helper entrypoints that the implementation will extend | Narrow discovery task against one helper module. |
| T002 | 3 | Introduce a normalized composite confidence score on a `0-100` scale and widen semantic retrieval to `top_k = 20` | Touches the core ranking path and query width in `scripts/read_code.py`; moderate logic but still one module. |
| T003 | 3 | Refactor the anchor formatter to produce a ranked shortlist of 5 candidates instead of a single forced anchor | Output shaping plus ranking changes in the same helper module; enough logic to merit a medium estimate. |
| T004 | 2 | Add top-candidate body selection logic so the highest-confidence candidate returns its indexed body inline when confidence is at least `90/100` | Clear existing pattern reuse from the indexed `body` field; bounded change in one module. |
| T005 | 3 | Update `read_code_context` output formatting to render the shortlist and the inline top-body payload together | Output contract change plus coordination with ranking state and threshold gating. |
| T006 | 2 | Add deterministic tie-break handling so shortlist ordering stays stable for the same input and index snapshot | Existing rank tuple can be extended with a stable tie-break; limited surface. |
| T007 | 2 | Add regression coverage for shortlist size, confidence normalization, and top-body gating | Straightforward integration-style assertions against the current helper contract. |
| T008 | 3 | Add a bounded internal helper path for selecting a non-top shortlist candidate and returning its indexed body | Introduces the follow-up body path and selection logic; still confined to the helper family. |
| T009 | 2 | Add regression coverage for the non-top candidate follow-up path and bounded retry behavior | Testing the new helper path is straightforward once the core behavior exists. |
| T010 | 1 | Update `AGENTS.md` with the read-code rule source, the top-5 shortlist, the `90/100` cutoff, and the bounded follow-up helper rule | Docs-only change in a single markdown file. |
| T011 | 1 | Update the feature quickstart with shortlist/body examples and the follow-up helper explanation | Docs-only change in a single markdown file. |
| T012 | 1 | Align `scripts/read-code.sh` help text and usage guidance with the new shortlist/body contract | Small shell wrapper documentation tweak, no new logic. |
| T013 | 1 | Confirm the solution-review and tasking artifacts remain consistent with the sketch contract after implementation edits | Process/documentation safeguard only; no code path changes. |

## Solution Sketch — T002

### Existing symbols to modify

- `scripts/read_code.py:_vector_query_line_num`
- `scripts/read_code.py:_vector_anchor_rank`
- `scripts/read_code.py:_vector_match_for_item`

### New symbols to create

- `scripts/read_code.py:normalized_composite_confidence` or equivalent internal helper

### Composition

- Reuse the existing rank signals, but normalize them into a single `0-100` confidence score.
- Increase the retrieval pool to `top_k = 20` before shortlist selection.
- Keep the score deterministic so repeated reads yield the same output for the same indexed snapshot.

### Failing assertion

- A task-specific test should fail if the helper still emits the old narrow retrieval width or if the confidence score is not normalized to `0-100`.

### Domains touched

- 17 Code patterns
- 04 Caching & performance

## Solution Sketch — T003

### Existing symbols to modify

- `scripts/read_code.py:_vector_query_line_num`
- `scripts/read_code.py:_vector_anchor_rank`
- `scripts/read_code.py:read_code_context`

### New symbols to create

- `scripts/read_code.py:render_anchor_shortlist` or equivalent internal formatter

### Composition

- Convert the best-match-only pipeline into a shortlist formatter.
- Return the top 5 candidates in ranked order.
- Preserve exact-symbol and body/docstring preference in deterministic tie-breaks.

### Failing assertion

- A task-specific test should fail if the helper still returns one candidate only or if shortlist ordering changes between identical runs.

### Domains touched

- 17 Code patterns
- 12 Testing

## Solution Sketch — T005

### Existing symbols to modify

- `scripts/read_code.py:read_code_context`
- `scripts/read_code.py:_render_numbered_window`

### New symbols to create

- `scripts/read_code.py:render_top_candidate_body` or equivalent internal formatter

### Composition

- Keep `read_code_context` as the anchor-seeking entrypoint.
- After shortlist generation, attach the top candidate's body when confidence is at least `90/100`.
- Preserve the shortlist in the response so the agent can still pick alternatives later.

### Failing assertion

- A task-specific test should fail if the top candidate's body is omitted at or above the threshold or if the shortlist disappears.

### Domains touched

- 17 Code patterns
- 12 Testing

## Solution Sketch — T008

### Existing symbols to modify

- `scripts/read_code.py:read_code_context`
- `scripts/read_code.py:read_code_window`

### New symbols to create

- `scripts/read_code.py:candidate_body_helper` or equivalent internal helper

### Composition

- Add a bounded follow-up path that selects a non-top shortlist candidate and returns that candidate's indexed body.
- Keep the helper family small and avoid introducing a new top-level command sprawl.
- Reuse the same candidate identity metadata already present in the shortlist.

### Failing assertion

- A task-specific test should fail if the helper cannot retrieve a later shortlisted candidate's body or if it allows unbounded retry behavior.

### Domains touched

- 17 Code patterns
- 12 Testing
- 13 Identity & access (selection boundary for candidate identity)

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 2 | 2 | 0 |
| Phase 2: Foundational | 8 | 3 | 0 |
| Phase 3: User Story 1 | 7 | 3 | 0 |
| Phase 4: User Story 2 | 5 | 2 | 0 |
| Phase 5: User Story 3 | 4 | 4 | 2 |
| Phase N: Polish & Cross-Cutting | 2 | 2 | 2 |
| **Total** | **26** | **14** | **4** |

## Warnings

- No task scores 8 or 13.
- No breakdown pass is required.
- The highest-effort implementation slices are the ranking/shortlist formatter tasks and the bounded follow-up body helper.
