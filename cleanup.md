# Cleanup Inventory

This is the current inventory of unused, legacy, or potentially obsolete workflow surfaces. Legacy does not always mean safe to delete; some legacy code remains a compatibility dependency.

## Explicitly Legacy Or Non-Canonical

- `/speckit.research`: research is folded into `/speckit.plan`.
- `/speckit.sketch`: design slices now belong in `plan.md`.
- `/speckit.solutionreview`: validates the obsolete sketch-first path.
- `/speckit.tasks`: deprecated upstream-compatible task generation; `/speckit.tasking` is canonical.
- `/speckit.solution`: compatibility alias; it is not the canonical tasking interface.
- `/speckit.breakdown`: compatibility substep; `/speckit.estimate` owns estimate, breakdown, re-estimation, and finalization.
- `scripts/speckit_tasking_chain.py`: deterministic chain no longer used by the canonical generative estimate step.
- `scripts/speckit_tasking_codex_runner.py`: old runner used by that deterministic chain.
- Per-task HUD workflow: separate HUD packets are no longer required; current tasks use `tasks.md`, `plan.md`, `spec.json`, and acceptance artifacts.
- `src/mcp_clickup/clickup_client.py`: legacy direct-token ClickUp client retained during transport retirement.
- Direct `src/mcp_clickup/__main__.py` publication: retired; live mutations are agent-owned Composio operations.
- The read-code MCP/stdio transport and legacy symbol-dump route: retired in favor of the in-process bounded reader/vector service.
- `.specify/command-manifest.yaml`: deprecated mirror that remains for governance compatibility.

## Legacy But Still Referenced

- `scripts/speckit_solution_step.py`: legacy implementation underneath `scripts/speckit_tasking_step.py`; not currently safe to delete.
- `scripts/speckit_tasking_chain.py` and its runner: still referenced by the compatibility `speckit.solution` manifest.
- `src/mcp_clickup/sync_engine.py`, `manifest.py`, and `artifact_parser.py`: the transport is retired, but mapping and reconciliation logic may still be reusable.
- HUD generators such as `scripts/speckit_remake_huds.py` and `scripts/speckit_fill_huds.py`: old artifact workflow, still referenced by historical specs and tests.
- `.github/workflows/codex-clickup-runner*.yml` and `codex-clickup-dispatch.yml`: manual or older ClickUp runner surfaces; external callers have not been proven absent.

## Legacy-Mode But Not Necessarily Unused

The manifest also marks these as `mode: legacy`, but they may still be valid optional or manual commands:

- `speckit.clarify`
- `speckit.split`
- `speckit.checklist`
- `speckit.feasibilityspike`
- `speckit.analyze`
- `speckit.closeout`
- `speckit.retro`
- `speckit.constitution`

## Suggested Cleanup Order

1. Remove obsolete command aliases after confirming no external callers.
2. Remove the deterministic tasking chain and runner.
3. Retire the HUD generators and old HUD artifact path.
4. Remove the direct ClickUp client after mapping logic is separated from transport.
5. Retire old ClickUp GitHub workflows after replacing or confirming their triggers.

This inventory is based on explicit repository workflow and architecture documentation, not a complete dead-code analysis.
