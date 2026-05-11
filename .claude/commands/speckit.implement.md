# /speckit.implement

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Execute implementation through script-owned preflight, task start, persistent builder/QA subagent orchestration, script-owned QA handoff, and documentation updates. `/speckit.implement` itself is the orchestrator. It owns the helper sequence, mediates all builder↔QA handoff directly, and keeps the Codex session warm across queued tasks until the task gate says implementation is complete.

1. Resolve feature context and run HUD-only pre-implementation gate checks.
2. Consume the next registered task from `.speckit/task-ledger.jsonl` and the matching `tasks.md` / HUD contract.
3. Spawn and reuse two persistent `spawn_agent` subagents on `gpt-5.4-mini`: one builder and one QA reviewer.
4. Mediate builder→QA handoff for one task at a time; route QA failures back to the same builder before closeout.
5. Run script-owned offline QA handoff and canonical ledger closeout only after the orchestrator has a QA-pass-worthy task result.
6. If the task gate reports more open tasks, continue the same warm Codex session and reuse the same builder/QA subagents on the next registered task.
6. Update quickstart runbook + decision log via `scripts/speckit_implement_docs.py`.
7. Preserve GitHub sync handoff via `/speckit.checkpoint Phase [N]` compact status line; do not emit a prose summary.

## Expanded Guidance (Load On Demand)

### 1. Setup + preflight

1. Run:
   - `.specify/scripts/python/check_prerequisites.py --json --require-tasks --include-tasks`
2. Resolve:
   - `FEATURE_DIR`
   - `AVAILABLE_DOCS`
3. Run gate status:
   - `uv run --no-sync python3 scripts/speckit_gate_status.py --mode implement --feature-dir "$FEATURE_DIR" --json`
4. Gate handling (required):
   - If `missing_task_hud`, stop and require at least one task HUD under `huds/`.
   - Map failures to `docs/governance/gate-reason-codes.yaml`.

### 2. Context + setup verification

Required context:
- `tasks.md`
- `plan.md`

If present, include:
- `data-model.md`
- `contracts/`
- `research.md`
- `quickstart.md`

Run setup verification:
- `uv run --no-sync python3 scripts/speckit_prepare_ignores.py --repo-root . --plan-file "$FEATURE_DIR/plan.md" --json`

Treat non-zero as hard-block.

Before task execution or handoff:
- Ensure the implementation branch named after `FEATURE_DIR` is checked out or created from `main`.
- Keep `specify` on `main`; branch creation belongs to the implement path, not the spec path.
- If the current checkout is dirty, stop and ask the user to commit, stash, or discard the changes before branch checkout or task execution.

### 3. Task execution flow (required)

- Tasking has already registered the task queue into `.speckit/task-ledger.jsonl`.
- Select the next registered task in `tasks.md` order.
- Append `task_started` only when the selected task is not already active.
- Execute only the next eligible task from `tasks.md` and corresponding HUD.
- `/speckit.implement` itself must use `spawn_agent` directly.
- Do not use `fork_context: true` because the builder and QA subagents must run on `gpt-5.4-mini`.
- Spawn exactly two persistent subagents and reuse them for the full implement session:
  - builder subagent
  - QA subagent
- The orchestrator agent is the mediator. Do not let the subagents coordinate closeout directly.
- Use the command docs themselves as the subagent prompts:
  - builder prompt: `.claude/commands/speckit.implement.md`
  - QA prompt: `.claude/commands/speckit.qa.md`
- Per task, the orchestrator must:
  1. send the selected task, HUD, and feature context to the builder
  2. collect the builder result
  3. send the builder result, acceptance criteria, HUD seam, and test evidence to the QA subagent
  4. if QA returns `FIX_REQUIRED`, send those findings back to the same builder and retry the same task
  5. once QA returns a pass-worthy handoff, stop the subagent loop for that task and let the script-owned QA/closeout path continue
- Do not route task execution through `scripts/speckit_codex_handoff_runner.py`.
- Do not delegate implement orchestration to `scripts/speckit_implement_step.py`.
- Preserve task dependency and phase ordering.
- Emit required task-ledger progression events via `scripts/task_ledger.py`.
- Run targeted verification before closeout (tests/diagnostics/gates required by task scope).
- Use canonical script-owned QA + closeout path:
  - `scripts/speckit_offline_qa_handoff.py`
  - `scripts/speckit_closeout_task.py`
- Subagents do not append ledger events, close tasks, or emit phase-completion events.

### 4. Documentation step (runner-owned until fully centralized)

Primary path (runner-owned, script-backed):
- `uv run --no-sync python3 scripts/speckit_implement_docs.py --feature-dir "$FEATURE_DIR" --entry-id "<task-or-run-id>" --runbook-note "<note>" --decision-entry "<decision>" --json`

The step runner invokes this helper after closeout; do not re-sequence these actions manually in the command doc.

Required outputs:
- update quickstart runbook notes for implementation outcome
- append decision-log entry with:
  - what changed
  - why it changed
  - what was decided
  - what artifact/behavior changed
  - relevant commit/PR/issue reference

If script path is temporarily unavailable, preserve these outputs manually in `quickstart.md` and keep format stable.

### 5. Completion

Return completion payload to the runner/driver when:
- required tasks for current scope are closed
- script-owned verification/QA paths passed
- required documentation update is complete
- the task gate has run after closeout so it can inspect the task ledger and either emit completion or point to the next open task

The task gate uses the task ledger as the source of truth for whether work is still open.

`implementation_completed` append is driver-owned (pipeline driver route), not command-doc-owned.

## Behavior rules

- Do not bypass script-owned gates or ledger sequencing.
- Do not mark task completion before tests/QA requirements pass.
- Do not perform manual quickstart/decision-log appends when `speckit_implement_docs.py` is available.
- Do not emit completion events from LLM content.
- Do not let the builder or QA subagents invoke closeout, task-gate, or pipeline phase completion.
- Do not use a Codex subrunner for implement task execution.
