---
description: Generate solution sketches, test specifications, and acceptance test code for each task in tasks.md. Sub-agent of /speckit.solution; callable standalone.
handoffs:
  - label: Estimate Tasks
    agent: speckit.estimate
    prompt: Sketches are ready. Estimate fibonacci complexity for each task.
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Produce the LLD layer for each task: what to modify/create, how the pieces compose, and where to find existing solutions before writing new code. Also generates per-story acceptance test code (complete, runnable) and per-task test specifications (descriptions for the implement agent to write from). This is a sub-agent of `/speckit.solution` — it runs after `/speckit.tasking` produces tasks.md.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root. Parse `FEATURE_DIR`, `TASKS`. Read tasks.md, plan.md, research.md (if present), spike.md (if present), catalog.yaml.

2. **Load codebase context**:
   - For each task: use `mcp__codegraph__find_code` to resolve the `file:symbol` annotation from tasks.md to its current location.
   - For each resolved symbol: use `mcp__codegraph__analyze_code_relationships` (find_callers, find_callees) to understand the call graph around the change point.
   - Read only the source files directly touched by the current batch of tasks — do not read the full codebase.

3. **For each task — apply reuse-first decision tree (mandatory, stop at first match)**:

   1. Does `research.md ## Repo Assembly Map` have a repo/file covering this task? → Plan to adapt that code. Record: `source: owner/repo:path, adaptation: [what to change]`.
   2. Does `research.md ## Package Adoption Options` have a package covering this task? → Plan to install and call it. Record: `package: name==version, entry_point: [function/class to use]`.
   3. Does codegraph find an existing symbol in THIS codebase that covers this task? → Plan to reuse or extend it. Record: `reuse: file:symbol, extension: [what to add/change]`.
   4. Only if none of the above: plan to write net-new code. Record: `net_new: true, rationale: [why no reuse path exists]`.

   **Default bias check**: If the decision tree reaches step 4 for more than 50% of tasks, flag this as a warning — the reuse-first scan may be incomplete.

4. **For each task ≥ 3 points — generate a solution sketch**:

   Record in estimates.md (sketches section) and the task's HUD:
   - **Modify**: `file:symbol — [what changes and why]`
   - **Create**: `file — [new symbol name, signature, purpose]` (or "none")
   - **Reuse**: `[source from step 3 — or "net-new"]`
   - **Composition**: how the pieces wire together to satisfy the task goal
   - **Test specification**: describe the assertion and key edge cases in plain language — NOT runnable code (the implement agent writes the unit test code from this spec as their TDD forcing function)
   - **Domains touched**: list only the domain files from `.claude/domains/` that apply to this task's code. Include Domain 17 (Code Patterns) whenever the task creates or restructures any module or public symbol.

   For 1–2 point tasks: record `sketch: trivial` — no sketch required.

5. **For each user story — generate acceptance test code**:

   Acceptance tests are story-level contracts, not design decisions. The criteria are already defined in the spec's Independent Test Criteria for each story phase in tasks.md.

   - Read the Independent Test Criteria for the story from tasks.md
   - Write complete, runnable acceptance test code in Python (pytest) that asserts the observable story-level behavior
   - Place in `.speckit/acceptance-tests/story-N.py` (where N is the story number)
   - Tests must be runnable against real infrastructure — no mocks for external state boundaries
   - Tests must be deterministic PASS/FAIL oracles

   **Important**: These tests will FAIL until the story is implemented. During `/speckit.implement`, the agent confirms the pre-written test fails (RED), commits it, then implements (GREEN). The implement agent does NOT rewrite this test — it uses it as-is.

6. **Security review of reuse-first results (MANDATORY)**:

   For any task where the reuse-first path chose adapted external code (step 3.1 or 3.2):
   - Check adapted code against Domain 14 (Security Controls): no secrets hardcoded, no unvalidated external inputs passed through, no CVEs in the imported version
   - If a violation is found: either choose a different source, or record required sanitization steps that MUST be in the implementation
   - Record result in the task's HUD under `## Security Review`

7. **Generate HUD files**: For each task, pre-scaffold the HUD from the template:

   **For implementation tasks (code HUD)**:
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.sketch \
     TASK_ID=T0XX DESCRIPTION="[Task description]" \
     FEATURE_ID="[feature-id]"
   ```
   
   This copies `.specify/templates/hud-code-template.md` to `.speckit/tasks/T0XX.md` with:
   - Working Memory section (File:Symbol, Callers, Reuse path)
   - Solution Sketch (for 3+ point tasks) / "trivial" for 1–2 point tasks
   - Test Specification (plain-language, not runnable code)
   - Security Review
   - Functional Goal (Story Goal + Acceptance Criteria)
   - Quality Guards (domain rules for touched domains)
   - Process Checklist (all 5 standard items pre-populated)

   **For `[H]` human tasks (runbook HUD)**:
   ```bash
   uv run python .specify/scripts/pipeline-scaffold.py speckit.sketch \
     TASK_ID=T0XX DESCRIPTION="[Task description]" \
     FEATURE_ID="[feature-id]"
   ```

   This copies `.specify/templates/hud-runbook-template.md` to `.speckit/tasks/T0XX.md` with:
   - Runbook section (System, Steps, Verification command)
   - Functional Goal (Story Goal + Blocks)
   - Process Checklist (3 standard items pre-populated)

8. **Emit pipeline event**:
   ```json
   {"event": "sketch_completed", "feature_id": "NNN", "phase": "solution", "tasks_sketched": N, "acceptance_tests_written": N, "actor": "<agent-id>", "timestamp_utc": "..."}
   ```
   Append to `.speckit/pipeline-ledger.jsonl`.

9. **Report**: Sketches generated, acceptance tests written, reuse-first breakdown (adapted/package/reuse/net-new counts), security review results. Suggested next: `/speckit.estimate`.

## Behavior rules

- This command generates design artifacts — it does NOT write production code or test code into `src/` or `tests/`. Only `.speckit/` and `estimates.md` are written.
- Acceptance test code goes to `.speckit/acceptance-tests/` — NOT committed to `tests/` yet. Implement agent handles the RED commit.
- Unit test specifications are plain-language descriptions, NOT runnable code — do not write pytest assertions for unit tests.
- If tasks.md has changed since a prior sketch run: re-sketch only tasks whose `file:symbol` annotation changed or whose story phase changed. Skip unchanged tasks.
- HUDs are pre-computed — `/speckit.implement` reads one small file per task. Keep HUDs concise.
