# /speckit.implement

## User Input

```text
$ARGUMENTS
```

## Contract

Execute implementation through script-owned preflight, task start, root-owned task implementation, persistent QA subagent review, script-owned QA handoff, and documentation updates. `/speckit.implement` itself owns the helper sequence, implements one task at a time, hands completed work to QA, and keeps the Codex session warm across queued tasks until the task gate says implementation is complete.

1. Resolve feature context and run task pre-implementation gate checks.
2. Consume the next registered task from `.speckit/task-ledger.jsonl` and the matching `tasks.md` contract.
3. Spawn and reuse one persistent `spawn_agent` QA subagent on `gpt-5.4-mini`.
4. Implement one task at a time in the root agent, then hand the completed task to QA; route QA failures back into the same root-agent task loop before closeout.
5. Run script-owned offline QA handoff and canonical ledger closeout only after the root agent has a QA-pass-worthy task result.
6. If the task gate reports more open tasks, continue the same warm Codex session and reuse the same QA subagent on the next registered task.
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

Context loading rule:
- Do not reread `spec.md` as routine per-task grounding during implement.
- Read only the current task line from `tasks.md`, the relevant `plan.md` slice for that task's seam, and the exact code/doc seam to be changed.
- Carry forward the active task's local context across adjacent work on the same seam.
- Reread broader feature context only when the next task changes seam materially or when tests/QA contradict the current task-local model.

Before task execution or handoff:
- Ensure the implementation branch named after `FEATURE_DIR` is checked out or created from `main`.
- Keep `specify` on `main`; branch creation belongs to the implement path, not the spec path.
- If the current checkout is dirty, stop and ask the user to commit, stash, or discard the changes before branch checkout or task execution.

### 3. Task execution flow (required)

- Tasking has already registered the task queue into `.speckit/task-ledger.jsonl`.
- Select the next registered task in `tasks.md` order.
- Append `task_started` only when the selected task is not already active.
- Execute only the next eligible task from `tasks.md` and the resolved feature context.
- `/speckit.implement` itself must use `spawn_agent` directly for QA.
- Do not use `fork_context: true` because the QA subagent must run on `gpt-5.4-mini`.
- Spawn exactly one persistent subagent and reuse it for the full implement session:
  - QA subagent
- The root agent is both implementer and orchestrator. Do not let the QA subagent coordinate closeout directly.
- The root-agent default is intentionally simple:
  - check the next eligible task/start gate
  - implement the next task from `tasks.md`
  - send the completed task result to QA
  - when QA returns a pass-worthy offline-QA result, record any real task commit metadata and run closeout
  - advance to the next task
- Preserve task-ledger and dependency gates exactly. Do not begin another task until the current task has passed QA and closeout is complete.
- In the normal case, the root agent should implement directly from the selected task entry and feature context rather than creating an extra builder delegation layer.
- Do not broad-reground in the full feature spec between tasks when the active seam has not changed.
- Additional root-agent investigation is only justified on concrete signals such as:
  - invalid or empty QA completion
  - QA findings that need clarification before retry
  - offline QA / closeout contradictions
- The root agent should not be the source of routine delay. When the task packet is already clear enough, implement it directly instead of expanding the context unnecessarily.
- For code-bearing tasks, the root agent must run a tight red-green loop before QA:
  - derive the behavior from the task acceptance criteria
  - write one focused regression test that should fail against the current code
  - run that test and confirm the failure
  - implement the smallest fix that makes the regression pass
  - rerun the targeted test and any directly relevant checks until they are green
- For docs-only, manifest-only, or operator-guidance tasks, skip the failing-test phase and use the narrowest deterministic validation available instead.
- The QA subagent may use `.claude/commands/speckit.qa.md` as its standing review contract because it is a task reviewer rather than the implementation worker.
- The orchestrator's QA handoff template must explicitly instruct:
  - run `scripts/speckit_offline_qa_handoff.py` first for the active task
  - then apply the `/speckit.qa` behavioral review rules to interpret that canonical result
  - only do deeper manual inspection when the offline-QA result fails, is invalid, or needs explanation for a root-agent retry
- Per task, the root agent must:
  1. identify the behavior from the selected task and acceptance criteria
  2. write and run the focused red test for code-bearing work, or the narrow deterministic validation for non-code work
  3. implement the selected task from the resolved feature context
  4. rerun the targeted test or directly relevant checks until the task is green
  5. collect changed files and test evidence
  6. send the task result, task id, changed files, and test evidence to the QA subagent
  7. the QA subagent owns the canonical offline-QA stage for that task by preparing the payload as needed and running `scripts/speckit_offline_qa_handoff.py`
  8. if QA returns `FIX_REQUIRED`, apply those findings in the root agent and retry the same task
  9. once QA returns a pass-worthy offline-QA result, run `scripts/speckit_closeout_task.py` and include commit metadata only if a real task commit exists
  10. if closeout returns `clickup_sync_status=pending_agent_update`, the root agent must use the connected Composio ClickUp tools to set that mapped task to the exact `clickup_desired_status` value after repo closeout succeeds
  11. if the Composio ClickUp update fails, keep repo closeout authoritative, report the failure as retry-needed, and continue without rolling back task closure
- The orchestrator may verify task identity, required artifacts, and evidence completeness before the QA handoff, but must not perform an additional correctness review or substitute its own QA judgment for the QA subagent verdict.
- A root-agent implementation result is not commit authorization. QA must run against the active branch/worktree state and must not depend on a pre-QA commit.
- Agent-owned ClickUp completion flow after closeout:
  - read `clickup_task_id`, `clickup_desired_status`, and `clickup_sync_status` from the closeout payload
  - when `clickup_sync_status=pending_agent_update`, use the connected ClickUp Composio toolkit after closeout, not before
  - validate or re-derive the exact allowed done label if the update rejects the requested status
  - never reopen or roll back the repo task when the external ClickUp update fails
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
- Do not let the QA subagent invoke closeout, task-gate, or pipeline phase completion.
- Do not use a Codex subrunner for implement task execution.
- Do not treat quiet subagents as stalled until the defined wait budget is exhausted.
- Do not trust stale or mis-scoped QA JSON artifacts; reject them if `task_id`, `qa_run_id`, or required fields do not match the active task.
- Do not treat an empty/null subagent completion as a valid QA verdict.
