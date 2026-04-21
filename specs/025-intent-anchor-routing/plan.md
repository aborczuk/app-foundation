# Implementation Plan — Read-Code Anchor Output Simplification

## Summary

### Feature Goal

| Item | Decision |
|------|----------|
| Problem | Agents spend too long guessing at anchors, retrying reads, and overusing numeric windows. |
| Feature outcome | `read-code` returns a bounded shortlist of semantic anchors with confidence, prefers indexed body text when it is highly confident, and widens retrieval recall to reduce misses. |
| Scope | Documentation plus read-code output contract changes only; no new service, server, or storage layer. |
| Primary consumer | Agents using `AGENTS.md`, `scripts/read-code.sh`, and `scripts/read_code.py`. |

### Architecture Direction

| Layer | Decision |
|------|----------|
| Rule source | `AGENTS.md` is the authoritative pre-read rules document for read-code behavior. |
| Retrieval | Increase semantic retrieval to `top_k = 20` so ranking has enough recall to work with. |
| Output | Return the top 5 ranked anchor candidates with confidence metadata by default. |
| Body handling | Prefer the indexed `body` payload when a symbol hit is highly confident and body text exists. |
| Expansion | Allow one bounded "ask for more" expansion from the shortlist; do not recurse. |
| Persistence | Reuse the existing vector index and body field; no new persistence or custom server. |

### Why This Direction

| Reason | Impact |
|------|--------|
| Reuse-first | Keeps the change inside the current repo and avoids another runtime surface. |
| Lower retry cost | More candidates and clearer confidence reduce blind retries. |
| Better learning payload | Returning body text when confident gives agents the actual unit they want to read. |
| Bounded behavior | A fixed shortlist and one expansion keep the workflow deterministic and token-bounded. |

## Technical Context

| Area | Current State | Plan Impact |
|------|--------------|-------------|
| Agent guidance | `AGENTS.md` already defines read limits and helper-first reading. | Keep that doc as the source of read-code rules and make the contract explicit in the feature docs. |
| Read helper | `scripts/read-code.sh` already drives bounded anchored reads. | Preserve the helper; change what it returns and how it prioritizes outputs. |
| Vector ranking | `scripts/read_code.py` already ranks semantic hits and consults the vector index. | Expand the candidate pool and return a shortlist instead of a single forced anchor. |
| Body storage | `src/mcp_codebase/index/domain.py` already carries `body` on symbol/query results. | Reuse that field for body-first output when confidence is high. |
| Index query controls | `src/mcp_codebase/indexer.py` already supports top-k style retrieval. | Widen read-code retrieval without changing index storage. |
| Review gates | Speckit plan/research gates already exist. | Use deterministic gate scripts to validate the scaffold and the plan sections. |

### Async Process Model

This feature does not introduce a new asynchronous runtime. The read-code flow stays CLI/helper-driven and agent initiated.

| Concern | Decision |
|------|----------|
| Background work | None introduced. |
| User-visible latency | Reduced by returning a stronger first pass instead of forcing repeated retries. |
| Retry model | Bounded shortlist expansion only. |

### State Ownership / Reconciliation Model

| State | Owner | Notes |
|------|-------|------|
| Read rules | `AGENTS.md` | Human-facing contract for how agents should use read-code. |
| Candidate ranking | `scripts/read_code.py` | Owns semantic ranking and shortlist ordering. |
| Indexed body content | Existing codebase index | Source of truth for symbol body payloads. |
| Follow-up choice | Agent | Chooses a returned candidate or requests one bounded expansion. |

### Local DB Transaction Model

| Concern | Decision |
|------|----------|
| Writes | None required for this feature. |
| Reads | Existing vector index and indexed bodies only. |
| Transaction scope | Read-only access; no new mutation path. |

### Venue-Constrained Discovery Model

| Discovery step | When it happens | Why |
|------|----------------|-----|
| Helper read | First | Anchors the exact seam before broad exploration. |
| Codegraph discovery | After the seam is anchored | Used only to reason about related callers/callees/importers if needed. |
| Extra candidate expansion | Only when requested once | Keeps the feature bounded and predictable. |

### Implementation Skills

| Skill | Used for |
|------|----------|
| Python | Update `scripts/read_code.py` and any related tests. |
| Shell | Keep `scripts/read-code.sh` aligned with the contract. |
| Markdown | Document the user-facing rules and quickstart. |
| Speckit workflow | Keep artifacts and gates consistent with the repo process. |

## Repeated Architectural Unit Recognition

### Does a repeated architectural unit exist?

Yes. The same pattern repeats across the current helper flow:

| Repeated unit | Description |
|------|-------------|
| Anchor search | Find the best location for a user query. |
| Bounded read | Return a small, readable amount of context. |
| Fallback | If the first attempt is weak, expose more candidates instead of guessing. |

### Chosen Abstraction

| Abstraction | Responsibility |
|------|----------------|
| `ReadRuleSet` | Documents the agent-facing rules from `AGENTS.md`. |
| `AnchorCandidate` | Holds a ranked candidate, confidence, and symbol metadata. |
| `AnchorShortlist` | Returns the top 5 candidates and supports one bounded expansion. |
| `SymbolBodyPayload` | Carries full indexed body text when the symbol hit is highly confident. |

### Why It Matters

| Benefit | Result |
|------|--------|
| Stable output contract | Agents can continue reasoning without guessing what the helper meant. |
| Less duplicated logic | The same shortlist/body contract can be used across context and window paths. |
| Better ergonomics | The most useful unit of code is returned first when the data is already available. |

### Defining Properties

| Property | Requirement |
|------|-------------|
| Deterministic order | Sort candidates predictably by confidence and tie-break rules. |
| Bounded width | Return 5 candidates by default, not an unbounded list. |
| Bounded retry | Allow only one ask-for-more step. |
| Body-first preference | Use indexed body text when confidence is high and the body exists. |

## Reuse-First Architecture Decision

### Existing Sources Considered

| Source | Reuse value |
|------|-------------|
| `AGENTS.md` | Existing rule source for helper-first reads and bounded windows. |
| `scripts/read-code.sh` | Existing entrypoint for anchored code reads. |
| `scripts/read_code.py` | Existing ranking and bounded-read implementation. |
| `src/mcp_codebase/index/domain.py` | Existing `body` field and query payload shape. |
| `src/mcp_codebase/indexer.py` | Existing top-k retrieval control. |

### Preferred Reuse Strategy

| Strategy | Decision |
|------|----------|
| Keep shell wrapper | Yes; preserve `read-code.sh` as the agent entrypoint. |
| Reuse indexed body | Yes; return `body` when it is the best answer unit. |
| Expand retrieval pool | Yes; raise read-code retrieval to a bounded `top_k = 20`. |
| Add new server/package | No. |

### Net-New Architecture Justification

| New thing | Why it is needed |
|------|-------------------|
| Shortlist contract | The current helper returns one forced anchor; the feature needs a ranked candidate set. |
| Body-first preference | The current output contract does not clearly promote the indexed full body when it is better than a window. |
| Agent documentation | The shortlist and one-expansion rule must be documented so agents know how to use the output. |

## Pipeline Architecture Model

### Recurring Unit Model

| Step | Output |
|------|--------|
| Consult `AGENTS.md` | Read rules and limits before large reads. |
| Semantic retrieval | Pull a bounded pool of candidates (`top_k = 20`). |
| Deterministic ranking | Score and order candidates with confidence metadata. |
| Shortlist return | Expose the top 5 candidates to the agent. |
| One bounded expansion | Allow one extra candidate batch if the shortlist is not enough. |
| Body-first return | If confidence is high and `body` exists, return the body text instead of a numeric window. |

### Unit Properties

| Property | Requirement |
|------|-------------|
| Determinism | Stable sort order and predictable tie-breaks. |
| Boundedness | Hard limits on candidate count and expansions. |
| Readability | Candidate output must be easy for an agent to act on. |
| Compatibility | Preserve the current helper entrypoint and existing vector index. |

### Downstream Reliance

| Consumer | What it depends on |
|------|-------------------|
| Agents | The shortlist, confidence, and body-first behavior. |
| Later codegraph reasoning | A better first anchor set to reduce blind traversal. |
| Quickstart/docs | The documented shortlist and expansion rules. |

## Artifact / Event Contract Architecture

### Manifest Impact

| Item | Decision |
|------|----------|
| `speckit.plan` manifest | No manifest change required for this narrowed feature. |
| Pipeline events | Record `plan_started` for traceability. |
| Artifact set | `plan.md`, `data-model.md`, and `quickstart.md` remain the required plan outputs. |

## Architecture Flow

### Major Components

| Component | Responsibility |
|------|----------------|
| `AGENTS.md` | Source of agent-facing read rules and limits. |
| `scripts/read_code.py` | Retrieves and ranks semantic candidates. |
| Existing vector index | Supplies semantic matches and symbol bodies. |
| Plan docs | Explain the shortlist/body contract and usage rules. |

### Trust Boundaries

| Boundary | Trust decision |
|------|----------------|
| Agent input | The agent chooses a query intent and can request one bounded expansion. |
| Read helper output | The helper owns ranking and shortlist formatting. |
| Indexed body payload | Trusted as the stored source of the symbol body. |

### Primary Automated Action

| Action | Result |
|------|--------|
| Produce a ranked shortlist with confidence | Agents get enough information to continue without re-running blind searches. |

### Architecture Flow Notes

| Note | Detail |
|------|--------|
| No infinite loops | Expansion is capped at one step. |
| No new service boundary | Everything stays within the existing repo and helper flow. |
| No unbounded windows | Numeric windows remain a fallback/context tool, not the primary learning path. |

## External Ingress + Runtime Readiness Gate

| Ingress | Status | Notes |
|------|--------|------|
| CLI helper invocation | ✅ Pass | Already exists via `scripts/read-code.sh`. |
| External API | ✅ Pass | None introduced. |
| Runtime readiness | ⚠️ Conditional | Becomes ready when docs, shortlist output, and body-first behavior are aligned and validated. |

### Readiness Blocking Summary

| Blocker | Status | Notes |
|------|--------|------|
| New runtime dependency | ✅ Pass | None. |
| New storage layer | ✅ Pass | None. |
| Documentation gap | ⚠️ Conditional | Must be addressed in the feature docs and quickstart. |

## State / Storage / Reliability Model

### State Authority

| State type | Authority |
|------|----------|
| Candidate ranking state | `scripts/read_code.py` at runtime. |
| Rule state | `AGENTS.md` and feature docs. |
| Body payload | Existing indexed `body` field. |

### Persistence Model

| Data | Persisted where? |
|------|------------------|
| Candidate lists | Not persisted; computed per read. |
| Confidence metadata | Not persisted; returned as part of the read response. |
| Rule documentation | Persisted in repo markdown. |

### Retry / Timeout / Failure Posture

| Situation | Behavior |
|------|----------|
| Weak first candidate | Return the shortlist with confidence values instead of forcing a single answer. |
| Missing body | Fall back to the current bounded read behavior. |
| Ambiguous result | Allow one bounded "ask for more" step, then stop. |
| Repeated miss | Stop rather than loop. |

### Recovery / Degraded Mode Expectations

| Degraded mode | Expected result |
|------|------------------|
| Body unavailable | Return candidate metadata and let the agent choose the next step. |
| Query remains ambiguous | Preserve the ranked shortlist and avoid overcommitting to one anchor. |

## Contracts and Planning Artifacts

### Data Model

| Artifact | Planned contract |
|------|------------------|
| `data-model.md` | Define the shortlist, candidate, and body payload entities and their relationships. |

### Contracts

| Contract | Planned behavior |
|------|------------------|
| Read rules | `AGENTS.md` tells agents how to read before attempting large reads. |
| Shortlist contract | Return 5 candidates by default and allow one bounded expansion. |
| Body contract | Prefer indexed body text when confidence is high and body exists. |
| Retrieval contract | Expand semantic retrieval to a bounded `top_k = 20`. |

### Quickstart

| Artifact | Planned contract |
|------|------------------|
| `quickstart.md` | Explain how to validate the feature locally and how to interpret the shortlist/body output. |

## Constitution Check

| Principle | Plan alignment |
|------|----------------|
| Human-first decisions | The user controls scope and can still change thresholds or wording. |
| Reuse at every scale | Existing helper, index, and body field are reused. |
| Spec and process first | The plan stays inside Speckit artifacts and gates. |
| Test-driven verification first | The implementation should be validated against the plan gates and helper smoke checks. |

## Behavior Map Sync Gate

| Check | Status |
|------|--------|
| Separate behavior map exists | Not currently required for this narrowed scope. |
| Contract sync needed | Yes, if a downstream behavior map is generated later, it must preserve the shortlist/body-first contract. |
| Blocking issue | None for plan generation. |

## Open Feasibility Questions

| Question | Why it matters |
|------|----------------|
| None | None |

## Handoff Contract to Sketch

### Settled by Plan

| Decision | Status |
|------|--------|
| `AGENTS.md` is the source of read-code rules | Settled |
| Vector retrieval widens to `top_k = 20` | Settled |
| Return a top-5 candidate shortlist | Settled |
| Allow one bounded "ask for more" expansion | Settled |
| Expose a normalized composite confidence score on a `0-100` scale | Settled |
| Prefer indexed body text when normalized composite confidence is at least `90/100` | Settled |
| Return the top candidate body inline with the shortlist | Settled |
| Provide a follow-up body helper for any other shortlist candidate | Settled |

### Sketch Must Preserve

| Constraint | Why |
|------|-----|
| Bounded shortlist | Keeps the output actionable and deterministic. |
| One expansion cap | Prevents loops and runaway token use. |
| Body-first preference | Matches the user-approved scope. |
| Confidence scale is normalized and explicit | Makes the `90/100` cutoff meaningful and stable. |
| Top-candidate body is additive, not a replacement | Preserves the shortlist while giving the agent the best body immediately. |
| Follow-up body access stays bounded | Lets the agent inspect other candidates later without adding a new sprawling API surface. |
| No new server/package | Preserves reuse-first architecture. |

### Sketch May Refine

| Area | Allowed refinement |
|------|--------------------|
| Tie-break details | Tighten ordering rules as long as they stay deterministic. |

### Sketch Must Not Re-Decide

| Decision | Protected by this plan |
|------|------------------------|
| Rule source | `AGENTS.md` |
| Shortlist width | 5 candidates |
| Expansion cap | One bounded follow-up step |
| Retrieval width | `top_k = 20` |
| Confidence scale | Normalized composite score on `0-100` |
| Top-item body behavior | Returned inline with the shortlist |
| Non-top body behavior | Retrieved later through a bounded helper |

## Phase 1 Planning Artifacts Summary

| Artifact | Status | Notes |
|------|--------|-------|
| `plan.md` | Complete | Architecture, contracts, and handoff rules are written. |
| `data-model.md` | Complete | Entities and state model are defined. |
| `quickstart.md` | Complete | Local validation and usage steps are documented. |

## Plan Completion Summary

### Ready for Plan Review?

| Check | Status |
|------|--------|
| Plan sections present | Yes |
| Research prerequisite satisfied | Yes |
| Required artifacts present | Yes |
| Open feasibility questions remain | Yes, but they are narrow and bounded |

### Suggested Next Step

Proceed to `/speckit.planreview` so the remaining threshold questions can be confirmed without broadening the scope.
