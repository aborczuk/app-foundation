---
description: Add an ad-hoc task to tasks.md with full architectural fit check, estimate it, and auto-sync spec.md when scope expands.
---

## User Input

```text
$ARGUMENTS
```

If `$ARGUMENTS` is empty, **STOP** and ask: "What do you need done? Describe the change in plain English."

## Purpose

This command is the **guardrailed shortcut** for ad-hoc changes. It ensures every change — no matter how small — fits the existing architecture before a task is written, that scope-expanding changes are synced into `spec.md`, and that the task is properly estimated and broken down before implementation begins.

Use this when you need a change done **now** without running the full specify → plan → tasks ceremony — but only when the change fits within the existing architecture. If it doesn't fit, this command gates and redirects to `/speckit.plan`.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute.
   - If tasks.md does not exist, **STOP** and ask: "No tasks.md found. Do you want me to create one, or should we run `/speckit.solution` first?"

2. **Load context**:
   - **Required**: `plan.md` — tech stack, architecture, module boundaries, file structure
   - **Required**: `spec.md` — user stories and scope boundaries
   - **If exists**: `specs/001-auto-options-trader/behavior-map.md` — runtime behavior map
   - **If exists**: `data-model.md`, `contracts/`, `research.md`
   - **Codebase tree**: Read `src/` directory structure to understand actual module layout
   - **Current tasks**: Read `tasks.md` to understand existing task IDs, phases, and placement

3. **Architectural fit check** — this is a hard gate:
   - Does the change fit within the existing architecture as defined in `plan.md` and `spec.md`?
   - Where exactly does it land: which module, file, and layer?
   - Does it respect the behavior map (no undocumented runtime behavior changes)?
   - Is it within existing spec scope (bug fix / improvement) or does it represent new scope?

   **If the change fits**: identify the exact landing zone and proceed to step 4.

   **If the change does NOT fit** (requires new modules, new architectural patterns, cross-cutting structural changes): **STOP** — tell the user:
   > "This change requires architectural review before a task can be written. Run `/speckit.plan` first, then return to `/speckit.addtobacklog`."

   **If the change is new scope** (not a bug fix or improvement to existing behavior): set a `SCOPE_EXPANDS=true` flag and proceed to step 4.

   **If the request is ambiguous**: ask a clarifying question before proceeding. Do NOT assume.

4. **Scope sync gate (new scope only)**:
   - If `SCOPE_EXPANDS=true`, run `/speckit.specify --update-current-spec "$ARGUMENTS"` before writing tasks.
   - Confirm `spec.md` and `checklists/requirements.md` reflect the new scope and contain no unresolved `[NEEDS CLARIFICATION]` markers.
   - Re-load `spec.md` after the sync and ensure the new task request is now in-scope.

5. **Write task(s) to tasks.md** using the format rules from `/speckit.solution`:
   - Read tasks.md and find the highest existing task ID (e.g., T050).
   - Assign the next sequential ID (e.g., T051).
   - Use the standard checklist format: `- [ ] T0XX [USn?] Description with exact file path`
   - Determine the correct phase placement:
     - If the task relates to an existing user story phase, add it to that phase.
     - If it's a cross-cutting concern, add it to the Polish phase.
     - If it doesn't fit any existing phase, append it to a new `## Ad-Hoc Tasks` section at the end (before Dependencies/Notes).
   - Include async lifecycle, state-safety, or transaction-integrity guard tasks if the change touches those paths (same rules as `/speckit.solution`).
   - Map the user story label if applicable.

6. **Run `/speckit.estimate`** on the updated tasks.md.
   - Estimate owns the breakdown loop: if any task scores 8 or 13 it will automatically invoke `/speckit.breakdown` and re-estimate until all tasks are ≤5 points.

7. **Commit planning artifacts**:
   - If `SCOPE_EXPANDS=true`, stage `spec.md`, `checklists/requirements.md`, `tasks.md`, and `estimates.md`.
   - If `SCOPE_EXPANDS=false`, stage only `tasks.md` and `estimates.md`.
   - Do not stage source files — implementation has not run yet.
   - Review the diff — never stage secrets or unrelated changes.
   - Commit message format:
     ```
     T0XX Add task: <short description>

     <what the task covers and why it fits the existing architecture>
     ```

8. **Prompt for next steps**:
   - Ask: "Tasks written and committed. Run `/speckit.implement` to proceed with implementation."
   - If `SCOPE_EXPANDS=true`, also report that spec sync was completed automatically via `/speckit.specify --update-current-spec`.

## Notes

- This command does NOT implement anything. Implementation is handled entirely by `/speckit.implement`.
- This command auto-updates `spec.md` and `checklists/requirements.md` only when the request is in-scope architecturally but out-of-scope behaviorally.
- This command does NOT update `plan.md`. If the change requires architectural changes, run `/speckit.plan` first.
- The task ID sequence is global to tasks.md — ad-hoc tasks get the next available ID, maintaining a single sequential timeline.
- TDD and all per-task validation rules are enforced at implementation time by `/speckit.implement` — not here.
- If `codebase-lsp` MCP server is connected, use `get_type`/`get_diagnostics` during implementation to verify types before writing and check for pyright errors after editing (same guidance as `/speckit.implement`).
