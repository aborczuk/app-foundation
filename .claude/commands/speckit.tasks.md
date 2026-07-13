---
description: Generate an upstream-style tasks.md for the feature, with story-level acceptance criteria as the only material extension.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. **Setup**: Run `.specify/scripts/python/check_prerequisites.py --json` from repo root and parse `FEATURE_DIR` and available documents.
2. **Load design documents**:
   - Required: `plan.md`, `spec.md`
   - Optional: `data-model.md`, `contracts/`, `research.md`, `quickstart.md`
3. **Generate tasks.md from the upstream structure**:
   - Organize tasks by phase and user story
   - Preserve story priority and dependencies from `spec.md` / `plan.md`
   - Include `Goal`, `Independent Test`, and `Acceptance Criteria` for each user story phase
   - Keep task lines concise, with exact file paths in the description
   - Add `[H]` only for explicit human/operator work in external systems
4. **Run estimation (mandatory)**:
   - Invoke `/speckit.estimate`
   - Clear any required breakdown loop before reporting completion
5. **Report**:
   - path to `tasks.md`
   - total task count
   - task count per user story
   - independent test criteria for each story
   - acceptance criteria coverage for each story
   - parallel opportunities
   - format validation result
   - path to `estimates.md`

Context for task generation: $ARGUMENTS

## Task Generation Rules

Use the upstream Spec Kit task shape with one extension: add `Acceptance Criteria` under each user story phase.

**Required task shape**:
- `- [ ] T0NN [P?|H?] [USn?] <action> in <path>`
- `[P]` and `[H]` are mutually exclusive.
- `[USn]` is required in user-story phases and forbidden in setup/foundational/polish phases.
- Task IDs must be sequential and unique.

**Required story phase shape**:
- `**Goal**`
- `**Independent Test**`
- `### Acceptance Criteria`

**Deterministic format gate (mandatory before reporting completion)**:
```bash
uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
```
- If exit code is non-zero: fix all reported errors and re-run.

**Phase structure**:
- Phase 1: Setup
- Phase 2: Foundational blockers
- Phase 3+: User stories in priority order, independently testable
- Final phase: Polish and cross-cutting validation
