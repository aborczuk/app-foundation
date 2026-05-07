# Effort Estimate: Make Tetris

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T000 | 1 | Record External Ingress + Runtime Readiness Gate status, route ownership, and rollout note | Documentation and traceability only. |
| T001 | 2 | Create the Tetris package scaffold for runtime, engine, and browser-shell ownership | Small structural scaffold across a new package namespace. |
| T002 | 3 | Wire an isolated Tetris route into the FastAPI app | Touches a live runtime seam and must not disturb existing endpoints. |
| T003 | 3 | Define typed board, piece, score, and session-state models | Core domain modeling with bounded scope but real state semantics. |
| T004 | 5 | Implement the authoritative game engine API | Primary gameplay logic with multiple transitions and invariants. |
| T005 | 3 | Add deterministic engine tests for spawn, gravity, movement, and rotation | Focused but non-trivial rule coverage. |
| T006 | 3 | Add route/runtime integration coverage for the Tetris shell | Integration seam with FastAPI rendering and startup behavior. |
| T007 | 5 | Implement session bootstrap and per-tick state progression handlers | Connects the route to the engine and session lifecycle behavior. |
| T008 | 5 | Build the browser shell for board rendering, keyboard input, and state polling | UI shell work spans templates, static assets, and interaction wiring. |
| T009 | 3 | Add unit tests for single-line, multi-line, and score-update transitions | Engine rule coverage with state and scoring interactions. |
| T010 | 5 | Implement line-clear collapse and scoring transitions | Gameplay logic with multiple branches and state updates. |
| T011 | 3 | Surface score and cleared-board updates in the browser shell contract | Couples UI rendering to engine output without changing core rules. |
| T012 | 3 | Add unit coverage for blocked-spawn game over and restart reset | Another rule-heavy engine behavior path. |
| T013 | 3 | Add integration coverage for game-over display and restart flow | Crosses runtime and browser shell boundaries, but stays bounded. |
| T014 | 5 | Implement blocked-spawn game-over detection and immutable ended-session behavior | Session-ending logic with clear state invariants. |
| T015 | 5 | Implement restart endpoint/state reset and browser restart affordance | Touches runtime, state reset, and UI restart plumbing. |
| T016 | 2 | Add plan-to-task trace notes and scenario coverage references | Light documentation and traceability update. |
| T017 | 2 | Add implementation quickstart/run notes for local Tetris verification | Small docs-only operational note. |

---

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup (Shared Infrastructure) | 3 | 2 | 2 |
| Phase 2: Foundational (Blocking Prerequisites) | 11 | 3 | 2 |
| Phase 3: User Story 1 - Start and Play a Tetris Game (Priority: P1) | 16 | 4 | 2 |
| Phase 4: User Story 2 - Clear Lines and Track Score (Priority: P2) | 11 | 3 | 1 |
| Phase 5: User Story 3 - Reach Game Over and Restart (Priority: P3) | 16 | 4 | 2 |
| Phase 6: Polish & Cross-Cutting Verification | 4 | 2 | 1 |
| **Total** | **61** | **18** | **10** |

---

## Warnings

- No 8/13-point tasks detected; `/speckit.breakdown` is not required.
- The highest-risk seams are the engine API, session lifecycle, and restart flow because they touch the authoritative gameplay state.
- Tetris route/browser-shell work should stay isolated from existing control-plane endpoints.
