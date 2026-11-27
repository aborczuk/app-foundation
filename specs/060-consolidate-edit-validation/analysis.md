# Specification Analysis Report: Consolidate Edit Validation

**Feature**: `060-consolidate-edit-validation`
**Date**: 2026-11-27
**Artifacts Analyzed**: `spec.md`, `plan.md`, `spec.json`, `tasks.md`, `estimates.md`
**External Ingress + Runtime Readiness Gate**: `N/A` — Feature `060` is strictly repo-local developer/agent workflow automation (hooks, `edit_code.py`, `read_code.py`, `bootstrap_session.py`, and `.codegraphcontext/workflow-state/`). No external ingress, webhooks, callbacks, or public network endpoints are introduced or modified.

## Specification Analysis Report

| ID | Category | Severity | Location(s) | Summary | Recommendation |
|----|----------|----------|-------------|---------|----------------|
| A-001 | Estimation / Sizing | LOW | `plan.md`, `estimates.md` | Feature total is 56 points (`L`) across 16 tasks, with every task capped at 2–5 points (zero 8/13 tasks). | No action required; execute phases sequentially following `T001`–`T002` foundation first. |

## Coverage Summary Table

| Requirement Key | Has Task? | Task IDs | Notes |
|-----------------|-----------|----------|-------|
| FR-001 | Yes | T001, T002, T003, T004 | Changed-path set tracked in `.codegraphcontext/workflow-state/` via `workflow_evidence.py` and PostToolUse hook. |
| FR-002 | Yes | T003, T004, T014 | Intermediate edits trigger zero automatic technical validators or synchronous discovery refreshes. |
| FR-003 | Yes | T003, T004, T014 | Multi-file temporarily inconsistent edits succeed without intermediate validator failures. |
| FR-004 | Yes | T005, T006 | Optional `edit_code.py validate` shares the exact pass/failure/evidence rules with `sync`. |
| FR-005 | Yes | T005, T006, T014 | Closeout (`edit_code.py sync`) enforces ruff, pyright, docstrings, targeted pytest, and required docs checks. |
| FR-006 | Yes | T005, T006 | `--skip-ruff` / `--skip-pyright` bypass flags removed from closeout `sync`. |
| FR-007 | Yes | T001, T002, T005, T006 | Reusable validation evidence keyed by content hashes, validator config, `uv.lock`, Python minor version, validator ID, and selectors. |
| FR-008 | Yes | T001, T002, T005, T006 | Any content, config, dependency, or selector change invalidates affected evidence. |
| FR-009 | Yes | T005, T006, T014 | Unchanged validated state runs each mandatory validator at most once (`SC-002`). |
| FR-010 | Yes | T001, T002, T003, T004 | Edits mark affected discovery backends/scopes `stale` without forcing synchronous refresh. |
| FR-011 | Yes | T008, T009, T014 | Authoritative reads (`context`, `find`, `analyze`) refresh stale affected scopes or fail closed with stderr (`SC-004`). |
| FR-012 | Yes | T008, T009, T014 | Repeated authoritative reads on clean `current` state cause zero duplicate refreshes (`SC-003`). |
| FR-013 | Yes | T005, T007, T014 | Closeout verifies and refreshes any remaining stale discovery scopes before handoff succeeds. |
| FR-014 | Yes | T010, T011, T014 | Direct Git commits retain active `pre-commit` lint and `post-commit` refresh safeguards. |
| FR-015 | Yes | T010, T011, T014 | Exact verified commit evidence skips duplicate pre-commit lint and post-commit refresh (`SC-006`). |
| FR-016 | Yes | T010, T011, T014 | Missing, stale, corrupt, or mismatched commit evidence forces full safeguard execution (`SC-006`). |
| FR-017 | Yes | T015 | Active workflow docs (`AGENTS.md`, `docs/governance/shell-hook-guards.md`) specify one unambiguous owner per seam (`SC-007`). |
| FR-018 | Yes | T015, T016 | Existing bounded-read rules, discovery entrypoints, governance gates, ledgers, and CI checks remain effective. |
| FR-019 | Yes | T001, T003, T005, T008, T010, T012, T014, T016 | Full unit + live-backend regression coverage across all workflows including temporarily inconsistent multi-file edits. |
| FR-020 | Yes | T012, T013, T014 | `bootstrap_session()` skips `cgc_safe_index.py` when `codegraph_health_probe` is already healthy and clean (`SC-008`). |
| FR-021 | Yes | T012, T013, T014 | Multi-scope bootstrap aggregates failures without later successes overwriting earlier failures and surfaces subprocess stderr (`SC-008`). |
| FR-022 | Yes | T001, T002, T012, T013, T014 | Discovery/indexing subprocesses run with `repo_local_tool_env()` with zero `~/.codegraphcontext` access (`SC-008`). |

## Constitution Alignment Issues

None. All core constitutional principles are satisfied:
- **Human-First Decisions**: All 4 open questions were resolved explicitly with the human owner (benchmarking dropped to feature `062`, existing `cgc_owner` content fingerprinting reused, sandbox isolation retained).
- **Security First**: Subprocess `HOME`/`XDG_*` isolation scopes strictly to discovery/indexing subprocesses; closeout skip bypasses are removed; direct Git safeguards fail closed.
- **Reuse at Every Scale**: Builds directly on `scripts/cgc_owner.py`, `scripts/hook_edit_paths.py`, `scripts/hook_refresh_indexes.py`, and existing guard wrappers.
- **Spec & Process First**: Pipeline and task ledgers are validated and synchronized with zero drift.
- **Test Driven Verification First**: Every user story precedes implementation with failing unit tests, and `T014` provides live-backend integration verification against real local git, validators, indexers, and a restricted `HOME`.

## Unmapped Tasks

None. All 16 tasks (`T001`–`T016`) map cleanly to approved plan slices `PL-01`–`PL-07` and spec requirements `FR-001`–`FR-022` / `SC-001`–`SC-008`.

## Metrics

- Total Requirements: 22 (`FR-001`–`FR-022`) + 8 Success Criteria (`SC-001`–`SC-008`)
- Total Tasks: 16 (`T001`–`T016`, 56 story points, max task size 5)
- Coverage %: 100% (22/22 FRs, 8/8 SCs)
- Ambiguity Count: 0
- Duplication Count: 0
- Critical Issues Count: 0
- High Issues Count: 0

## Next Actions

1. Record `analysis_completed` (`critical_count=0`, `high_count=0`) in `.speckit/pipeline-ledger.jsonl`.
2. Verify all implement-readiness gates (`pipeline_ledger.py validate`, `task_ledger.py validate`, `speckit_tasks_gate.py validate-format`, `speckit_gate_status.py --mode implement`, `pipeline_driver.py --dry-run`).
3. Feature `060` is ready for `/speckit.implement` starting at `T001`.
