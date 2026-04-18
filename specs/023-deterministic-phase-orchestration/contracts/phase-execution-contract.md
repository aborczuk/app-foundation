# Contract: Phase Execution and Validate-Before-Emit

This contract defines the planning-level execution boundary for driver-managed phase flow.

---

## Scope

- Feature: `023-deterministic-phase-orchestration`
- Execution entrypoint: `scripts/pipeline_driver.py`
- Event append path: `scripts/pipeline_ledger.py append`
- Registry source of truth: `command-manifest.yaml`

---

## Execution Sequence Contract

All automated phase runs must preserve this ordered sequence:

1. `orchestrate`
2. `extract`
3. `scaffold`
4. `LLM Action`
5. `validate`
6. `emit/handoff`

If any step before `emit/handoff` fails, completion event append is forbidden.

---

## Step Result Envelope Contract

Required top-level fields:

- `schema_version`
- `ok`
- `exit_code` (`0|1|2`)
- `correlation_id`

Conditional requirements:

- `exit_code=0` requires `next_phase`
- `exit_code=1` requires `gate` + non-empty `reasons`
- `exit_code=2` requires `error_code` + `debug_path`

Envelope is invalid if correlation id mismatches request context.

---

## Event Emission Contract

- Completion event name is sourced from `command-manifest.yaml` for the executed command.
- Event append is allowed only when deterministic validation passes.
- On validation failure, blocked result, timeout, or append failure:
  - no completion event is emitted
  - step result must remain non-success
  - debug/error information must be preserved for rerun

---

## Ownership Contract

- Commands/templates own artifact synthesis intent and required output structure.
- Deterministic scripts own gating, validation, and ledger append mechanics.
- Ledger state is authoritative for phase progression.

---

## Downstream Reliance

Downstream phases may assume:

- emitted completion event implies validation pass
- missing completion event implies phase not complete
- handoff payloads are eligible for consumption only after successful emit path
