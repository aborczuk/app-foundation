# Tasks: Make Tetris

**Input**: Design documents from `/specs/029-make-tetris/`
**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories)

**One-Line Purpose**: Deliver a browser-playable Tetris loop from the existing FastAPI app with a Python-authoritative game engine and deterministic regression coverage.

## Format: `[ID] [P?] [Story] Description — file:symbol`

- `[P]`: Task can run in parallel only when the file ownership and dependencies are disjoint.
- `[H]`: Human-required external/manual action.
- `[USn]`: User story label required only in user-story phases.
- Every task includes concrete file ownership and primary symbol scope.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Record the runtime gate and establish the package seams the feature will use.
**External Ingress + Runtime Readiness Gate**: Required. This feature adds a browser-facing FastAPI route and static delivery surface.

- [ ] T000 Record External Ingress + Runtime Readiness Gate status, route ownership, and rollout note in `specs/029-make-tetris/tasks.md` — `specs/029-make-tetris/tasks.md:T000`
- [ ] T001 Create the Tetris package scaffold for runtime, engine, and browser-shell ownership in `src/clickup_control_plane/tetris/__init__.py`, `src/clickup_control_plane/tetris/router.py`, `src/clickup_control_plane/tetris/models.py`, and `src/clickup_control_plane/tetris/service.py` — `src/clickup_control_plane/tetris/__init__.py:package`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the host route and the typed engine seams before story-level work.

**CRITICAL**: No story implementation starts until the runtime route and core engine symbols exist.

- [ ] T002 Wire an isolated Tetris route into the FastAPI app without disturbing existing endpoints in `src/clickup_control_plane/app.py` and `src/clickup_control_plane/tetris/router.py` — `src/clickup_control_plane/app.py:app`
- [ ] T003 Define typed board, piece, score, and session-state models in `src/clickup_control_plane/tetris/models.py` — `src/clickup_control_plane/tetris/models.py:TetrisSessionState`
- [ ] T004 Implement the authoritative game engine API for spawn, step, move, rotate, lock, clear, score, and restart in `src/clickup_control_plane/tetris/service.py` — `src/clickup_control_plane/tetris/service.py:TetrisGameService`

---

## Phase 3: User Story 1 - Start and Play a Tetris Game (Priority: P1) 🎯 MVP

**Goal**: A user can open the Tetris page and play a live falling-piece session with legal movement and rotation behavior.

**Independent Test**: Open the Tetris route, start a session, move and rotate pieces, and confirm state updates respect board bounds and collision rules.

### Tests for User Story 1

- [ ] T005 [P] [US1] Add deterministic engine tests for spawn, gravity progression, lateral movement, and rotation boundary/collision behavior in `tests/unit/test_tetris_engine.py` — `tests/unit/test_tetris_engine.py:test_spawn_and_movement_rules`
- [ ] T006 [P] [US1] Add route/runtime integration coverage for serving the Tetris experience from the FastAPI surface in `tests/integration/test_tetris_route.py` — `tests/integration/test_tetris_route.py:test_tetris_route_serves_playable_shell`

### Implementation for User Story 1

- [ ] T007 [US1] Implement session bootstrap and per-tick state progression handlers in `src/clickup_control_plane/tetris/service.py` and `src/clickup_control_plane/tetris/router.py` — `src/clickup_control_plane/tetris/router.py:create_tetris_session`
- [ ] T008 [US1] Build the browser shell for board rendering, keyboard input, and state polling in `src/clickup_control_plane/tetris/router.py`, `src/clickup_control_plane/tetris/templates/tetris.html`, and `src/clickup_control_plane/tetris/static/tetris.js` — `src/clickup_control_plane/tetris/static/tetris.js:bindTetrisControls`

---

## Phase 4: User Story 2 - Clear Lines and Track Score (Priority: P2)

**Goal**: Completed rows clear correctly and the score updates in the same session.

**Independent Test**: Play until a row is completed, confirm the row disappears, the board collapses cleanly, and the score increases in the UI.

### Tests for User Story 2

- [ ] T009 [P] [US2] Add unit tests for single-line, multi-line, and score-update transitions in `tests/unit/test_tetris_engine.py` — `tests/unit/test_tetris_engine.py:test_line_clear_and_score_updates`

### Implementation for User Story 2

- [ ] T010 [US2] Implement line-clear collapse and scoring transitions in `src/clickup_control_plane/tetris/service.py` — `src/clickup_control_plane/tetris/service.py:apply_lock_and_clear`
- [ ] T011 [US2] Surface score and cleared-board updates in the browser shell contract in `src/clickup_control_plane/tetris/templates/tetris.html` and `src/clickup_control_plane/tetris/static/tetris.js` — `src/clickup_control_plane/tetris/static/tetris.js:renderScoreboard`

---

## Phase 5: User Story 3 - Reach Game Over and Restart (Priority: P3)

**Goal**: A user can see game over when no new piece can spawn and can restart into a fresh session immediately.

**Independent Test**: Drive the board to a blocked spawn state, confirm game-over behavior freezes mutation, then restart and verify board and score reset.

### Tests for User Story 3

- [ ] T012 [P] [US3] Add unit coverage for blocked-spawn game over and full-session restart reset in `tests/unit/test_tetris_engine.py` — `tests/unit/test_tetris_engine.py:test_game_over_and_restart`
- [ ] T013 [P] [US3] Add integration coverage for game-over display and restart flow at the HTTP/runtime seam in `tests/integration/test_tetris_route.py` — `tests/integration/test_tetris_route.py:test_game_over_and_restart_flow`

### Implementation for User Story 3

- [ ] T014 [US3] Implement blocked-spawn game-over detection and immutable ended-session behavior in `src/clickup_control_plane/tetris/service.py` — `src/clickup_control_plane/tetris/service.py:detect_game_over`
- [ ] T015 [US3] Implement restart endpoint/state reset and browser restart affordance in `src/clickup_control_plane/tetris/router.py`, `src/clickup_control_plane/tetris/templates/tetris.html`, and `src/clickup_control_plane/tetris/static/tetris.js` — `src/clickup_control_plane/tetris/router.py:restart_tetris_session`

---

## Phase 6: Polish & Cross-Cutting Verification

**Purpose**: Close the loop on deterministic verification and implementation handoff clarity.

- [ ] T016 [P] Add plan-to-task trace notes and scenario coverage references in `specs/029-make-tetris/tasks.md` and generated HUDs — `specs/029-make-tetris/tasks.md:traceability`
- [ ] T017 Add implementation quickstart/run notes for exercising the Tetris route locally in `specs/029-make-tetris/quickstart.md` — `specs/029-make-tetris/quickstart.md:local_verification`

---

## Dependency Order

- T001 -> T002, T003, T004
- T002, T003, T004 -> T005, T006, T007, T008
- T007, T008 -> T009, T010, T011
- T010, T011 -> T012, T013, T014, T015
- T012, T013, T014, T015 -> T016, T017

## Implementation Strategy

- Deliver the runtime-host seam and typed engine first so gameplay logic stays authoritative in Python.
- Complete User Story 1 before line-clear/score work.
- Add game-over/restart only after the engine and browser shell are stable enough to support full-loop regression tests.
