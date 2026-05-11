# /speckit.qa

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Act as the persistent implement-session QA subagent for one completed task at a time. Review the builder output against task acceptance criteria, detect drift, and emit a structured PASS/FIX_REQUIRED verdict for the orchestrator. The downstream offline QA script remains the canonical closeout authority.

1. Resolve feature context and task HUD.
2. Read acceptance criteria from HUD (or tasks.md fallback).
3. Review the builder output, diff/test evidence, and HUD seam for the selected task.
4. Verify implementation matches acceptance criteria (semantic drift detection).
5. Emit structured PASS/FIX_REQUIRED findings back to the orchestrator only.

## Expanded Guidance (Load On Demand)

### 1. Setup + context resolution

Required arguments:
- `--feature-id` (e.g., `023`)
- `--task-id` (e.g., `T001`)

Optional:
- `--payload-file` — path to pre-built handoff payload
- `--result-file` — path to write verdict JSON

Resolve:
- `FEATURE_DIR` from `specs/{feature_id}-*`
- `HUD_PATH` from `FEATURE_DIR/huds/{task_id}.md`
- `TASKS_FILE` from `FEATURE_DIR/tasks.md`

### 2. Acceptance criteria extraction

Primary source: HUD `Functional Goal > Acceptance Criteria`

If HUD is missing or lacks acceptance criteria, fall back to tasks.md `Independent Test` within the task's phase.

If neither exists → `FIX_REQUIRED: MISSING_ACCEPTANCE_CRITERIA`

### 3. Test verification

The orchestrator provides the task-local `test_runs` evidence in the QA handoff payload:
- Confirm that tests covering the changed files were actually executed.
- Confirm that all relevant test runs have `exit_code == 0`.
- If tests were skipped or failed, this is a blocking finding.

Do not run tests manually unless the provided logs are ambiguous or missing. Do not emit ledger events or close tasks.

### 4. Drift detection

Check that the builder implementation addresses the acceptance criteria:
- **File symbol check**: Was the HUD's `File:Symbol` actually modified?
- **Keyword match**: Do changed files contain keywords from acceptance criteria?
- **Test coverage**: Do tests verify the acceptance criteria?

If drift detected → `FIX_REQUIRED: IMPLEMENTATION_DRIFT`

### 5. Verdict emission

The QA subagent emits a JSON result back to the orchestrator:

```json
{
  "mode": "behavioral_qa",
  "feature_id": "023",
  "task_id": "T001",
  "verdict": "PASS",
  "findings": [],
  "warnings": [],
  "test_runs": [...],
  "acceptance_criteria": "...",
  "file_symbol": "..."
}
```

Verdict rules:
- `PASS` — no findings, all checks passed
- `FIX_REQUIRED` — one or more blocking findings

Findings are specific and actionable:
- `MISSING_ACCEPTANCE_CRITERIA` — no acceptance criteria in HUD or tasks.md
- `MISSING_CHANGED_FILES` — no changed files in payload
- `IMPLEMENTATION_DRIFT` — changed files don't match HUD file:symbol
- `TESTS_FAILED` — one or more test runs failed
- `MISSING_TEST_EVIDENCE` — no tests found or run

### 6. Integration with offline QA

This QA subagent is the orchestrator-facing reviewer inside `/speckit.implement`. The script-owned offline QA path is still authoritative for canonical task closeout:
- `scripts/speckit_offline_qa_handoff.py`
- `scripts/speckit_closeout_task.py`

The behavioral QA agent invoked by `offline_qa.py` after schema validation remains the canonical downstream check. The combined result includes both schema and behavioral findings.

To skip behavioral QA (e.g., for legacy specs without HUDs):
```bash
python scripts/offline_qa.py --payload-file ... --skip-behavioral
```

## Behavior rules

- Do not pass tasks with missing acceptance criteria.
- Do not trust pre-recorded test exit codes; always run tests fresh.
- Do not skip drift detection even if tests pass.
- Keep findings specific and actionable (file names, symbol names, test names).
- Emit warnings for non-blocking issues (e.g., missing HUD but tasks.md has criteria).
- Do not append ledger events, close tasks, or emit phase-completion events.
