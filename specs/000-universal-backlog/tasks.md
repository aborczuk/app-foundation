# Tasks: Universal Backlog

**Input**: Design documents from `/specs/000-universal-backlog/`
**Prerequisites**: plan.md (required), spec.md (required)
**Organization**: This file is the always-on backlog destination for ad-hoc work. New tasks added by `/speckit.addtobacklog` should be appended here.

## Phase 1: Backlog Bootstrap

**Purpose**: Keep the universal backlog available as a stable intake surface.

- [ ] T000 Maintain the universal backlog intake surface in `specs/000-universal-backlog/tasks.md`

**Checkpoint**: The universal backlog exists and is ready to accept ad-hoc tasks from any branch.

## Phase 2: Ad-Hoc Tasks

**Purpose**: Repository-wide ad-hoc tasks added through `/speckit.addtobacklog`.

<!-- Ad-hoc tasks are appended below this line by speckit.addtobacklog. -->

- [ ] T001 Harden UUID-based feature identity routing in `scripts/pipeline_driver.py` and `scripts/pipeline_driver_state.py`
- [ ] T002 [P] Add subprocess CLI coverage for `scripts/pipeline_driver.py` in `tests/integration/test_pipeline_driver_cli.py`
- [ ] T003 [P] Add integration coverage for slug resolution and wrong-phase redirection in `tests/integration/test_pipeline_driver_feature_flow.py`
- [ ] T004 Wire `speckit.specify` handoff to a real artifact path and stop falling back to `.` in `scripts/pipeline_driver.py`
- [ ] T005 Replace the remaining host `python3` examples with `uv run python` in `docs/governance/how-to-add-speckit-step.md`
- [ ] T006 Update `.github/workflows/ci.yml` to run task-ledger validation through `uv run python`
- [ ] T007 Standardize remaining repo-owned host-python invocations in `scripts/e2e_020.sh` and `.github/workflows/ci.yml` to use `uv run python`
- [ ] T008 Add `sed`-read enforcement to the `PreToolUse` hook in `.claude/settings.json` and `scripts/hook_enforce_code_reads.py` so large file reads are routed through `scripts/read-code.sh`
- [ ] T009 Add a checkpoint pause, GitHub sync handoff, and next-task HUD kickout to `.claude/commands/speckit.checkpoint.md` and `.claude/commands/speckit.implement.md`
- [ ] T010 Write a canonical task closeout command/script plus governance and command-doc updates in `.claude/commands/`, `scripts/`, and `CLAUDE.md` so task closure happens through one append-first path that records tests, offline QA, `task_closed`, `[X]`, commit SHA, and QA run id`

## Dependencies & Execution Order

- No application dependencies.
- Ad-hoc tasks are appended sequentially after T000.
