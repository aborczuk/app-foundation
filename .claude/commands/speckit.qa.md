# /speckit.qa

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Run behavioral QA for a completed task to verify implementation against acceptance criteria, detect drift, and emit a structured PASS/FIX_REQUIRED verdict.

1. Resolve feature context and task HUD.
2. Read acceptance criteria from HUD (or tasks.md fallback).
3. Review the deterministic test logs provided in the handoff payload.
4. Verify implementation matches acceptance criteria (semantic drift detection).
5. Emit structured verdict JSON with specific findings.

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

The deterministic behavioral script has already run the tests. Review the `test_runs` evidence in the handoff payload:
- Confirm that tests covering the changed files were actually executed.
- Confirm that all relevant test runs have `exit_code == 0`.
- If tests were skipped or failed, this is a blocking finding.

Do not run tests manually unless the provided logs are ambiguous or missing.

### 4. Drift detection

Check that the implementation addresses the acceptance criteria:
- **File symbol check**: Was the HUD's `File:Symbol` actually modified?
- **Keyword match**: Do changed files contain keywords from acceptance criteria?
- **Test coverage**: Do tests verify the acceptance criteria?

If drift detected → `FIX_REQUIRED: IMPLEMENTATION_DRIFT`

### 5. Verdict emission

The QA agent emits a JSON result:

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

The behavioral QA agent is invoked by `offline_qa.py` after schema validation. The combined result includes both schema and behavioral findings.

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
