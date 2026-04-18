---
description: Prove all Open Feasibility Questions in plan.md with targeted probes before LLD begins. Auto-invoked by /speckit.plan after planreview; callable standalone.
handoffs:
  - label: Revise Plan (spike failed)
    agent: speckit.plan
    prompt: Feasibility spike failed — revise the architecture based on the evidence in spike.md
    send: false
  - label: Begin Solution Phase
    agent: speckit.solution
    prompt: All feasibility questions confirmed. Begin the solution phase.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Compact Contract (Load First)

Prove that the architecture committed to `plan.md` is actually buildable before any task breakdown or LLD begins.

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --paths-only` and parse `FEATURE_DIR` and `IMPL_PLAN`.
2. Read `## Open Feasibility Questions` in `plan.md`.
   - If no open questions remain, emit `feasibility_spike_completed` with `fq_count: 0` and exit.
3. For each open FQ, run a targeted probe.
4. Classify each result.
5. Write `spike.md`.
6. Branch on the result and either confirm the plan or route back to `/speckit.plan`.

## Expanded Guidance (Load On Demand)

### 1. Setup

Run `.specify/scripts/bash/check-prerequisites.sh --json --paths-only` from repo root. Parse `FEATURE_DIR` and `IMPL_PLAN`. Read `plan.md`.
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

### 2. Read Open Feasibility Questions

Locate `## Open Feasibility Questions` in `plan.md`.
   - If section is absent or contains only the placeholder comment: report "No open feasibility questions found. Plan is ready for /speckit.solution." Emit `feasibility_spike_completed` to `.speckit/pipeline-ledger.jsonl` with `fq_count: 0` and exit.
   - If all items are already checked `[x]`: same — report complete and exit.
   - Parse all unchecked `- [ ] **FQ-NNN**:` items. Extract: question text, Probe field, Blocking field.

### 3. For each open FQ — run a targeted probe

Determine probe type from the question and Probe field:
- **subprocess test**: Can a service execute a shell command? → `subprocess.run(["service-cli", "exec", "echo", "ok"], capture_output=True, timeout=60)`
 - **library import test**: Is a package importable at the right version? → `uv run python -c "import lib; assert lib.__version__ >= '2.1.0'"`
- **API call**: Does an endpoint respond as expected? → `httpx.get(url, timeout=30)`
- **service availability**: Is a local service reachable? → check port / ping process
- **code experiment**: Run a minimal script that exercises the specific capability in question

Rules:
- Max 60 seconds per probe. Kill and mark INCONCLUSIVE if exceeded.
- Capture stdout, stderr, and exit code.
- Do NOT assume a probe passes because it does not crash — verify the specific claim.

### 4. Classify each FQ result

- **CONFIRMED**: The probe demonstrates the capability works as the architecture assumes.
- **FAILED**: The probe demonstrates the capability does NOT work. Hard stop — do not continue to other FQs.
- **INCONCLUSIVE**: Probe timed out, service unavailable, or result is ambiguous. Ask human: "FQ-NNN could not be proven automatically: [reason]. Can you confirm this works, or should the architecture be revised?"

### 5. Write spike.md

Pre-scaffold the spike file from template:

1. Run: `uv run python .specify/scripts/pipeline-scaffold.py speckit.feasibilityspike --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
   - Pre-structures the file with Summary section, Probed Questions section, Technology Selection table, Failed Questions table, etc.
2. Fill in the scaffolded structure with every FQ: its probe, result, evidence snippet, and architecture implication — regardless of pass/fail.

### 6. Branch on overall result

   **If ALL confirmed**:
   - Update `plan.md ## Technology Selection`: fill in confirmed library/tool selections with evidence links (e.g., `"async IBKR connectivity: ib-async 2.1.0 — confirmed by FQ-001"`).
   - Mark each `- [ ] **FQ-NNN**` in plan.md as `- [x] **FQ-NNN**` with a `Confirmed: spike.md#FQ-NNN` annotation.
   - Emit `feasibility_spike_completed` to `.speckit/pipeline-ledger.jsonl`:
     ```json
     {"event": "feasibility_spike_completed", "feature_id": "NNN", "phase": "plan", "fq_count": N, "spike_artifact": "specs/NNN-feature/spike.md", "actor": "<agent-id>", "timestamp_utc": "..."}
     ```
   - Report: "All N feasibility questions confirmed. Technology Selection filled. Plan is ready for /speckit.solution."

   **If ANY failed**:
   - Do NOT update `## Technology Selection`.
   - Do NOT mark any FQ as `[x]`.
   - Emit `feasibility_spike_failed` to `.speckit/pipeline-ledger.jsonl` with `failed_fq` field naming the failed question.
   - **HARD BLOCK**: "Feasibility FAILED for [FQ-NNN]: [evidence summary]. The architecture assumes [capability] but the probe shows it is not available. Re-run /speckit.plan with this evidence and revise the architecture before proceeding."
   - Do NOT route to /speckit.solution.

   **If ANY inconclusive (and human confirms)**:
   - Treat as CONFIRMED for that FQ and proceed as above.
   - Note in spike.md: "FQ-NNN: human-confirmed (unautomated)."

   **If ANY inconclusive (and human denies or asks to revise)**:
   - Treat as FAILED.

## Behavior rules

- This command is **execution-only**: it proves or disproves claims. It does NOT redesign the architecture — that is /speckit.plan's responsibility.
- Probes must be targeted and minimal. Do not run full test suites.
- spike.md is always written, even on failure — it is the evidence record for the architecture revision.
- If called with no Open Feasibility Questions, exit cleanly — do not error.
