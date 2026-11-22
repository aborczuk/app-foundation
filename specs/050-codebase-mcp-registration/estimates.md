# Effort Estimate: Codebase MCP Registration

**Date**: 2026-11-22 | **Total Points**: 12 | **T-shirt Size**: XS
**Estimated by**: AI (speckit.estimate)

## Per-Task Estimates

| Task ID | Points | Description | Rationale |
|---------|--------|-------------|-----------|
| T001 | 2 | Add shared configuration assertions | Reuses the existing TOML test module. |
| T002 | 2 | Add registration assertions | Straightforward assertions over parsed TOML. |
| T003 | 2 | Register existing MCP commands | Declarative update to one known configuration file. |
| T004 | 1 | Add Semble approval assertions | Extends the shared test module. |
| T005 | 1 | Set Semble approval modes | Changes two scalar values. |
| T006 | 1 | Add language-guidance assertion | Simple text assertion in the shared test module. |
| T007 | 1 | Clarify language guidance | Changes one existing sentence. |
| T008 | 1 | Run targeted verification | Executes one test selector and TOML parsing. |
| T009 | 1 | Review scoped diff | Confirms the preservation constraint. |

## Solution Sketch

All tasks are one- or two-point changes and require no detailed sketch. The implementation reuses `tests/unit/test_codex_config.py`, `.codex/config.toml`, and `AGENTS.md`; it introduces no new runtime component or state.

## Phase Totals

| Phase | Points | Task Count | Parallel Tasks |
|-------|--------|------------|----------------|
| Phase 1: Setup | 2 | 1 | 0 |
| Phase 2: User Story 1 | 4 | 2 | 0 |
| Phase 3: User Story 2 | 2 | 2 | 0 |
| Phase 4: User Story 3 | 2 | 2 | 0 |
| Phase 5: Verification | 2 | 2 | 0 |
| **Total** | **12** | **9** | **0** |

## Warnings

- No task is scored 8 or 13.
- No task has high uncertainty or asynchronous, state-safety, or transaction-integrity risk.
