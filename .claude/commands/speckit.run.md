# /speckit.run

## User Input

```text
$ARGUMENTS
```

## Compact Contract (Load First)

Treat this command as the canonical trigger for deterministic phase orchestration.

1. Resolve feature scope and the current allowed phase from ledger-authoritative state.
2. Evaluate deterministic gates for the requested phase before any mutation.
3. Execute phase routing through the pipeline driver contract only.
4. For generative routes, require runner-adapter execution and return a structured step result.
5. Validate artifacts and contracts before any completion event append.
6. Emit success event and next-step handoff only after validation succeeds.

## Expanded Guidance (Load On Demand)

- Keep this command as a trigger contract, not a procedure script.
- Route phase execution through `scripts/pipeline_driver.py` and manifest-owned driver metadata.
- Allow direct reruns for current/earlier phases; block forward progression beyond latest allowed phase.
- Keep event emission driver-owned and idempotent.
- Return deterministic blocked/error payloads with explicit reason codes when validation or routing fails.

## Behavior rules

- Do not bypass the driver for phase execution.
- Do not emit completion events before validation.
- Do not encode ledger append procedures in this command document.
