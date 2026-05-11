# Tasks: make tetris

**Input**: Design documents from `/specs/029-make-tetris/`
**Prerequisites**: `plan.md`, `spec.md`, `spec.json`
**Tests**: Deterministic unit and integration coverage are required because the feature introduces a rule-heavy gameplay state machine into the FastAPI runtime.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel when the listed files do not overlap.
- **[Story]**: Required only for tasks inside user story phases.
- Every task description includes concrete file paths or file:symbol seams.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the isolated Tetris runtime surface inside the existing app without perturbing current control-plane routes.

- [X] T001 Extend `src/clickup_control_plane/app.py:create_app` and create `src/clickup_control_plane/tetris/__init__.py`, `src/clickup_control_plane/tetris/routes.py`, and `src/clickup_control_plane/tetris/assets/` scaffolding so the FastAPI app has a dedicated Tetris mount seam for PL-01.

**Checkpoint**: The repo has a dedicated Tetris package and a single runtime seam in `create_app()` for the feature.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Build the authoritative typed gameplay core that every user story depends on.

**⚠️ CRITICAL**: No user story task should begin before this phase is coherent.

- [X] T002 Create typed gameplay state symbols in `src/clickup_control_plane/tetris/models.py` and piece definitions in `src/clickup_control_plane/tetris/pieces.py` for board geometry, tetromino orientations, score state, and session status required by PL-02.
- [X] T003 Implement deterministic state transitions in `src/clickup_control_plane/tetris/engine.py` and `src/clickup_control_plane/tetris/service.py` for spawn, move, rotate, gravity tick, lock, line-clear preparation, score accumulation hooks, and restartable session orchestration from PL-02.

**Checkpoint**: The Tetris package owns a typed game-state engine that the browser shell can call without embedding game rules in UI code.

## Phase 3: User Story 1 - Start and Play a Tetris Game (Priority: P1)

**Goal**: Opening the feature starts a playable session with visible board state and responsive controls.

**Independent Test**: Open the Tetris page, confirm an empty board plus active piece are rendered, then move/rotate the active piece while gravity continues to advance play.

- [X] T004 [US1] Add the initial game page and session endpoints in `src/clickup_control_plane/tetris/routes.py` and wire them from `src/clickup_control_plane/app.py:create_app` so the browser can fetch a fresh authoritative session and tick/move/rotate commands through PL-01 and PL-03 seams.
- [ ] T005 [US1] Build the playable browser shell in `src/clickup_control_plane/tetris/assets/tetris.js`, `src/clickup_control_plane/tetris/assets/tetris.css`, and the page response in `src/clickup_control_plane/tetris/routes.py` so the board, active piece, controls, score panel, and game loop render from server-backed session state.

## Phase 4: User Story 2 - Clear Lines and Track Score (Priority: P2)

**Goal**: Completed rows clear deterministically and the visible score updates in the same session.

**Independent Test**: Drive the engine into a completed row, confirm the row disappears, the board collapses correctly, and the rendered score increases without resetting the session.

- [ ] T006 [US2] Complete line-clear and scoring behavior in `src/clickup_control_plane/tetris/engine.py` and `src/clickup_control_plane/tetris/service.py` so locked pieces trigger row detection, collapse logic, score updates, and next-piece continuation consistent with PL-02.
- [ ] T007 [US2] Add deterministic unit coverage in `tests/unit/test_tetris_engine.py` for boundary movement, blocked rotation, single/multi-line clears, score updates, and next-piece continuation required by PL-04.

## Phase 5: User Story 3 - Reach Game Over and Restart (Priority: P3)

**Goal**: The session reaches a stable game-over state and can restart into a fresh run immediately.

**Independent Test**: Play or simulate a full board until a new piece cannot spawn, verify controls stop mutating the ended session, then restart and observe a clean board plus zeroed score.

- [ ] T008 [US3] Finalize terminal-state and restart handling in `src/clickup_control_plane/tetris/engine.py`, `src/clickup_control_plane/tetris/service.py`, and `src/clickup_control_plane/tetris/routes.py` so illegal spawn transitions mark the session game over, post-game commands are inert, and restart creates a fresh authoritative session.
- [ ] T009 [US3] Add end-to-end runtime verification in `tests/integration/test_tetris_routes.py` for opening the Tetris surface, progressing session state, reaching game over, and restarting through the FastAPI route/runtime seam defined by PL-04.

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Close the loop on artifact hygiene and feature-facing documentation that supports implementation and verification.

- [ ] T010 Update `specs/029-make-tetris/tasks.md`, generated HUDs under `specs/029-make-tetris/huds/`, and any touched docstrings in `src/clickup_control_plane/tetris/*.py` so the solution artifact set preserves slice-to-task traceability, explicit constraints, and implement-ready acceptance criteria.

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 must finish before any foundational or story work because it establishes the route/package seam.
- Phase 2 must finish before any story work because every gameplay and browser interaction depends on the typed engine/service core.
- Phase 3 delivers the MVP playable loop.
- Phase 4 extends the same authoritative session with clear/score behavior after the MVP path works.
- Phase 5 depends on the prior runtime and engine behavior to close the full play loop.
- Phase 6 runs after the feature tasks are materially settled.

### User Story Dependencies

- **US1**: Depends on T001-T003 and is the MVP entry point.
- **US2**: Depends on US1 runtime wiring plus T006.
- **US3**: Depends on US1 and US2 behavior because game over and restart operate on the complete session loop.

### Parallel Opportunities

- T002 and T003 should remain sequential because the engine depends on the typed model layer.
- T004 and T005 should remain sequential because the browser shell depends on the route/session contract.
- T007 can start after T006’s public engine behavior is stable.
- T009 can start after T008’s route/runtime contract is stable.

## Implementation Strategy

### MVP First

1. Finish T001-T003 to establish the Tetris package and deterministic engine core.
2. Finish T004-T005 to deliver User Story 1 as the first playable milestone.
3. Verify the MVP before expanding rule coverage and terminal-state behavior.

### Incremental Delivery

1. Add line-clear and score behavior with T006-T007.
2. Add game-over and restart behavior with T008-T009.
3. Close with T010 so the HUD/tasking artifacts stay aligned with the implemented design.

## Plan Design Slice Index

Use these plan slices as the authoritative tasking inputs:

- Slice PL-01 - Tetris Runtime Surface
- Slice PL-02 - Authoritative Game-State Engine
- Slice PL-03 - Playable Browser Shell
- Slice PL-04 - Deterministic Verification Gates
