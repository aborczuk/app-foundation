# Combined Plan - 059-workflow-state-consistency

_Feature: `059`_
_Source Spec: `spec.md`_
_Artifact: `plan.md`_

## Triage

- duplicate: false
- t_shirt_size: m
- risk_level: medium
- reason: No existing feature unifies vector edit fingerprinting across commit boundaries, non-destructive Plan/Solution scaffolding, NNN/NNN-slug ledger normalization, and estimate-to-ledger contract alignment; persistent warmed-reranker ownership is explicitly delegated to feature 061.

## Strategy Contract

```json
{
  "domains": {
    "reasoning": {
      "storage": "Vector edit fingerprints, populated spec/plan/task artifacts, and append-only pipeline/task ledgers are stateful persistence surfaces that must remain deterministic and non-destructive.",
      "ops governance": "Pipeline driver routing, command manifests, custom templates, and ledger transition contracts govern every Speckit phase transition.",
      "testing": "Live-backend verification for vector index refresh and read_code.py paths is required alongside mocked contract tests per constitution Principle IV."
    },
    "relevant": [
      "storage",
      "ops governance",
      "testing"
    ]
  },
  "risk": {
    "external_dependency_uncertainty": "low",
    "human_operator_dependency": "low",
    "overall": "medium",
    "repo_uncertainty": "low",
    "requirement_clarity": "low",
    "runtime_side_effect_risk": "medium",
    "state_data_migration_risk": "medium"
  },
  "strategy": {
    "architecture_diagram": false,
    "architecture_strategy": true,
    "expanded_design_notes": false,
    "external_research": false,
    "net_new_surface": false,
    "strategy_reason": "All four root causes are verified in repository code (`read_code_health.py`, `speckit_plan_step.py`, `speckit_solution_step.py`, `pipeline_ledger.py`, `pipeline_driver.py`, and `command-manifest.yaml`). No external research or net-new operator surface is needed, but explicit architecture strategy is required to preserve append-only audit integrity and non-destructive artifact invariants."
  },
  "triage": {
    "duplicate": false,
    "duplicate_matches": [],
    "duplicate_reason": "Confirmed unique scope; persistent warmed-reranker ownership is explicitly separated into feature 061.",
    "risk_level": "medium",
    "tshirt_size": "m"
  }
}
```

## Internal Discovery

### Term: vector_edit_signature

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/read_code_health.py`
  - `/Users/andreborczuk/app-foundation/src/mcp_codebase/health.py`
  - `/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py`

### Term: apply_strategy_and_prepare_tasking

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/speckit_plan_step.py`
  - `/Users/andreborczuk/app-foundation/scripts/speckit_solution_step.py`
  - `/Users/andreborczuk/app-foundation/scripts/speckit_tasking_step.py`

### Term: feature_id_normalization

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/scripts/pipeline_ledger.py`
  - `/Users/andreborczuk/app-foundation/scripts/pipeline_driver.py`
  - `/Users/andreborczuk/app-foundation/scripts/pipeline_driver_state.py`

### Term: estimate_contract

- matches: true
- exit_code: 0
- files:
  - `/Users/andreborczuk/app-foundation/.claude/commands/speckit.estimate.md`
  - `/Users/andreborczuk/app-foundation/command-manifest.yaml`
  - `/Users/andreborczuk/app-foundation/.specify/command-manifest.yaml`

## Relevant Domains

### storage
- Why it matters: Vector edit signatures, populated markdown artifacts, and append-only JSONL ledgers must remain deterministic, non-destructive, and backward-compatible across commits and reruns.
- Required checklist prompts:
  - [x] Append-only ledger integrity is preserved without rewriting historical `.speckit/pipeline-ledger.jsonl` records.
  - [x] Populated `plan.md` and `tasks.md` files are preserved byte-for-byte unless explicitly missing or empty.
  - [x] Fingerprint computation is deterministic across working-tree edits, refreshes, commits, and reads.

### ops governance
- Why it matters: `command-manifest.yaml`, `.specify/command-manifest.yaml`, `.claude/commands/speckit.estimate.md`, and `scripts/pipeline_ledger.py` must agree on feature IDs and transition contracts.
- Required checklist prompts:
  - [x] Custom templates and workflow steps are preserved without regression.
  - [x] Feature `061` boundary (persistent warmed-reranker ownership) is documented and respected.
  - [x] Migration and backward-compatibility behavior is documented for operators.

### testing
- Why it matters: Constitution Principle IV requires live-backend verification for infrastructure-critical index and `read_code.py` paths in addition to mocked unit/contract tests.
- Required checklist prompts:
  - [x] Mocked contract tests cover edge cases and malformed inputs.
  - [x] Live-backend verification tests exercise real vector index refresh, fingerprint stability across commit boundaries, and real `read_code.py` queries.

## Summary

Resolve four recurring workflow state inconsistencies in five cohesive implementation slices:
1. Make vector edit fingerprinting deterministic across edits, refreshes, git commits, and reads so committing already-refreshed content never triggers false staleness.
2. Make `speckit_plan_step.py:apply_strategy` and `speckit_solution_step.py:prepare_tasking` non-destructive so populated `plan.md` and `tasks.md` artifacts are preserved while custom templates continue scaffolding missing artifacts.
3. Normalize `NNN` and `NNN-slug` feature IDs consistently to canonical `NNN` across `pipeline_ledger.py`, `pipeline_driver.py`, and `pipeline_driver_state.py` while preserving append-only audit integrity.
4. Align `.claude/commands/speckit.estimate.md`, `command-manifest.yaml`, `.specify/command-manifest.yaml`, `scripts/pipeline_ledger.py`, and `scripts/pipeline_driver_state.py` around one unambiguous estimate/tasking transition contract.
5. Add live-backend verification for vector index refresh and `read_code.py` paths and document migration/compatibility behavior and the feature `061` boundary.

## Internal Research

- **Vector edit fingerprinting (`scripts/read_code_health.py:787-852`, `src/mcp_codebase/health.py:287-302`)**: `codegraph_current_edit_signature()` currently relies on `git status --porcelain --untracked-files=normal`. After an edit + refresh persists ` M <file>` into `.codegraphcontext/vector-last-edit-signature`, committing that same file causes `git status --porcelain` to return `""`, immediately mismatching the persisted signature and flagging unchanged committed content as stale. Replacing the comparison with a deterministic content/tree digest (covering tracked content hashes + indexed working-tree deltas, ignoring `.codegraphcontext/`, `.speckit/`, `.uv-cache/`, `logs/`, `shadow-runs/`) makes edit → refresh → commit → verify invariant to git commit transitions while still catching real edits.
- **Plan apply-strategy overwrite (`scripts/speckit_plan_step.py:770-814, 918-958`)**: `_write_selected_scaffold()` unconditionally calls `plan_file.write_text(_render_template_subset(...))`, replacing every non-base section (`Summary`, `Internal Research`, `Architecture Strategy`, `Design Slices`, `Plan Completion Summary`) with blank template stubs even when `plan.md` already contains authored content. Preserving already-populated section bodies (and refusing to overwrite populated sections with blank template stubs) eliminates destructive plan resets while keeping custom template scaffolding for missing sections.
- **Solution task creation overwrite (`scripts/speckit_solution_step.py:170-213`, `scripts/speckit_tasking_step.py`)**: `prepare_tasking()` unconditionally executes `tasks_path.write_text(_render_tasks_scaffold(feature_dir, plan_path))`, destroying existing populated `tasks.md` files on rerun. Guarding `prepare_tasking()` to only scaffold when `tasks.md` is missing or empty/blank preserves populated task graphs while returning metadata indicating whether scaffolding occurred.
- **Feature ID normalization (`scripts/pipeline_ledger.py:230`, `scripts/pipeline_driver.py:1347-1385`, `scripts/pipeline_driver_state.py:384-400`)**: `pipeline_ledger.py` enforces strict `NNN` format and rejects `NNN-slug` (e.g., `059-workflow-state-consistency`), while `pipeline_driver.py:append_requested_pipeline_event` passes raw `resolved_feature_id` (`059-workflow-state-consistency`) on new features with zero prior ledger events, causing `pipeline_event_append_failed`. Introducing one shared canonical normalizer (`normalize_feature_id`) used by both `pipeline_ledger.py` (`append`, `assert-phase-complete`, `validate`, state lookup) and `pipeline_driver.py` / `pipeline_driver_state.py` ensures `059` and `059-workflow-state-consistency` resolve identically to `059` while rejecting malformed IDs.
- **Estimate vs ledger transition contract (`command-manifest.yaml:207-232`, `.specify/command-manifest.yaml`, `.claude/commands/speckit.estimate.md`, `scripts/pipeline_ledger.py:178-195`, `scripts/pipeline_driver_state.py`)**: `.claude/commands/speckit.estimate.md` treats `speckit_tasking_step.py finalize` (`tasking_completed`) as the completion event, while `command-manifest.yaml` declares both `estimation_completed` (`compatibility_only: true`) and `tasking_completed` (`task_count`, `story_count`). Aligning the manifest, command doc, ledger transitions, and driver state mapping removes ambiguity while keeping historical `estimation_completed` ledger entries valid.

## Architecture Strategy

1. **Single Canonical Fingerprint Seam**: Compute one deterministic content fingerprint helper shared by refresh persistence (`scripts/hook_refresh_indexes.py`, `scripts/read_code_health.py`) and read-time freshness verification (`scripts/read_code_health.py`, `src/mcp_codebase/health.py`) so read, refresh, commit, and verify compute identical digests over the same indexed scope.
2. **Non-Destructive Artifact Preservation**: Treat populated markdown sections/files as authoritative state. `apply_strategy()` merges/preserves existing populated sections instead of regenerating blank stubs; `prepare_tasking()` only writes from `.specify/templates/tasks-template.md` when `tasks.md` does not exist or is blank/unpopulated.
3. **Canonical Ledger Boundary Normalization**: Normalize `NNN` and `NNN-slug` at a single helper in `scripts/pipeline_ledger.py` (reused by `scripts/pipeline_driver.py` and `scripts/pipeline_driver_state.py`). Never mutate or rewrite existing `.speckit/pipeline-ledger.jsonl` records; preserve full append-only audit integrity.
4. **Explicit Scope Boundary with Feature 061**: Feature `059` owns fingerprint determinism, non-destructive scaffolding, feature-ID normalization, estimate transition alignment, live-backend verification, and migration docs; persistent warmed-reranker process ownership remains strictly in feature `061-persistent-repo-research-backends`.

## Design Slices

### Slice PL-01 - Deterministic vector edit fingerprinting across reads, refreshes, commits, and verification
- Estimate: medium
- Implementation Directive: Replace porcelain-only signature drift in `scripts/read_code_health.py` and `src/mcp_codebase/health.py` (and refresh persistence in `scripts/hook_refresh_indexes.py`) with a deterministic content-based fingerprint over indexed repo files so edit → refresh → read → commit → verify produces identical fingerprints without false-positive staleness while still detecting genuine post-refresh edits; add unit coverage in `tests/unit/test_read_code_health.py`.

### Slice PL-02 - Non-destructive Plan apply-strategy and Solution task creation
- Estimate: medium
- Implementation Directive: Update `scripts/speckit_plan_step.py` (`apply_strategy` / `_write_selected_scaffold`) to preserve existing populated section content rather than overwriting with blank template stubs, and update `scripts/speckit_solution_step.py` (`prepare_tasking`, exposed via `scripts/speckit_tasking_step.py`) to preserve existing populated `tasks.md` files while still scaffolding missing/empty artifacts from custom templates; add unit tests in `tests/unit/test_plan_step.py` and `tests/unit/test_speckit_solution_step.py`.

### Slice PL-03 - Consistent NNN and NNN-slug feature ID normalization in pipeline ledger and driver
- Estimate: medium
- Implementation Directive: Add a shared `normalize_feature_id()` helper in `scripts/pipeline_ledger.py` that accepts `NNN` or `NNN-slug` and normalizes to canonical `NNN` while rejecting malformed IDs; wire it into `pipeline_ledger.py` (`append`, `assert-phase-complete`, `validate`), `scripts/pipeline_driver.py` (`append_requested_pipeline_event`, `append_pipeline_success_event`), and `scripts/pipeline_driver_state.py` (`resolve_phase_state`) without rewriting historical append-only ledger entries; add unit tests in `tests/unit/test_pipeline_ledger_sequence.py` and `tests/unit/test_pipeline_driver.py`.

### Slice PL-04 - Align estimate command, manifests, and ledger transition contract
- Estimate: low
- Implementation Directive: Reconcile `.claude/commands/speckit.estimate.md`, `command-manifest.yaml`, `.specify/command-manifest.yaml`, `scripts/pipeline_ledger.py`, and `scripts/pipeline_driver_state.py` so `estimation_completed` (compatibility) and `tasking_completed` (canonical, with `task_count` and `story_count`) share identical prerequisites, required fields, and follow-on transitions; verify via `pipeline_ledger.py validate-manifest` and contract tests in `tests/unit/test_pipeline_ledger_sequence.py`.

### Slice PL-05 - Live-backend verification and migration/compatibility documentation
- Estimate: medium
- Implementation Directive: Add live-backend verification tests in `tests/integration/test_live_vector_fingerprint_and_read_code.py` exercising real local vector index refresh, fingerprint stability across edit/refresh/commit/verify, and real `read_code.py` execution (separate from mocked unit/contract tests); update `docs/governance/pipeline-driver-readme.md` and `docs/governance/speckit-end-to-end.md` with migration/backward-compatibility guidance and the explicit scope boundary with feature `061`.

## Plan Completion Summary

The five-slice plan covers every functional requirement (`FR-001` through `FR-013`) and success criterion (`SC-001` through `SC-005`) using existing repository seams, preserves append-only ledger integrity and custom templates, keeps persistent warmed-reranker ownership scoped to feature `061`, and is ready for tasking, estimation, and cross-artifact analysis.
