# Combined Plan - 031-speed-up-vector-context

_Feature: `031-speed-up-vector-context`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: m
- risk_level: medium
- reason: Existing specs cover the vector index and intent anchoring separately, but none define the trust-routing and latency behavior for `read_code context` itself.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "caching": "The plan needs a session and scope trust model so healthy vector state can be reused without repeated heavyweight status probes.",
      "code patterns": "The core work is a routing and control-flow refactor across preflight, query classification, and fallback sequencing.",
      "resilience": "The plan must preserve safe escalation when trust is stale, weak, or ambiguous instead of trading correctness for speed.",
      "testing": "The benchmark corpus and regression coverage must prove scoped, broad, and markdown-aware reads still return the intended seams."
    },
    "relevant": [
      "caching",
      "resilience",
      "testing",
      "code patterns"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "low",
    "human_operator_dependency": "low",
    "overall": "medium",
    "repo_uncertainty": "medium",
    "requirement_clarity": "medium",
    "runtime_side_effect_risk": "medium",
    "state_data_migration_risk": "low"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": true,
    "expanded_design_notes": true,
    "external_research": false,
    "net_new_surface": false,
    "strategy_reason": "The plan needs explicit routing and trust strategy because the feature splits broad versus scoped queries, changes when freshness is proven, and constrains fallback and markdown scope behavior."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [
      "specs/020-codebase-vector-index/spec.md",
      "specs/025-intent-anchor-routing/spec.md"
    ],
    "duplicate_reason": "Existing specs cover the vector index and intent anchoring separately, but none define the trust-routing and latency behavior for `read_code context` itself.",
    "risk_level": "medium",
    "tshirt_size": "m"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/validate_catalog.py`

### Term: faster

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/README.md`

### Term: read_code

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/read_code.py`

### Term: context

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/speckit_build_offline_qa_payload.py`

### Term: retrieval

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/025-intent-anchor-routing/huds/T002.md`

## Relevant Domains

- `caching`: Session and scope trust reuse are the primary latency lever because healthy vector state is currently reproven on repeated reads.
- `resilience`: The refactor must preserve safe escalation when trust is stale, weak, empty, or ambiguous so a faster path does not mask incorrect seams.
- `testing`: Benchmark and regression coverage are required because the feature changes a heavily used discovery path with both latency and correctness consequences.
- `code patterns`: The change is mainly a routing and control-flow simplification across `read_code.py` and `read_code_health.py`, so the design has to remove unnecessary branches rather than add more guards.

## Summary

Split `read_code context` into scoped and broad request paths, make vector freshness proof conditional instead of mandatory, and remove avoidable sequential code-plus-markdown work for scoped code queries. Keep markdown-aware broad discovery for “how does this work?” questions, but only pay broader trust and mixed-scope costs when the query shape or result quality requires them.

## Internal Research

- The current exact-symbol scoped benchmark measured about `8.65s` total in-process for `_vector_anchor_rank` against [`scripts/read_code.py`](/Users/andreborczuk/app-foundation/scripts/read_code.py).
- Preflight consumed about `5.75s`, while semantic query work consumed about `2.90s`.
- The expensive preflight seam is vector freshness, not codegraph availability: `vector_index_probe()` took about `5.63s`, while `_ensure_codegraph_session_available()` was effectively `0.003s`.
- Scoped query work currently runs both `_vector_find_candidates(..., "code")` and `_vector_find_candidates(..., "markdown")` from [`_query_semantic_anchor_candidate`](/Users/andreborczuk/app-foundation/scripts/read_code.py:707), even for a Python-file exact symbol query.
- In the measured scoped benchmark, the code query took about `1.32s`, the markdown query took about `1.30s`, and the markdown branch returned zero results.
- The current overlap optimization is structurally late: it is only consulted after the expensive global vector status probe has already run.

## Architecture Strategy

Introduce a two-path `read_code context` architecture:

- Scoped path:
  - classify symbol-shaped, path-scoped, or file-local requests before global vector freshness proof
  - use scope-local trust or healthy session trust first
  - skip markdown retrieval unless content type, file type, or query shape requires it
  - escalate to heavier freshness proof or fallback only after a miss, weak result, stale trust state, or conflicting candidates
- Broad path:
  - preserve markdown-aware semantic discovery for behavior questions
  - allow healthy session trust to satisfy normal repeated reads
  - run the slower trust or recovery path only when broad discovery is empty, weak, stale, or ambiguous

This split is necessary because the current single path proves global vector freshness and runs dual-scope retrieval before it knows whether the request is narrow or broad, which erases the value of scoped trust and scoped retrieval optimizations.

## Expanded Design Notes

Freshness should be modeled as “trusted enough for this request” rather than “the entire vector DB is globally proven fresh on every call.” For scoped reads, acceptable trust signals include unchanged session state, unchanged scope-local edit state, or an exact strong hit in the requested file. For broad reads, session-level trust can still be used for healthy repeated reads, but the slower proof path should remain available for first use, stale state, or ambiguous outcomes.

Fallback behavior needs to become conditional. The current `read_code context` flow allows recovery work after semantic resolution, but the plan should require observable triggers before paying for it: empty result sets, weak top candidates, stale trust state, or conflicts between expected scope and returned seams. This keeps safety behavior explicit and prevents recovery branches from becoming hidden default latency.

Markdown behavior remains important for broad understanding queries because specs, HUDs, and quickstarts often explain intent better than code alone. The optimization target is not “turn markdown off”; it is “do not synchronously pay for markdown on obviously code-scoped reads.” For genuinely mixed broad queries, the remaining product decision is whether code and markdown should run in parallel or whether one should be preferred and the other staged behind it.

## Design Slices

### Slice PL-01 - Scoped Trust Fast Path

- Estimate: medium
- Implementation Directive: Refactor scoped `read_code context` requests to classify early, avoid global vector freshness proof by default, skip markdown retrieval when it is irrelevant, and preserve current seam selection for the accepted scoped benchmark corpus.

### Slice PL-02 - Broad Discovery and Conditional Escalation

- Estimate: medium
- Implementation Directive: Rework broad discovery to use session-level trust for healthy reads, preserve markdown-aware behavior questions, and make heavyweight freshness and fallback work conditional on stale, empty, weak, or ambiguous outcomes.
- Ranking Note: regular broad discovery should de-prioritize test-file candidates unless the request is explicitly scoped to tests.

### Slice PL-03 - Benchmark and Regression Coverage

- Estimate: medium
- Implementation Directive: Add validation coverage and benchmark cases for scoped code queries, broad code-plus-markdown discovery, markdown-oriented reads, and stale-trust escalation so latency improvements are measured and correctness regressions are caught.
- Benchmark Corpus: keep the accepted corpus aligned with `tasks.md` across scoped exact-symbol/file-local reads, broad code-plus-markdown discovery, markdown-first reads, and stale-trust escalation cases.
- Validation Expectation: preserve the measured timings in `## Internal Research` and treat `uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file specs/031-speed-up-vector-context/tasks.md --json` as the task-file format check for this benchmark contract.

## Plan Completion Summary

Selected a medium-depth plan with architecture strategy, expanded design notes, and three implementation slices because the feature changes a frequently used internal discovery path and must rebalance speed versus trust without changing the user-facing command surface. This depth is enough because repo-local timing work already isolated the dominant latency seams, and the remaining work is routing, trust policy, and regression coverage rather than external research. The next phase should turn the three slices into tasks, starting with the scoped trust fast path because it offers the clearest latency win.
