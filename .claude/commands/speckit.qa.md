# /speckit.qa

## User Input

```text
$ARGUMENTS
```

## Contract

Act as the persistent implement-session QA subagent for one completed task at a time. Own the canonical offline-QA stage for the active task: prepare the minimum valid task-scoped payload, run `scripts/speckit_offline_qa_handoff.py` immediately, and emit a structured PASS/FIX_REQUIRED result for the orchestrator using that canonical result. `scripts/speckit_closeout_task.py` remains orchestrator-owned after QA passes.

1. Resolve feature context and the active task entry in `tasks.md`.
2. Read acceptance criteria from `tasks.md`.
3. Build or correct the minimum valid task-scoped offline-QA payload from the builder output, changed files, and test evidence.
4. Run `scripts/speckit_offline_qa_handoff.py` for the active task immediately.
5. If offline QA fails or returns an invalid/contradictory result, inspect the task more deeply only as needed to explain the failure and route fixes.
6. If the offline QA passes, then continue to the other steps in this document. You must do a manual drift detection as well as check that the functionality exists, and works.
7. Emit structured PASS/FIX_REQUIRED findings back to the orchestrator only.

## Guidance

### 1. Setup + context resolution

Required arguments:
- `--feature-id` (e.g., `023`)
- `--task-id` (e.g., `T001`)

Optional:
- `--payload-file` — path to pre-built handoff payload
- `--result-file` — path to write verdict JSON

Resolve:
- `FEATURE_DIR` from `specs/{feature_id}-*`
- `TASKS_FILE` from `FEATURE_DIR/tasks.md`

### 2. Acceptance criteria extraction

Primary source: the executable task entry in `tasks.md`. At minimum, the task contract must expose acceptance via the task's `Independent Test` in the task phase.

If no acceptance criteria can be extracted from tasks.md → `FIX_REQUIRED: MISSING_ACCEPTANCE_CRITERIA`

### 3. Fail-fast offline QA

The QA subagent should treat `scripts/speckit_offline_qa_handoff.py` as the first-class gate for the active task:
- prepare the minimum valid task-scoped payload
- run the handoff script immediately
- use its result as the primary QA outcome

Do not do a long manual review before this step. Extra inspection is only for:
- invalid payload/result artifacts
- failed offline QA verdicts
- contradictory or unclear findings that need explanation before a builder retry

### 4. Test verification

The orchestrator provides the task-local `test_runs` evidence in the QA handoff payload:
- Confirm that tests covering the changed files were actually executed.
- Confirm that all relevant test runs have `exit_code == 0`.
- If tests were skipped or failed, this is a blocking finding.

Do not run tests manually unless the provided logs are ambiguous or missing. Do not emit ledger events or close tasks.

### 5. Drift detection

Check that the builder implementation addresses the acceptance criteria:
- **Primary seam check**: If the task contract or payload names a primary edit seam, was it actually modified?
- **Keyword match**: Do changed files contain keywords from acceptance criteria?
- **Test coverage**: Do tests verify the acceptance criteria?

If drift detected → `FIX_REQUIRED: IMPLEMENTATION_DRIFT`

### 6. Verdict emission

The QA subagent emits a JSON result back to the orchestrator:

```json
{
  "mode": "behavioral_qa",
  "feature_id": "023",
  "task_id": "T001",
  "qa_run_id": "implement-qa-20260511T120000Z",
  "verdict": "PASS",
  "findings": [],
  "warnings": [],
  "changed_files_considered": ["src/example.py"],
  "test_runs": [...],
  "acceptance_criteria": "...",
  "file_symbol": "..."
}
```

Verdict rules:
- `PASS` — no findings, all checks passed
- `FIX_REQUIRED` — one or more blocking findings

Findings are specific and actionable:
- `MISSING_ACCEPTANCE_CRITERIA` — no acceptance criteria in tasks.md
- `MISSING_CHANGED_FILES` — no changed files in payload
- `IMPLEMENTATION_DRIFT` — changed files don't match the task's declared seams or required edits
- `TESTS_FAILED` — one or more test runs failed
- `MISSING_TEST_EVIDENCE` — no tests found or run
- `INVALID_COMPLETION` — missing required result fields or empty completion payload
- `TASK_SCOPE_MISMATCH` — result task id or run id does not match the active orchestrator task/run

### 7. Integration with offline QA

This QA subagent is the orchestrator-facing owner of the canonical offline-QA stage inside `/speckit.implement`:
- prepare or repair the task-scoped payload
- run `scripts/speckit_offline_qa_handoff.py` first
- treat any offline-QA failure as an automatic fail
- always perform manual inspection after a passing offline-QA result

The behavioral QA agent invoked by `offline_qa.py` after schema validation remains the canonical downstream check. The combined result includes both schema and behavioral findings. A pass-worthy offline-QA result does not end review; it only allows the manual inspection step to proceed before any closeout.

The orchestrator must treat the QA result as invalid, not as a verdict, when:
- `qa_run_id` is missing
- `task_id` does not match the active task
- `changed_files_considered` is missing when changed files were part of the payload
- `payload_file` or `result_file` is missing
- the completion payload is empty/null

When that happens:
- retry once against the same QA subagent with a stricter response instruction
- if the retry is still invalid, respawn the QA subagent and rerun the review for the same task

To skip behavioral QA (e.g., for legacy specs without HUDs):
```bash
python scripts/offline_qa.py --payload-file ... --skip-behavioral
```

## Behavior rules

- Do not pass tasks with missing acceptance criteria.
- Do not trust pre-recorded test exit codes; always run tests fresh.
- Do not skip drift detection even if tests pass.
- Treat offline-QA failure as an automatic FAIL.
- Do manual inspection in all cases, including offline-QA PASS results.
- Keep findings specific and actionable (file names, symbol names, test names).
- Emit warnings for non-blocking issues (e.g., missing HUD but tasks.md has criteria).
- Do not append ledger events, close tasks, or emit phase-completion events.
- Do not emit an empty/null completion; that is `INVALID_COMPLETION`.
- Do not emit a QA result for the wrong `task_id` or stale `qa_run_id`.
