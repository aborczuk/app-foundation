# /speckit.implement

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Execute implementation through deterministic HUD-gated preflight, task start, local Codex task execution, QA handoff, and documentation updates. The step runner owns the helper sequence.

1. Resolve feature context and run HUD-only pre-implementation gate checks.
2. Consume the next registered task from `.speckit/task-ledger.jsonl` and the matching `tasks.md` / HUD contract.
3. Run verification gates before task closeout.
4. Run offline QA handoff and canonical ledger closeout.
5. Update quickstart runbook + decision log via `scripts/speckit_implement_docs.py`.
6. Preserve GitHub sync handoff via `/speckit.checkpoint Phase [N]` compact status line; do not emit a prose summary.

## Expanded Guidance (Load On Demand)

### 1. Setup + deterministic preflight

1. Run:
   - `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks`
2. Resolve:
   - `FEATURE_DIR`
   - `AVAILABLE_DOCS`
3. Run gate status:
   - `uv run --no-sync python scripts/speckit_gate_status.py --mode implement --feature-dir "$FEATURE_DIR" --json`
4. Gate handling (required):
   - If `missing_e2e_md` or `missing_e2e_script`, stop and require `/speckit.e2e`.
   - If `missing_estimates_md`, stop and require `/speckit.estimate` (or `/speckit.solution` path that includes estimation).
   - Map failures to `docs/governance/gate-reason-codes.yaml`.
5. Checklist handling (required, until centralized in script):
   - If `checklists.incomplete_total > 0`, stop and ask human whether to proceed.
   - Continue only on explicit proceed confirmation.

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
- `uv run --no-sync python scripts/speckit_prepare_ignores.py --repo-root . --plan-file "$FEATURE_DIR/plan.md" --json`

Treat non-zero as hard-block.

### 3. Task execution flow (required)

- Tasking has already registered the task queue into `.speckit/task-ledger.jsonl`.
- Select the next registered task in `tasks.md` order.
- Append `task_started` only when the selected task is not already active.
- Execute only the next eligible task from `tasks.md` and corresponding HUD.
- Hand that task to the local Codex runner at `scripts/speckit_codex_handoff_runner.py`.
- If offline QA fails, feed the QA feedback back into the same runner session and retry the same task before closeout.
- Preserve task dependency and phase ordering.
- Emit required task-ledger progression events via `scripts/task_ledger.py`.
- Run targeted verification before closeout (tests/diagnostics/gates required by task scope).
- Use canonical QA + closeout path:
  - `scripts/speckit_offline_qa_handoff.py`
  - `scripts/speckit_closeout_task.py`

### 4. Documentation step (runner-owned until fully centralized)

Primary path (runner-owned, script-backed):
- `uv run --no-sync python scripts/speckit_implement_docs.py --feature-dir "$FEATURE_DIR" --entry-id "<task-or-run-id>" --runbook-note "<note>" --decision-entry "<decision>" --json`

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
- deterministic verification/QA paths passed
- required documentation update is complete
- the task gate has run after closeout so it can inspect the task ledger and either emit completion or point to the next open task

The task gate uses the task ledger as the source of truth for whether work is still open.

`implementation_completed` append is driver-owned (pipeline driver route), not command-doc-owned.

## Behavior rules

- Do not bypass script-owned gates or ledger sequencing.
- Do not mark task completion before tests/QA requirements pass.
- Do not perform manual quickstart/decision-log appends when `speckit_implement_docs.py` is available.
- Do not emit completion events from LLM content.
