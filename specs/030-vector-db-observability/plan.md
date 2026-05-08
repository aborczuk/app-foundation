# Combined Plan - 030-vector-db-observability

_Feature: `030-vector-db-observability`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

[This template documents every section the combined `speckit.plan` step may keep. `scripts/speckit_plan_step.py` prunes unused sections after triage so the emitted `plan.md` contains only the sections required by strategy.]

## Triage

- duplicate: false
- t_shirt_size: m
- risk_level: high
- reason: No existing feature provides vector DB observability through the same shared cgc dashboard and alert pathway.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "code patterns": "It must extend the existing cgc and shared health seams rather than creating a parallel ad hoc contract.",
      "observability": "The feature is primarily about exposing actionable shared health, dashboard, and alert signals for the vector index.",
      "ops governance": "Warnings, blocking conditions, and next actions become operational control surfaces for maintainers and agents.",
      "testing": "The feature requires deterministic health-path verification plus live-ish lifecycle checks for write, refresh, warning, and failure states."
    },
    "relevant": [
      "observability",
      "code patterns",
      "testing",
      "ops governance"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "low",
    "human_operator_dependency": "medium",
    "overall": "high",
    "repo_uncertainty": "medium",
    "requirement_clarity": "low",
    "runtime_side_effect_risk": "medium",
    "state_data_migration_risk": "low"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": true,
    "expanded_design_notes": true,
    "external_research": false,
    "strategy_reason": "The repo already has the core seams locally, so external research is unnecessary. The plan does need explicit shared-health architecture and detailed design notes because the change must join cgc doctor/health, vector-index lifecycle status, and shared dashboard/alert pathways without creating a separate contract."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [],
    "duplicate_reason": "No existing feature provides vector DB observability through the same shared cgc dashboard and alert pathway.",
    "risk_level": "high",
    "tshirt_size": "m"
  }
}
```

## Internal Discovery

### Term: specification

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/quickstart.md`

### Term: vector

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/030-vector-db-observability/spec.md`

### Term: observability

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/030-vector-db-observability/spec.md`

### Term: one-line

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/025-intent-anchor-routing/spec.md`

### Term: purpose

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/specs/025-intent-anchor-routing/spec.md`

## Relevant Domains

- `observability`: the core deliverable is a first-class shared health, dashboard, and alert surface for vector-index state.
- `code patterns`: the solution must extend the current `cgc` doctor and shared health pattern instead of introducing a vector-only inspection contract.
- `testing`: the feature needs deterministic coverage for healthy, stale, warning, and blocking states, plus lifecycle verification around promotion and preserved last-good state.
- `ops governance`: warning thresholds, blocking conditions, and next-action guidance become operational controls that agents and maintainers will act on.

## Summary

Extend the existing codegraph health pathway so the top-level health experience reports both graph health and vector-index health from one shared contract. Keep the current graph doctor semantics intact, add a vector-health payload that exposes active snapshot, previous snapshot, staging count and bytes, warning state, and preserved-failure state, then route vector warnings and failures through the same dashboard and alert pathway used for adjacent repo health signals. Back the shared surface with the already-existing vector lifecycle seam in `chroma.py`, where promotion, pruning, threshold warnings, and fail-fast low-disk behavior already exist but are not surfaced as first-class observability outputs.

## Internal Research

- `src/mcp_codebase/doctor.py` currently exposes a compact graph-only doctor CLI built on `classify_graph_health(...)`, with human output limited to `status`, `access_mode`, `detail`, `recovery_hint`, and `next`.
- `src/mcp_codebase/health.py` defines the canonical shared graph-health vocabulary today: `healthy`, `stale`, `locked`, and `unavailable`. That is the existing shared health seam this feature must extend rather than bypass.
- `src/mcp_codebase/index/store/chroma.py` now owns the vector lifecycle truth:
  - `_activate_snapshot(...)` promotes `staging -> active` and rotates `active -> previous`.
  - `_apply_staging_guardrails(...)` prunes orphaned staging directories, logs threshold warnings for excessive staging count and bytes, and fails hard on low free disk.
  - the store already has concrete thresholds: retain max `16` orphaned staging dirs, warn at `32` dirs, warn at `8 GiB`, and fail below `5 GiB` free space.
- Repo behavior observed during this planning run still surfaced stale-vector warnings on semantic reads. That confirms the feature is not redundant: the lifecycle seam exists, but shared visibility remains too weak and too indirect.

## Architecture Strategy

Do not build a separate vector doctor. Extend the current shared health architecture in layers:

1. Preserve `classify_graph_health(...)` and its current graph contract as one slice of a broader shared health payload.
2. Add a vector-index health classification seam that derives status from manifest validity, active and previous snapshot references, staging population, warning-threshold crossings, low-disk state, and last-known failure or preserved-state metadata.
3. Introduce a shared top-level health result that carries both graph health and vector DB health while keeping them clearly distinguished for operators.
4. Route warning and failure outputs from the vector lifecycle seam into the same dashboard and alert pathway used for adjacent repo health signals so the warnings are visible without log forensics.

This architecture is necessary because the repo already has two partial truths: `cgc` health knows how to report graph readiness, and `chroma.py` knows vector lifecycle and capacity state. The feature’s job is to join those truths into one supported operational surface.

## Expanded Design Notes

- The shared health result should distinguish at least:
  - graph status using the existing graph-readiness vocabulary
  - vector status using health states such as healthy, stale, capacity-constrained, structurally invalid, or blocked by lifecycle failure
- The vector side should expose concrete fields, not prose-only summaries:
  - active snapshot reference
  - previous snapshot reference
  - staging root
  - staging count
  - staging bytes
  - threshold values
  - preserved last-good state
  - most recent failure condition
  - next corrective action
- The dashboard and alert integration should treat vector warnings as first-class health events. Warnings must not stay hidden in backend logs alone.
- Keep “never built” and “manifest points at missing path” separate from generic stale state, because those require different corrective actions.
- The shared surface should be queryable both programmatically and as human-readable output so it works for CLI maintainers, tasking and implement agents, and any existing runtime dashboard pathway.
- Testing must cover both contract and behavior:
  - contract tests for shared health payload shape and warning classification
  - live-ish lifecycle tests that perform write and refresh flows and assert the surfaced state matches actual active, previous, staging, and preserved-state behavior

## Design Slices

### Slice PL-01 - Shared Health Contract Extension

- Estimate: medium
- Why this slice exists: The repo already has a graph-health contract, but vector observability must appear in the same top-level pathway without breaking existing `cgc` behavior.
- File/Symbol Seams: `src/mcp_codebase/health.py`, `src/mcp_codebase/doctor.py`, shared health and reporting adapters that currently consume graph health
- Implementation Directive: Introduce a shared health result that preserves current graph-health semantics while adding a clearly separated vector-health payload with machine-readable status, reason, and recovery data.

### Slice PL-02 - Vector Lifecycle Status Derivation

- Estimate: medium
- Why this slice exists: The truth about vector state already lives in the vector store lifecycle, but it is not surfaced as an operator-facing health model.
- File/Symbol Seams: `src/mcp_codebase/index/store/chroma.py`, vector-index manifest and status metadata readers
- Implementation Directive: Derive vector health from active and previous snapshot references, staging population, threshold crossings, invalid manifests, and preserved failure state without reintroducing direct filesystem forensics as the supported operator workflow.

### Slice PL-03 - Shared Dashboard And Alert Routing

- Estimate: high
- Why this slice exists: The feature is incomplete if warnings only exist as backend logs; shared dashboards and alerts are the actual operator surface requested by the spec.
- File/Symbol Seams: repo health dashboard and status pathway, repo alert emission pathway, any runtime surface that currently renders or dispatches adjacent health signals
- Implementation Directive: Route vector warning and blocking states through the same dashboard and alert pathways used for related repo health signals, carrying current measurements, thresholds, and next-action guidance.

### Slice PL-04 - Verification Of Healthy, Warning, And Failure States

- Estimate: medium
- Why this slice exists: This feature changes operator trust. It needs proof that the surfaced health state matches actual lifecycle behavior, including preserved last-good state after failure.
- File/Symbol Seams: unit tests for shared health classification, integration and runtime tests for vector write, refresh, warning, and failure scenarios
- Implementation Directive: Add deterministic coverage for healthy, stale, capacity, and failure classifications plus live-backed lifecycle verification that confirms active, previous, staging, and preserved-state reporting remain truthful.

## Plan Completion Summary

This plan used medium scope with high rigor. That was enough because the repo-local seams are already identifiable: graph health lives in `doctor.py` and `health.py`, while vector lifecycle truth lives in `chroma.py`. The next phase should convert these slices into task-level solution artifacts that keep one rule explicit: extend the shared `cgc` health, dashboard, and alert experience rather than creating a vector-only side path.
