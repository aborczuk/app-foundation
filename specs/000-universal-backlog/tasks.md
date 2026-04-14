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

## Dependencies & Execution Order

- No application dependencies.
- Ad-hoc tasks are appended sequentially after T000.
