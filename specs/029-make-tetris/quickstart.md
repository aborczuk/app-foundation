# Quickstart

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
