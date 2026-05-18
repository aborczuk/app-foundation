# /speckit.implement

## User Input

```text
$ARGUMENTS
```

## Contract

Execute implementation through script-owned preflight, task start, persistent builder/QA subagent orchestration, script-owned QA handoff, and documentation updates. `/speckit.implement` itself is the orchestrator. It owns the helper sequence, mediates all builder↔QA handoff directly, and keeps the Codex session warm across queued tasks until the task gate says implementation is complete.

1. Resolve feature context and run HUD-only pre-implementation gate checks.
2. Consume the next registered task from `.speckit/task-ledger.jsonl` and the matching `tasks.md` / HUD contract.
3. Spawn and reuse two persistent `spawn_agent` subagents on `gpt-5.4-mini`: one builder and one QA reviewer.
4. Mediate builder→QA handoff for one task at a time; route QA failures back to the same builder before closeout.
5. Run script-owned offline QA handoff and canonical ledger closeout only after the orchestrator has a QA-pass-worthy task result.
6. If the task gate reports more open tasks, continue the same warm Codex session and reuse the same builder/QA subagents on the next registered task.
6. Update quickstart runbook + decision log via `scripts/speckit_implement_docs.py`.
7. Preserve GitHub sync handoff via `/speckit.checkpoint Phase [N]` compact status line; do not emit a prose summary.

## Guidance

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
- The orchestrator default is intentionally minimal:
  - check the next eligible task/start gate
  - send the next task HUD to the builder
  - forward the builder result to QA
  - when QA returns a pass-worthy offline-QA result, create the implementation commit and run closeout
  - advance to the next task
- When the builder finishes a task and that task moves into QA/offline-QA, do not idle the builder if another task is already ledger-eligible.
- If `assert-can-start` allows a parallel or otherwise dependency-safe next task, send that next task HUD to the builder while QA/offline-QA continues on the previous task.
- Preserve task-ledger and dependency gates exactly; parallel continuation is allowed only when the ledger says the next task can start.
- In the normal case, the orchestrator role is managerial rather than implementation-focused. Do not add extra repo exploration, seam rereads, or independent code analysis before every task handoff.
- Additional orchestrator investigation is only justified on concrete signals such as:
  - invalid or empty builder/QA completion
  - QA findings that need clarification before retry
  - offline QA / closeout contradictions
  - a builder request for more bounded context
- The orchestrator should not be the source of routine delay. When the task packet is already clear enough, pass it through immediately instead of expanding the context on the orchestrator side.
- Do not send the full implement command doc as the builder subagent prompt.
- The builder subagent should receive the selected task HUD as the default implementation packet.
- Only add extra context when the builder explicitly asks for it or a concrete failure requires it.
- Any extra context must stay narrow and task-local.
- The QA subagent may use `.claude/commands/speckit.qa.md` as its standing review contract because it is a task reviewer rather than the implementation worker.
- The orchestrator's QA handoff template must explicitly instruct:
  - run `scripts/speckit_offline_qa_handoff.py` first for the active task
  - then apply the `/speckit.qa` behavioral review rules to interpret that canonical result
  - only do deeper manual inspection when the offline-QA result fails, is invalid, or needs explanation for a builder retry
- Per task, the orchestrator must:
  1. send the selected task, HUD, and feature context to the builder
  2. collect the builder result
  3. send the builder result, task id, HUD path, changed files, and test evidence to the QA subagent
  4. the QA subagent owns the canonical offline-QA stage for that task by preparing the payload as needed and running `scripts/speckit_offline_qa_handoff.py`
  5. if QA returns `FIX_REQUIRED`, send those findings back to the same builder and retry the same task
  6. once QA returns a pass-worthy offline-QA result, stop the subagent loop for that task, create the implementation commit, and run `scripts/speckit_closeout_task.py`
- The orchestrator may verify task identity, required artifacts, and evidence completeness before the QA handoff, but must not perform an additional correctness review or substitute its own QA judgment for the QA subagent verdict.
- A builder result is not commit authorization. Implementation commits must wait until the QA subagent returns a pass-worthy offline-QA result for the active task.
- Guard JSON payload/result handling actively:
  - extract a compact decision summary once rather than repeatedly rereading full payload/result JSON artifacts
  - QA payload minimum fields: `feature_id`, `task_id`, `changed_files`, `acceptance_criteria`, `test_runs`
  - QA result minimum fields: `qa_run_id`, `task_id`, `verdict`, `findings`, `changed_files_considered`, `payload_file`, `result_file`
  - reject a QA payload/result as invalid if the current task id does not match, required fields are missing, or the result run id is older than the active payload/run
  - only reread a full QA payload/result artifact if the file changed, a new run id was produced, or a downstream gate contradicted the cached summary
- Use an explicit wait budget before declaring a subagent stalled:
  - first wait window: allow a normal response window before intervening
  - second wait window: if still quiet but not failed, allow one extended wait
  - only after both wait windows expire may the orchestrator mark the builder or QA subagent as stalled
- Treat invalid or empty subagent completions as orchestration failures, not verdicts:
  - an empty/null completion is `invalid_completion`, not `PASS` and not `FIX_REQUIRED`
  - retry once against the same subagent with a stricter response instruction
  - if the retry is still empty/invalid, respawn a replacement subagent before continuing the task
- Do not route task execution through `scripts/speckit_codex_handoff_runner.py`.
- Do not delegate implement orchestration to `scripts/speckit_implement_step.py`.
- Preserve task dependency and phase ordering.
- Emit required task-ledger progression events via `scripts/task_ledger.py`.
- Run targeted verification before closeout (tests/diagnostics/gates required by task scope).
- Use canonical script-owned QA + closeout path:
  - `scripts/speckit_closeout_task.py`
- The QA subagent, not the orchestrator, owns invoking `scripts/speckit_offline_qa_handoff.py` for the active task.
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
- Do not treat quiet subagents as stalled until the defined wait budget is exhausted.
- Do not trust stale or mis-scoped QA JSON artifacts; reject them if `task_id`, `qa_run_id`, or required fields do not match the active task.
- Do not treat an empty/null subagent completion as a valid builder result or QA verdict.
