# Sketch Blueprint — Read-Code Anchor Output Simplification

## Feature Solution Frame

### Core Capability

| Item | Decision |
|------|----------|
| Core capability | Return a bounded shortlist of anchor candidates with normalized confidence, inline body text for the top confident candidate, and a bounded follow-up body helper for other shortlisted candidates. |
| Primary user value | Agents can act on a stronger first result instead of retrying blind reads. |
| Public surface | Keep the existing `read_code_context` and `read_code_window` entrypoints. |

### Current -> Target Transition

| Current state | Target state |
|--------------|--------------|
| One best anchor + window/context output | Top-5 shortlist + normalized confidence + optional top-body inline + bounded follow-up body helper |
| Internal ranking scale is implicit | Normalized composite confidence on a `0-100` scale |
| `top_k` retrieval is narrow | Retrieval expands to `top_k = 20` before ranking |
| Agents infer the rules from trial/error | `AGENTS.md` explicitly documents the rules and the one-expansion limit |

### Dominant Execution Model

| Concern | Decision |
|--------|----------|
| Runtime style | CLI/helper-driven, not a new service or async runtime. |
| Read flow | Semantic retrieval -> deterministic ranking -> shortlist -> top-body inline -> bounded follow-up helper for other shortlisted candidates. |
| Determinism | Stable ordering, explicit confidence thresholds, bounded retry behavior. |

### Main Design Pressures

| Pressure | Design response |
|---------|-----------------|
| Token efficiency | Return the best body immediately and keep the shortlist bounded to 5. |
| Recall | Retrieve more candidates internally with `top_k = 20`. |
| Determinism | Use one normalized score and stable tie-break ordering. |
| Simplicity | Keep two entrypoints; add modes/flags and internal helpers rather than new top-level commands. |

## Solution Narrative

The solution keeps the current `read_code_context` and `read_code_window` entrypoints, but changes the shape of what they return. The helper will retrieve a wider semantic pool, compute a normalized composite confidence score from the existing ranking signals, return a shortlist of the top 5 candidates, and include the full indexed body for the top candidate when the confidence is at least `90/100`. If the agent wants the body for a non-top candidate, the same helper surface will expose a bounded follow-up body selection path rather than adding a family of new read functions.

This keeps the read workflow elegant:

1. The agent reads the shortlist once.
2. The agent gets the best body immediately when it is trustworthy.
3. The agent can ask for another shortlisted candidate's body later without leaving the same helper family.

## Construction Strategy

### Construction Notes

| Step | Implementation idea |
|------|---------------------|
| 1 | Expand the vector retrieval width in `scripts/read_code.py` from the narrow local default to `top_k = 20`. |
| 2 | Add a normalized composite confidence calculation that converts the existing ranking signals into a `0-100` score. |
| 3 | Change the formatter to return a ranked shortlist of 5 candidates instead of a single forced anchor. |
| 4 | Inline the body for the top candidate when confidence >= `90/100` and `body` exists. |
| 5 | Add a bounded follow-up helper path for a selected non-top candidate so the agent can fetch that candidate's body later. |
| 6 | Keep `read-code.sh` stable as the entrypoint and update its docs/flags only as needed. |

## Acceptance Traceability

| Plan requirement | Sketch design element |
|-----------------|----------------------|
| AGENTS.md rules first | Documented in the feature guide and quickstart. |
| Multiple anchor candidates | Shortlist formatter returns top 5 candidates. |
| Confidence threshold | Normalized `0-100` score, body-first at `90/100`. |
| Top candidate body inline | Response envelope includes top candidate body when confidence is high. |
| Other candidate bodies later | Follow-up helper for a selected shortlist candidate. |
| Wider retrieval pool | Vector retrieval widened to `top_k = 20`. |

## Work-Type Classification

| Work type | Classification |
|----------|-----------------|
| Code change | Medium-sized update in one Python helper module plus docs and tests. |
| Coordination | Low, because no new service boundary is introduced. |
| Risk | Medium, because score normalization and response shape must stay deterministic. |

## Current-System Inventory

| File / surface | Current role | Design impact |
|----------------|--------------|---------------|
| [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py) | Anchor resolution, ranking, and context/window printing | Primary implementation surface for shortlist/body behavior. |
| [`scripts/read-code.sh`](/Users/andreborczuk/app-foundation/scripts/read-code.sh) | Shell entrypoint | Keep stable; align docs and flags only. |
| [`AGENTS.md`](/Users/andreborczuk/app-foundation/AGENTS.md) | Agent rules and read limits | Must document the shortlist/body contract and the one-expansion rule. |
| [`src/mcp_codebase/index/domain.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/index/domain.py) | Indexed body already exists | Reuse `body` as the source for inline top-item body output. |
| [`src/mcp_codebase/indexer.py`](/Users/andreborczuk/app-foundation/src/mcp_codebase/indexer.py) | Vector query already supports top-k | Reuse the query surface and widen the requested candidate pool. |
| [`specs/025-intent-anchor-routing/plan.md`](/Users/andreborczuk/app-foundation/specs/025-intent-anchor-routing/plan.md) | Approved contract | The implementation must preserve the settled thresholds and boundedness. |

## Command / Script Surface Map

| Surface | Current shape | Target shape |
|--------|---------------|--------------|
| `read_code_context` | Find anchor, print numbered context | Return shortlist, confidence, and inline top body when threshold is met |
| `read_code_window` | Print bounded numeric slice, optionally anchored | Keep numeric slice behavior; preserve bounded follow-up reads and avoid new function sprawl |
| Internal body helper | None explicit | Add bounded helper logic to fetch/select body for a chosen shortlisted candidate |

## CodeGraphContext Findings

### Seed Symbols

| Symbol | Finding |
|-------|---------|
| `read_code_context` | Main caller entrypoint for anchored reads. |
| `read_code_window` | Main caller entrypoint for numeric windows. |
| `_vector_query_line_num` | Current retrieval path is narrow and single-anchor oriented. |
| `_vector_anchor_rank` | Existing ranking already favors exact symbol, body, and docstring signals. |
| `_resolve_line_num_strict` | Strict literal matching remains part of the anchor pipeline. |

### Primary Implementation Surfaces

| Surface | Why it matters |
|--------|----------------|
| `scripts/read_code.py` | Contains the ranking, retrieval width, and output formatting logic to change. |
| `scripts/read-code.sh` | The user-facing entrypoint that should continue to work unchanged. |

### Secondary Affected Surfaces

| Surface | Why it matters |
|--------|----------------|
| `AGENTS.md` | Must document the shortlist/body contract so agents know how to use it. |
| `quickstart.md` | Must show the shortlist and body-first usage pattern. |
| Tests | Must verify score normalization, bounded shortlist, and top-body behavior. |

### Caller / Callee / Dependency Notes

| Observation | Meaning |
|------------|---------|
| `main` calls both `read_code_context` and `read_code_window` | No new top-level CLI family is needed. |
| Both functions call the same lower-level anchor helpers | Shared output formatting is feasible without duplicating pipeline logic. |
| `cgc analyze deps scripts/read_code.py` did not surface dependency detail | No extra cross-module dependency work is visible for this feature right now. |

### Missing Seams or Contradictions

| Gap | Impact |
|----|--------|
| No normalized `0-100` confidence field today | The body-first threshold needs a real composite score contract. |
| No shortlist output today | The helper must add a structured candidate list instead of only one line anchor. |
| No explicit follow-up body helper today | Non-top candidate body retrieval must be added as a bounded mode/flag, not a new sprawl of commands. |

## Blast Radius

### Direct Implementation Surfaces

| File | Expected change |
|------|-----------------|
| `scripts/read_code.py` | Add shortlist formatter, normalized score, top-body inline behavior, and follow-up helper path. |
| `scripts/read-code.sh` | Update help text/docs if needed to explain the new response contract. |

### Indirect Affected Surfaces

| File | Expected change |
|------|-----------------|
| `AGENTS.md` | Document the read rules and the shortlist/body usage pattern. |
| `specs/025-intent-anchor-routing/quickstart.md` | Show how agents should read and select candidate bodies. |
| Tests | Add deterministic coverage for shortlist size, confidence gating, and follow-up body selection. |

### Regression-Sensitive Neighbors

| Surface | Risk |
|--------|------|
| Strict matching | Overly broad exact-match literals could still force ambiguous anchors. |
| Window mode | Must stay numeric and bounded; should not become the default retrieval path. |
| Helper limits | The one-expansion rule must remain bounded and deterministic. |

### Rollout / Compatibility Impact

| Impact | Assessment |
|-------|------------|
| Backward compatibility | High compatibility if current entrypoints remain stable. |
| Operator impact | Low; this is a local helper and docs change, not a service rollout. |
| User learning curve | Reduced once AGENTS.md documents the shortlist/body contract. |

### Operator / Runbook / Deployment Impact

| Impact | Assessment |
|-------|------------|
| Runbook | Update quickstart and AGENTS docs only. |
| Deployment | No deployment surface outside the repo. |
| Monitoring | Not applicable beyond tests and command output validation. |

## Reuse / Modify / Create Matrix

### Reuse Unchanged

| Piece | Why keep it |
|------|-------------|
| `scripts/read-code.sh` | Stable helper entrypoint with existing bounded-read semantics. |
| `src/mcp_codebase/index/domain.py` body fields | Already stores the symbol body we want to surface. |
| `src/mcp_codebase/indexer.py` retrieval interface | Already supports query top-k controls. |

### Modify / Extend Existing

| Piece | Change |
|------|--------|
| `scripts/read_code.py` | Compute normalized composite confidence, return shortlist, inline top body, add bounded follow-up helper mode. |
| `AGENTS.md` | Add explicit usage rules for shortlist, confidence, and follow-up body lookup. |

### Compose from Existing Pieces

| Piece | Composition |
|------|-------------|
| Shortlist response | Ranking signals + existing body/docstring metadata + normalized score. |
| Body-first response | Existing indexed `body` + confidence threshold + candidate identity. |

### Create Net-New

| Piece | Why it is net-new |
|------|-------------------|
| Internal shortlist formatter | The current code only emits a single anchor/window, not a ranked candidate list. |
| Bounded follow-up body helper path | Needed for non-top shortlisted candidates without creating a new command sprawl. |

### Reuse Rationale

The design stays inside the existing read-helper stack and reuses the indexed symbol body that already exists. The new behavior is a richer response contract, not a new service or database.

## Manifest Alignment Check

| Check | Status |
|------|--------|
| No new command manifest entry needed | PASS |
| Existing helper entrypoints remain intact | PASS |
| Solution phase uses current pipeline contract | PASS |

### Manifest Alignment Notes

The solution does not require a new CLI command. It expands the behavior of existing read helpers and the docs that tell agents how to use them.

## Architecture Flow Delta

### Delta Summary

| Stage | Current | Target |
|------|---------|--------|
| Retrieval | `top_k = 5` narrow candidate pull | `top_k = 20` broader candidate pull |
| Ranking | Best single anchor only | Normalized composite score and top-5 shortlist |
| Body handling | No inline body-first path | Inline top candidate body when score >= `90/100` |
| Follow-up | No explicit candidate-body selection helper | Bounded helper path for other shortlisted candidates |

### Added / Refined Nodes, Edges, or Boundaries

| Node / edge | Change |
|------------|--------|
| `read_code_context -> shortlist formatter` | New output edge that returns multiple candidates instead of one anchor. |
| `shortlist formatter -> top candidate body` | New additive edge for the highest-confidence candidate. |
| `shortlist formatter -> follow-up body helper` | New bounded edge for later candidate selection. |

## Component and Boundary Design

### Control Flow Notes

1. Parse the request and decide whether the helper is in anchor-seeking or numeric-window mode.
2. Retrieve a wider semantic pool.
3. Compute normalized composite confidence on a `0-100` scale.
4. Return the top 5 candidates.
5. Inline the body for the top candidate if confidence >= `90/100` and the indexed body exists.
6. Expose a bounded follow-up body helper for any other shortlisted candidate.

### Data Flow Notes

| Input | Transform | Output |
|------|-----------|--------|
| Query + file | Semantic retrieval and strict resolution | Candidate pool |
| Candidate pool | Metadata scoring + normalization | Ranked shortlist |
| Top candidate | Confidence gate | Inline body payload or no body payload |
| Selected non-top candidate | Bounded follow-up helper | Body payload for that candidate |

## Interface, Symbol, and Contract Notes

### Public Interfaces and Contracts

| Interface | Contract |
|----------|----------|
| `read_code_context` | Primary anchor/shortlist path; must emit the shortlist and top-body behavior. |
| `read_code_window` | Stable numeric slice path; remains bounded and predictable. |

### New or Changed Internal Helpers

| Symbol | Planned change |
|-------|----------------|
| `normalized_composite_confidence` | New normalized score value exposed to the agent as `0-100`. |
| `top_candidate_body` | New additive body payload for the highest-confidence result. |
| `candidate_body_helper` | Bounded internal selection path for shortlisted non-top candidates. |

### Ownership Boundaries

| Boundary | Owner |
|---------|-------|
| Ranking and response formatting | `scripts/read_code.py` |
| Human-readable usage rules | `AGENTS.md` |
| Demonstration and smoke test | `quickstart.md` |

## State / Lifecycle / Failure Model

### State Authority

| State | Authority |
|------|-----------|
| Candidate shortlist | `read_code.py` at runtime |
| Confidence score | Normalized composite score produced by the helper |
| Body retrieval | Existing indexed body data |

### Lifecycle / State Transitions

| State | Next state | Trigger |
|------|------------|---------|
| Retrieve | Rank | Vector pool returned |
| Rank | Shortlist | Top 5 selected |
| Shortlist | Inline body | Top candidate clears `90/100` and has body |
| Shortlist | Follow-up body request | Agent selects a non-top candidate |

### Retry / Replay / Ordering / Cancellation

| Concern | Decision |
|--------|----------|
| Retry | One bounded follow-up helper path only. |
| Replay | Deterministic ranking order should remain stable for the same inputs. |
| Cancellation | Not a special feature; the agent can stop after reading the shortlist. |

### Degraded Modes / Fallbacks / Recovery

| Situation | Behavior |
|----------|----------|
| No high-confidence body | Return the shortlist without top-body payload. |
| Missing body for top candidate | Fall back to shortlist only. |
| Ambiguous or weak match | Keep the shortlist and avoid forcing a single answer. |

## Non-Functional Design Implications

| Area | Implication |
|-----|-------------|
| Performance | Better first-pass recall, fewer retries, lower token churn. |
| Determinism | Normalized score and stable tie-breaks reduce ambiguity. |
| Maintainability | Keeps the API surface small while adding more useful output. |
| Usability | Agents can reason from the shortlist and immediately inspect the best body. |

## Migration / Rollback Notes

### Migration / Cutover Requirements

| Requirement | Note |
|------------|------|
| No service migration | None needed. |
| Docs first | Update AGENTS and quickstart so agents know the new contract. |
| Test first | Verify shortlist size, score scale, and body-first gating before relying on it. |

### Rollback Triggers

| Trigger | Action |
|-------|--------|
| Score normalization is inconsistent | Revert to single-anchor output until the score contract is fixed. |
| Body output becomes noisy | Disable body-first output and keep the shortlist only. |

### Rollback Constraints

| Constraint | Why |
|----------|-----|
| Keep current entrypoints | Avoid breaking agent scripts. |
| Keep bounded output | Never remove the shortlist cap. |

## Human-Task and Operator Boundaries

| Boundary | Rule |
|--------|------|
| Agent reading behavior | Must consult `AGENTS.md` before large reads. |
| Human control | The owner can still choose to adjust the threshold or helper shape later. |
| No hidden new command surface | Keep the solution inside the existing helper family. |

## Verification Strategy

### Unit-Testable Seams

| Seam | Test idea |
|-----|-----------|
| Confidence normalization | Given a fixed set of candidate signals, produce the expected `0-100` score. |
| Shortlist formatting | Ensure exactly 5 candidates are returned when available. |
| Top-body gating | Verify body appears only when score >= `90/100`. |
| Follow-up body helper | Verify selecting a later candidate returns that candidate's body and stays bounded. |

### Contract Verification Needs

| Contract | Check |
|---------|------|
| AGENTS docs | Read rules are present and explicit. |
| Public helper behavior | The CLI output matches shortlist/body expectations. |
| Score scale | The numeric score is normalized and documented as `0-100`. |

### Integration / Reality-Check Paths

| Path | Goal |
|-----|------|
| `read_code_context` on a known function | Confirm shortlist + top-body behavior. |
| `read_code_window` on a known line span | Confirm numeric windows still work. |
| Follow-up body selection | Confirm a non-top candidate can be revisited without a new command family. |

### Lifecycle / Retry / Duplicate Coverage Needs

| Coverage | Purpose |
|---------|---------|
| Duplicate shortlist requests | Ensure repeated reads are stable. |
| Body fallback path | Ensure no infinite retry behavior appears. |
| Non-top candidate selection | Ensure follow-up helper is bounded and deterministic. |

### Deterministic Oracles (if known)

| Oracle | Expected result |
|-------|------------------|
| Same input, same index snapshot | Same shortlist order and same top-body decision. |
| Same input, low confidence | Shortlist only, no top-body payload. |

### Regression-Sensitive Areas

| Area | Risk |
|-----|------|
| Strict literal matching | Could still force ambiguity if not kept narrow. |
| Numeric windows | Could become the wrong default if body-first output regresses. |
| Candidate selection helper | Must stay bounded and not turn into a second sprawling search API. |

## Domain Guardrails

| Guardrail | Decision |
|----------|----------|
| No new service | PASS |
| Reuse existing indexed body | PASS |
| Keep helper entrypoints stable | PASS |
| Keep bounded candidate output | PASS |

## LLD Decision Log

| Decision | Status |
|---------|--------|
| Normalized composite confidence score | Settled |
| Score scale | `0-100` |
| Body-first threshold | `90/100` |
| Top candidate body behavior | Inline with shortlist |
| Non-top candidate body behavior | Bounded follow-up helper |
| New top-level functions | Not required |

## Design Gaps and Repo Contradictions

### Missing Seams

| Gap | Resolution |
|----|------------|
| No shortlist formatter | Add one inside `scripts/read_code.py`. |
| No normalized score field | Add a composite confidence value on `0-100`. |

### Unsupported Assumptions

| Assumption | Why unsupported today |
|-----------|------------------------|
| The helper already returns multiple candidates | It currently returns one best anchor. |
| The body-first score is already normalized | Current ranking heuristics are not exposed as a 0-100 confidence contract. |

### Plan vs Repo Contradictions

| Plan item | Repo reality |
|----------|--------------|
| `90/100` threshold | Needs a normalized score field to make the threshold meaningful. |
| Follow-up body helper | Must be added as a bounded mode/flag/helper path. |

### Blocking Design Issues

None remain after the current contract decisions.

## Out-of-Scope / Preserve-As-Is Boundaries

| Boundary | Preserve |
|---------|----------|
| No new service | Keep the repo local. |
| No broad command sprawl | Avoid creating extra top-level read commands. |
| No unbounded retries | Keep one bounded follow-up path only. |

## Design-to-Tasking Contract

| Tasking area | Expected slice |
|-------------|----------------|
| Ranking and score normalization | Update `scripts/read_code.py` logic and tests. |
| Docs and usage rules | Update `AGENTS.md` and quickstart. |
| Follow-up body path | Add bounded helper behavior for selected non-top candidates. |
| Regression safety | Add deterministic tests for shortlist, confidence, and body gating. |

### Additional Tasking Notes

| Note | Meaning |
|-----|---------|
| Keep the helper family small | Avoid adding a new public command surface if a mode/flag can do the job. |
| Preserve numeric windows | They remain useful for exact line reads and should not be removed. |

## Decomposition-Ready Design Slices

### Slice SK-01: Ranking and Response Formatting

| Item | Content |
|------|---------|
| Goal | Add normalized composite confidence, shortlist formatting, and top-body inline behavior. |
| Files | `scripts/read_code.py`, tests |
| Exit criteria | Top 5 shortlist is returned; top candidate body appears when confidence >= `90/100`. |

### Slice SK-02: Bounded Follow-up Body Helper

| Item | Content |
|------|---------|
| Goal | Provide a bounded way to retrieve the body for a selected non-top candidate. |
| Files | `scripts/read_code.py`, tests |
| Exit criteria | A later selected shortlist candidate can return its body without introducing a new sprawling command family. |

### Slice SK-03: Agent Rules and Quickstart

| Item | Content |
|------|---------|
| Goal | Document the shortlist, confidence, and body-first contract in `AGENTS.md` and the feature quickstart. |
| Files | `AGENTS.md`, `specs/025-intent-anchor-routing/quickstart.md` |
| Exit criteria | An agent can read the rules first and know how to use the shortlist/body output. |

## Sketch Completion Summary

### Review Readiness

| Check | Status |
|------|--------|
| Plan contract is settled | PASS |
| No open feasibility questions remain | PASS |
| Sketch artifacts are populated | PASS |
| Design slices are task-ready | PASS |

### Suggested Next Step

Proceed to `/speckit.solutionreview`.
