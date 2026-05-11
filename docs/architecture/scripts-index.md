# Scripts Index

Status: canonical
Last reviewed: 2026-05-09
Owner: repository tooling

## Purpose

`scripts/` is a large flat namespace. This index groups it by responsibility so agents can reason about it as domains instead of as one undifferentiated directory.

## Domains

### Code Reading

- `scripts/read_code.py`
- `scripts/read_markdown.py`
- `scripts/read_code_health.py`
- `scripts/cgc_index_repo.py`
- `scripts/cgc_doctor.py`
- `scripts/cgc_safe_index.py`
- `scripts/cgc_owner.py`

Use these when discovering code, markdown, and index health.

### Governance Ledgers

- `scripts/pipeline_ledger.py`
- `scripts/task_ledger.py`

Use these for append-only state transitions and ordering checks.

### Pipeline Orchestration

- `scripts/pipeline_driver.py`
- `scripts/pipeline_driver_state.py`
- `scripts/pipeline_driver_contracts.py`
- `scripts/spec_routing.py`
- `scripts/speckit_*step.py`
- `scripts/speckit_*gate.py`

Use these when changing phase routing, gate enforcement, or step execution.

### Validation And Guards

- `scripts/edit_code.py`
- `scripts/pytest_guard.py`
- `scripts/ruff_guard.py`
- `scripts/pyright_guard.py`
- `scripts/git_diff_guard.py`
- `scripts/hook_*`
- `scripts/validate_*`

Use these when changing validation, policy enforcement, or handoff checks.

### QA And Handoff

- `scripts/offline_qa.py`
- `scripts/speckit_behavioral_qa.py`
- `scripts/speckit_offline_qa_handoff.py`
- `scripts/speckit_closeout_task.py`
- `scripts/codex_handoff_runner.py`
- `scripts/speckit_codex_handoff_runner.py`

Use these for post-edit verification, QA payload generation, and task closure.

## Best Entry Points

- "I need to validate an edit batch": `scripts/edit_code.py`
- "I need to understand the current feature/task state": `scripts/pipeline_ledger.py`, `scripts/task_ledger.py`
- "I need to understand why a Speckit step routed the way it did": `scripts/pipeline_driver.py`, `scripts/pipeline_driver_state.py`, `scripts/pipeline_driver_contracts.py`
- "I need to read code or markdown safely in this repo": `scripts/read_code.py`, `scripts/read_markdown.py`

## Related Docs

- `docs/architecture/workflow-overview.md`
- `docs/governance/pipeline-driver-readme.md`
- `docs/governance/speckit-end-to-end.md`

