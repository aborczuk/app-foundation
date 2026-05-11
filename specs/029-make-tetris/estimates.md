# Effort Estimate: make tetris

**Date**: 2026-05-08 | **Total Points**: 31 | **T-shirt Size**: medium
**Estimated by**: AI (speckit.estimate) — calibrate against actuals after implementation

---

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 2 | Establish the Tetris package and FastAPI mount seam in `src/clickup_control_plane/app.py:create_app` plus `src/clickup_control_plane/tetris/routes.py`. | Small but cross-cutting setup work touching one existing seam and a small package skeleton. |
| T002 | 3 | Create typed gameplay state and piece definitions in `src/clickup_control_plane/tetris/models.py` and `src/clickup_control_plane/tetris/pieces.py`. | Moderate modeling work with several new symbols but no runtime integration yet. |
| T003 | 5 | Implement deterministic spawn/move/rotate/gravity/session orchestration in `src/clickup_control_plane/tetris/engine.py` and `src/clickup_control_plane/tetris/service.py`. | Core rule engine is the highest-risk implementation seam and needs careful state transitions. |
| T004 | 3 | Add the game page and session command endpoints in `src/clickup_control_plane/tetris/routes.py` and `src/clickup_control_plane/app.py:create_app`. | Route wiring is moderate because it serializes engine state into a stable browser contract. |
| T005 | 5 | Build the playable browser shell in `src/clickup_control_plane/tetris/assets/tetris.js` and `src/clickup_control_plane/tetris/assets/tetris.css`. | Client loop, rendering, and keyboard control wiring are substantial but bounded once the route contract exists. |
| T006 | 3 | Add a dedicated local Tetris runtime path so `/tetris` can start without ClickUp/n8n bootstrap env for manual verification. | Moderate decoupling work across app bootstrap, config, and dev-facing docs/runtime seams without changing the authoritative game logic. |
| T007 | 3 | Add line-clear and score behavior in `src/clickup_control_plane/tetris/engine.py` and `src/clickup_control_plane/tetris/service.py`. | Targeted extension of the core engine after the base transitions exist. |
| T008 | 2 | Add deterministic unit coverage in `tests/unit/test_tetris_engine.py`. | Straightforward once engine interfaces are stable. |
| T009 | 3 | Finalize game-over and restart handling across `src/clickup_control_plane/tetris/engine.py`, `service.py`, and `routes.py`. | Moderate extension of existing session flow with a few invariants to preserve. |
| T010 | 1 | Add FastAPI integration coverage in `tests/integration/test_tetris_routes.py`. | Focused black-box verification using the already-defined runtime contract. |
| T011 | 1 | Refresh HUD/tasking traceability and docstrings for the Tetris artifacts. | Small closeout work after the main implementation shape settles. |

---

### T003 — Solution Sketch

**Modify**: `src/clickup_control_plane/tetris/engine.py:tick_session` and `src/clickup_control_plane/tetris/service.py` — centralize authoritative gameplay transitions behind typed helper functions.
**Create**: `src/clickup_control_plane/tetris/engine.py` and `src/clickup_control_plane/tetris/service.py`
**Reuse**: `src/clickup_control_plane/app.py:create_app` request-state patterns and existing dataclass-heavy Python service style in the repo
**Composition**: Route handlers call a session service; the service delegates every rules mutation to pure-ish engine helpers over typed state objects.
**Failing test assertion**: Moving, rotating, ticking, and locking pieces must preserve bounds/collision invariants while yielding a legal next session state.
**Domains touched**: `src/clickup_control_plane/tetris/*.py`, `tests/unit/test_tetris_engine.py`

### T005 — Solution Sketch

**Modify**: `src/clickup_control_plane/tetris/routes.py` — emit the HTML shell and asset references the browser uses for the playable surface.
**Create**: `src/clickup_control_plane/tetris/assets/tetris.js` and `src/clickup_control_plane/tetris/assets/tetris.css`
**Reuse**: Server-authored authoritative state from the Tetris route/session contract rather than embedding game rules in the browser
**Composition**: The browser shell renders server session snapshots, sends input commands, advances timed ticks, and updates score/game-over panels from returned state.
**Failing test assertion**: Loading the page should produce a visible playable board whose controls map to valid session mutations without desynchronizing from server state.
**Domains touched**: `src/clickup_control_plane/tetris/routes.py`, `src/clickup_control_plane/tetris/assets/*`, `tests/integration/test_tetris_routes.py`

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 2 | 1 | 0 |
| Phase 2: Foundational | 8 | 2 | 0 |
| Phase 3: User Story 1 | 8 | 2 | 0 |
| Phase 4: User Story 2 | 5 | 2 | 0 |
| Phase 5: User Story 3 | 4 | 2 | 0 |
| Phase 6: Polish & Cross-Cutting Concerns | 4 | 2 | 0 |
| **Total** | **31** | **11** | **0** |

---

## Warnings

- No tasks are currently estimated at 8 or 13 points; if engine or browser scope grows during implementation, split the task before re-estimating.
- Phase-level parallelism is intentionally limited because the route contract and authoritative engine must stabilize before the browser shell and verification work can proceed safely.
- The main uncertainty remains how much browser-side code is needed to keep the feature self-contained inside the existing FastAPI service without introducing a separate frontend stack.
