---
description: Decompose approved `sketch.md` into executable tasks, run estimate/breakdown subprocess loop, then generate HUDs and acceptance tests. Sub-agent of /speckit.solution; callable standalone.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Generate `tasks.md` from an approved sketch blueprint and finalize downstream execution artifacts in this order:

1. task decomposition,
2. estimate/breakdown subprocess loop,
3. deterministic format gate,
4. HUD generation,
5. acceptance-test generation.

This phase must consume `sketch.md` as an **authoritative design-to-tasking contract**, not as loose inspiration.

## Outline

### 1. Setup

Run:

```bash
.specify/scripts/bash/check-prerequisites.sh --json
```

Parse:

- `FEATURE_DIR`
- `AVAILABLE_DOCS`

### 2. Hard-block gate

Require:

- `FEATURE_DIR/sketch.md`
- a passing sketch review (`solutionreview_completed` with `critical_count == 0`)

If either condition fails, stop.

### 3. Load context

Required:

- `sketch.md`
- `spec.md`
- `plan.md`

Optional:

- `research.md`
- `catalog.yaml`
- `command-manifest.yaml`

When reading `sketch.md`, treat the following sections as authoritative inputs:

- `Solution Narrative`
- `Construction Strategy`
- `Acceptance Traceability`
- `Command / Script Surface Map`
- `Manifest Alignment Check`
- `CodeGraphContext Findings`
- `Blast Radius`
- `Interface, Symbol, and Contract Notes`
- `Human-Task and Operator Boundaries`
- `Verification Strategy`
- `Design-to-Tasking Contract`
- `Decomposition-Ready Design Slices`

### 4. Task derivation rules (mandatory)

Derive tasks from sketch using these rules:

#### A. Primary source of tasks
`Decomposition-Ready Design Slices` are the primary source of executable tasks.

Every design slice must produce at least one task unless an explicit omission rationale is recorded.

#### B. Ordering source
Task ordering must derive primarily from:

- `Construction Strategy`
- slice dependency relationships
- safety/validation sequencing implied by the sketch

Do not invent task order solely from convenience.

#### C. `[H]` task placement
`[H]` tasks must derive from:

- `Human-Task and Operator Boundaries`
- explicit external dependency constraints

Do not invent `[H]` tasks from vague prose.

#### D. `file:symbol` annotations
Task `file:symbol` annotations must derive from:

- touched files and touched symbols in design slices,
- symbol/interface notes in sketch,
- net-new file/symbol creation notes when applicable.

Do not invent unstable or line-number-based references.

#### E. Command/script/template/manifest work
If the sketch identifies necessary work against:

- commands,
- scripts,
- templates,
- manifest-owned artifacts,
- event flows,

those must become explicit tasks when they are part of the approved design.

Additionally, any command/script/template/manifest/event **deltas** listed in `Manifest Alignment Check` MUST map to one or more concrete tasks, or an explicit rationale for omission.

#### F. Scope control
No task may introduce:

- a new seam,
- a new interface,
- a new artifact,
- a new symbol family,
- a new runtime surface,

unless the sketch explicitly allows it or an explicit rationale is recorded.

### 5. Generate `tasks.md`

Pre-scaffold:

```bash
uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking --feature-dir "$FEATURE_DIR" FEATURE_NAME="[Feature Name]"
```

Then fill tasks from the sketch contract with:

- phase/story grouping,
- dependency ordering,
- `[H]` task placement,
- `[P]` only where true parallelism exists,
- `file:symbol` annotations,
- command/script/template/manifest tasks where required,
- verification-oriented tasks where the sketch requires them.

### 6. Task format rules

Every task MUST follow:

`- [ ] TNNN [P?] [H?] [USN?] Description — file:symbol`

Rules:

- `[P]` only if parallelizable with no incomplete dependencies
- `[H]` only if external human action is required; mutually exclusive with `[P]`
- `[USN]` required in user-story phases
- `file:symbol` required unless net-new file has no symbol yet

### 7. Estimate/breakdown subprocess loop (mandatory)

- Invoke `/speckit.estimate` against current `tasks.md`
- If any task scores 8/13, invoke `/speckit.breakdown`, then re-run estimate
- Repeat until no 8/13 tasks remain
- Emit **one aggregated** `estimation_completed` event for the final settled task set

### 8. Deterministic tasks format gate (mandatory)

Run:

```bash
      uv run python scripts/speckit_tasks_gate.py validate-format --tasks-file "$FEATURE_DIR/tasks.md" --json
```

If non-zero exit, fix and re-run before continuing.

### 9. Generate HUDs only after tasks are stable

**Code task HUD**
```bash
uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking.hud-code \
  TASK_ID=T0XX DESCRIPTION="[Task description]" FEATURE_ID="[feature-id]"
```

**Human task HUD**
```bash
uv run python .specify/scripts/pipeline-scaffold.py speckit.tasking.hud-runbook \
  TASK_ID=T0XX DESCRIPTION="[Task description]" FEATURE_ID="[feature-id]"
```

### 10. Generate acceptance tests

For each story, write `.speckit/acceptance-tests/story-N.py` from:

- Independent Test Criteria in `tasks.md`
- verification intent preserved from sketch
- acceptance traceability preserved from sketch

Tests must be deterministic PASS/FAIL oracles.

### 11. Emit pipeline event

Append:

```json
{"event": "tasking_completed", "feature_id": "NNN", "phase": "solution", "task_count": N, "story_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
```

to `.speckit/pipeline-ledger.jsonl`.

### 12. Report

Report:

- path to `tasks.md`
- settled estimate summary
- HUD count and acceptance-test count
- whether command/script/template/manifest work was included as tasks
- whether `[H]` tasks were derived from explicit sketch boundaries
- suggested next: `/speckit.analyze`

## Behavior rules

- Do not create HUDs before estimate/breakdown stabilization.
- Do not skip deterministic format validation.
- Do not mutate `sketch.md`; treat it as input contract.
- Do not let tasking invent major architecture absent from sketch.
- Preserve the construction strategy and safety invariants of the sketch when decomposing.
