# Quickstart

## Local Tetris Runtime

- Start the dedicated local Tetris runtime without ClickUp or n8n bootstrap env:
  - `uv run python -m uvicorn src.clickup_control_plane.app:tetris_app --host 127.0.0.1 --port 8765`
- Open `http://127.0.0.1:8765/tetris`.
- Manual verification:
  - page loads and renders the board/HUD
  - `New Game` starts a fresh session
  - arrow keys or buttons move/rotate the active piece
  - the piece falls over time without any browser-side gameplay authority
- The full control-plane runtime still uses:
  - `uv run python -m uvicorn src.clickup_control_plane.app:app --host 127.0.0.1 --port 8765`

## Deterministic Operator Runbook Notes

### Recovery Delta Validation Notes


<!-- speckit_implement_docs:entry_id=T001:runbook -->
- Closed T001 at commit 76b01e4 after offline QA pass offline-qa-t001-20260511T010431Z.


<!-- speckit_implement_docs:entry_id=T002:runbook -->
- Closed T002 at commit fd0c9b6 after offline QA pass offline-qa-t002-20260511T011831Z.


<!-- speckit_implement_docs:entry_id=T003:runbook -->
- Closed T003 at commit 4c27024 after offline QA pass offline-qa-t003-20260511T012657Z.


<!-- speckit_implement_docs:entry_id=T004:runbook -->
- Closed T004 at commit ba4ec3b after offline QA pass offline-qa-t004-20260511T013443Z.


<!-- speckit_implement_docs:entry_id=T005:runbook -->
- Closed T005 at commit f8d8351 after offline QA pass offline-qa-t005-20260511T163610Z, including live localhost verification of page, assets, and command flow.


<!-- speckit_implement_docs:entry_id=T006:runbook -->
- Closed T006 at commit ac5e6da after offline QA pass offline-qa-t006-20260511T170013Z; added the dedicated tetris_app quickstart path so /tetris can start without ClickUp/n8n env.


<!-- speckit_implement_docs:entry_id=T007:runbook -->
- Closed T007 at commit 5a428e5 after offline QA pass offline-qa-t007-20260511T170725Z; fixed queue-replenishing continuation after lock and added single-line clear coverage.

## Decision Log

<!-- speckit_implement_docs:entry_id=T001:decision_log -->
- T001 introduced the isolated /tetris mount seam and package scaffold; behavioral QA and offline payload generation were updated to recognize the current HUD/workspace contract.

<!-- speckit_implement_docs:entry_id=T002:decision_log -->
- T002 established typed gameplay-state contracts and canonical tetromino metadata; behavioral QA now honors explicit payload test evidence for early model-only tasks.

<!-- speckit_implement_docs:entry_id=T003:decision_log -->
- T003 added the deterministic engine/service seams for spawn, move, rotate, gravity, lock, line-clear scoring, and restart orchestration, plus unit coverage for the core gameplay loop.

<!-- speckit_implement_docs:entry_id=T004:decision_log -->
- T004 added the initial Tetris runtime surface: HTML entry route plus authoritative session, move, rotate, and tick endpoints that delegate to TetrisService through the FastAPI app seam.

<!-- speckit_implement_docs:entry_id=T005:decision_log -->
- T005 introduced the playable browser shell with server-backed board rendering, controls, gravity loop, and asset delivery; verification required running the shared app with dummy control-plane env because Tetris still shares the global app lifespan.

<!-- speckit_implement_docs:entry_id=T006:decision_log -->
- T006 split the shared app bootstrap into full-runtime and Tetris-only lifespan paths, exposed src.clickup_control_plane.app:tetris_app for local verification, added config helper coverage, and documented the exact local run command in quickstart.md.

<!-- speckit_implement_docs:entry_id=T007:decision_log -->
- T007 tightened the service-facing continuation seam: when a lock exhausts the deterministic queue, TetrisService now replenishes and spawns the next piece instead of dropping the session into GAME_OVER; unit coverage now includes single-line clear collapse and continuation.
