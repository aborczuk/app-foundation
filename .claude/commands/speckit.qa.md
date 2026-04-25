# /speckit.qa

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Run behavioral QA for a completed task to verify implementation against acceptance criteria, detect drift, and emit a structured PASS/FIX_REQUIRED verdict.

1. Resolve feature context and task HUD.
2. Read acceptance criteria from HUD (or tasks.md fallback).
3. Run actual tests for changed files (not just schema checks).
4. Verify implementation matches acceptance criteria (drift detection).
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

### 3. Test execution

Run pytest for test files covering the changed files:
- If changed file is in `tests/` → run it directly
- If changed file is in `src/` → guess test file from module name (`test_{module}.py`)
- If no test files found → run `pytest -k {task_id_lower}` as fallback

A test run fails if `exit_code != 0`.

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
