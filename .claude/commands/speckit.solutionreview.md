---
description: Cross-sketch quality review after tasking/sketch/estimate converge — domain compliance, DRY analysis, acceptance test review, and optimization scan. Sub-agent of /speckit.solution; callable standalone.
handoffs:
  - label: Begin Implementation
    agent: speckit.implement
    prompt: Solution review complete. Begin implementation.
    send: false
  - label: Revise Sketches (critical findings)
    agent: speckit.sketch
    prompt: Solution review found CRITICAL domain violations. Revise sketches and re-run.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Purpose

Quality gate for the solution layer before implementation begins. Reviews sketches for domain rule compliance (security always included), finds cross-task DRY opportunities, validates acceptance tests against Domain 12, and surfaces optimization suggestions. Does NOT modify sketches or tasks automatically — all findings are reported for human review. CRITICAL findings must be resolved before `/speckit.implement` may proceed.

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root. Parse `FEATURE_DIR`, `TASKS`. Read tasks.md, estimates.md, all HUDs in `.speckit/tasks/`, all acceptance tests in `.speckit/acceptance-tests/`.

2. **Gate check**: Verify estimates.md exists with solution sketches. If missing or no sketches present: **STOP** — "No solution sketches found. Run /speckit.sketch first."

3. **Domain compliance check (sketch level)**:

   For each task with a sketch in estimates.md:
   - Identify touched domains (from the "Domains touched" field in each sketch)
   - **Always add**: Domain 13 (Identity), Domain 14 (Security Controls), and Domain 17 (Code Patterns) — these are evaluated for every task regardless of domain tags
   - Read ONLY the identified domain files from `.claude/domains/`
   - For each domain rule, check whether the solution sketch (modify/create/composition) would violate it
   - This is distinct from planreview's domain check (architecture level) — this checks "will the code we're about to write follow the rules?"

   Severity assignment:
   - **CRITICAL**: Sketch proposes code that directly violates a MUST rule (e.g., secrets hardcoded, sync wrapper in async path, no transaction boundary on financial write)
   - **HIGH**: Sketch omits a required pattern (e.g., no error handling for external input, no lifecycle shutdown for spawned task)
   - **MEDIUM**: Sketch follows a less-preferred pattern where a better one exists
   - **LOW**: Style or minor convention deviation

   CRITICAL findings **block** `/speckit.solution` completion. The relevant sketches must be revised via `/speckit.sketch` before `solution_approved` can be emitted.

4. **External code security review**:

   For each task where the HUD's reuse path is "adapted external code" (from `research.md ## Repo Assembly Map` or a package):
   - Apply Domain 14 checks: no secrets in the adapted code, no unvalidated external inputs passed through, no known CVEs in the package version
   - Check that the HUD's `## Security Review` section documents the result
   - If `## Security Review` is missing or blank for an external-code task: flag as HIGH
   - If a CVE or secret is present in the adapted code and not addressed: flag as CRITICAL

5. **Cross-task DRY analysis**:

   Scan all sketches for repeated patterns:
   - Same utility function described in multiple sketches (e.g., HTTP retry, pagination helper, schema validator)
   - Same composition pattern across multiple tasks (e.g., always wrapping the same external call)
   - Same error handling boilerplate in multiple places

   For each detected duplication:
   - Identify the tasks affected
   - Propose a consolidation: shared utility file path, symbol name, which tasks should call it
   - Estimate the point reduction if consolidated (affects estimate accuracy)

   These suggestions are NOT auto-applied. Present to human for approval. If approved, `/speckit.sketch` must be re-run for affected tasks, then `/speckit.estimate` re-run for updated scores.

6. **Acceptance test compliance review (Domain 12)**:

   For each acceptance test in `.speckit/acceptance-tests/`:
   - Is there a deterministic PASS/FAIL oracle? (not "check logs manually")
   - Does the test run against real infrastructure, not mocks, for external state boundaries?
   - Is the test scoped to the story's observable behavior (not implementation internals)?
   - Does it cover the key acceptance criteria from tasks.md Independent Test Criteria?

   Flag non-compliant tests as HIGH. If a story has no acceptance test file: flag as CRITICAL.

7. **Optimization scan**:

   Look across all sketches for a simpler overall path:
   - Two tasks that could be collapsed without losing Independent Test Criteria coverage
   - A pattern from one sketch that makes another task trivially simpler (saves 2+ points)
   - A shared abstraction that reduces net-new code across 3+ tasks

   Present findings only — not auto-applied. Each suggestion must state: tasks affected, proposed change, estimated point savings.

8. **Write solutionreview.md**: Pre-scaffold the review file from template:

   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.solutionreview --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
      - Pre-structures the file with section headings for Domain Compliance Review, DRY Analysis, Acceptance Test Review, Optimization Scan, Findings Summary, etc.

   2. Fill all sections. If a section has no findings, state "None identified."

9. **Branch on outcome**:

   **If NO CRITICAL findings**:
   - Emit `solutionreview_completed` to `.speckit/pipeline-ledger.jsonl`:
     ```json
     {"event": "solutionreview_completed", "feature_id": "NNN", "phase": "solution", "critical_count": 0, "high_count": N, "actor": "<agent-id>", "timestamp_utc": "..."}
     ```
   - Report: "Solution review PASS. N high-severity findings to review before implement. solutionreview.md written."

   **If ANY CRITICAL findings**:
   - Emit `solutionreview_completed` with `critical_count > 0`.
   - **HARD BLOCK**: "Solution review FAILED — N CRITICAL findings must be resolved. Re-run /speckit.sketch for tasks: [list]. Then re-run /speckit.solutionreview."
   - Do NOT emit `solution_approved`.

10. **Report**: Domain compliance table, external code findings, DRY suggestions, acceptance test results, optimization suggestions. Remind: DRY consolidations and optimizations require human approval before sketches are revised.

## Behavior rules

- Read-only on all inputs except writing solutionreview.md
- Does NOT modify estimates.md, HUDs, tasks.md, or acceptance tests
- DRY and optimization findings are suggestions — never auto-apply
- CRITICAL domain violations block `solution_approved`; HIGH and below do not block but must appear in the report
- If called before `/speckit.estimate` has run: warn that estimates may change after DRY consolidations and re-run will be needed
