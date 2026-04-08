---
description: Execute the implementation plan by processing and executing all tasks defined in tasks.md
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

1a. **E2E artifacts gate (MANDATORY — hard block)**:
   - Check whether `FEATURE_DIR/e2e.md` exists.
   - Check whether a matching E2E script exists under `scripts/` (e.g. `scripts/e2e_<feature-slug>.sh`).
   - **If either artifact is missing**: **STOP immediately** with this message:

     > **E2E artifacts are missing. `/speckit.implement` cannot proceed.**
     > Run `/speckit.e2e` to generate `e2e.md` and the E2E script, then re-run `/speckit.implement`.
     > This is a non-negotiable pre-implementation gate per the project constitution (Canonical Workflow Pipeline rule: "Never skip `/speckit.e2e` before `/speckit.implement`").

   - Do **not** continue to any subsequent step. Do **not** ask the user if they want to proceed anyway.
   - **If both artifacts exist**: confirm their presence with a single line (e.g. `✅ E2E artifacts found: FEATURE_DIR/e2e.md`) and continue to step 1b.

1b. **Estimation artifact gate (MANDATORY — hard block)**:
   - Check whether `FEATURE_DIR/estimates.md` exists.
   - **If missing**: **STOP immediately** with this message:

     > **Estimation artifacts are missing. `/speckit.implement` cannot proceed.**
     > Run `/speckit.estimate` (or re-run `/speckit.solution`, which invokes estimation) to generate `estimates.md`, then re-run `/speckit.implement`.
     > This is a non-negotiable pre-implementation gate.

   - Do **not** continue to any subsequent step. Do **not** ask the user if they want to proceed anyway.
   - **If present**: confirm its presence with a single line (e.g. `✅ Estimation artifacts found: FEATURE_DIR/estimates.md`) and continue to step 2.

2. **Check checklists status** (if FEATURE_DIR/checklists/ exists):
   - Scan all checklist files in the checklists/ directory
   - For each checklist, count:
     - Total items: All lines matching `- [ ]` or `- [X]` or `- [x]`
     - Completed items: Lines matching `- [X]` or `- [x]`
     - Incomplete items: Lines matching `- [ ]`
   - Create a status table:

     ```text
     | Checklist | Total | Completed | Incomplete | Status |
     |-----------|-------|-----------|------------|--------|
     | ux.md     | 12    | 12        | 0          | ✓ PASS |
     | test.md   | 8     | 5         | 3          | ✗ FAIL |
     | security.md | 6   | 6         | 0          | ✓ PASS |
     ```

   - Calculate overall status:
     - **PASS**: All checklists have 0 incomplete items
     - **FAIL**: One or more checklists have incomplete items

   - **If any checklist is incomplete**:
     - Display the table with incomplete item counts
     - **STOP** and ask: "Some checklists are incomplete. Do you want to proceed with implementation anyway? (yes/no)"
     - Wait for user response before continuing
     - If user says "no" or "wait" or "stop", halt execution
     - If user says "yes" or "proceed" or "continue", proceed to step 3

   - **If all checklists are complete**:
     - Display the table showing all checklists passed
     - Automatically proceed to step 3

3. Load and analyze the implementation context:
   - **REQUIRED**: Read tasks.md for the complete task list and execution plan
   - **REQUIRED**: Read plan.md for tech stack, architecture, and file structure
   - **IF EXISTS**: Read data-model.md for entities and relationships
   - **IF EXISTS**: Read contracts/ for API specifications and test requirements
   - **IF EXISTS**: Read research.md for technical decisions and constraints
   - **IF EXISTS**: Read quickstart.md for integration scenarios

4. **Project Setup Verification**:
   - **REQUIRED**: Create/verify ignore files based on actual project setup:

   **Detection & Creation Logic**:
   - Check if the following command succeeds to determine if the repository is a git repo (create/verify .gitignore if so):

     ```sh
     git rev-parse --git-dir 2>/dev/null
     ```

   - Check if Dockerfile* exists or Docker in plan.md → create/verify .dockerignore
   - Check if .eslintrc* exists → create/verify .eslintignore
   - Check if eslint.config.* exists → ensure the config's `ignores` entries cover required patterns
   - Check if .prettierrc* exists → create/verify .prettierignore
   - Check if .npmrc or package.json exists → create/verify .npmignore (if publishing)
   - Check if terraform files (*.tf) exist → create/verify .terraformignore
   - Check if .helmignore needed (helm charts present) → create/verify .helmignore

   **If ignore file already exists**: Verify it contains essential patterns, append missing critical patterns only
   **If ignore file missing**: Create with full pattern set for detected technology

   **Common Patterns by Technology** (from plan.md tech stack):
   - **Node.js/JavaScript/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
   - **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
   - **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
   - **C#/.NET**: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`
   - **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`
   - **Ruby**: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`
   - **PHP**: `vendor/`, `*.log`, `*.cache`, `*.env`
   - **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`
   - **Kotlin**: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`
   - **C++**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`
   - **C**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `autom4te.cache/`, `config.status`, `config.log`, `.idea/`, `*.log`, `.env*`
   - **Swift**: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`
   - **R**: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`
   - **Universal**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`

   **Tool-Specific Patterns**:
   - **Docker**: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`
   - **ESLint**: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`
   - **Prettier**: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
   - **Terraform**: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`
   - **Kubernetes/k8s**: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`

5. Parse tasks.md structure and extract:
   - **Task phases**: Setup, Tests, Core, Integration, Polish
   - **Task dependencies**: Sequential vs parallel execution rules
   - **Task details**: ID, description, file paths, parallel markers [P]
   - **Acceptance Criteria**: Extract "Story Goal" and "Independent Test Criteria" for the phase containing the current task.
   - **Execution flow**: Order and dependency requirements

5.5 **Task Scaffolding & Discovery Gate (MANDATORY before coding each task)**:
   1. **Read HUD**: Load `.speckit/tasks/T0XX.md` — pre-computed by `speckit.estimate`. Contains working memory, solution sketch, functional goal, quality guards, and process checklist. If missing: **STOP** — run `/speckit.estimate` to regenerate HUDs.

   2. **Sketch validity check (3+ point tasks only)**: Verify the solution sketch in the HUD is still valid:
      - Run `mcp__codegraph__find_code` for each symbol named in the sketch.
      - If a symbol no longer exists or has moved: **STOP** — route to `/speckit.tasking` (re-annotate) or `/speckit.plan` (architecture changed).
      - If the sketch's approach contradicts what earlier tasks built: **STOP** — route to `/speckit.plan`.
      - Do NOT adapt the sketch on the fly. `speckit.implement` is an execution engine, not a design engine.

   3. **Scope Containment Guard (MANDATORY — hard block)**: Before writing any code, verify that everything this task is about to introduce is already covered by the current spec artifacts. For each item the task will create or modify, check:
      - **New HTTP endpoint** → must appear in `contracts/` with method, path, auth, and request/response contract
      - **New env var or config key** → must be named in a spec FR or data-model.md
      - **New auth mechanism or token** → must be named in a spec FR or a contracts/ security section
      - **New inter-service call or callback pattern** → must appear as a labeled edge in the Architecture Flow diagram in plan.md
      - **New schema or data model entity** → must appear in data-model.md
      - **New dependency** → must appear in plan.md Technical Context

      If **any** introduced item is not covered:
      - **STOP immediately** — do not write any code for this task
      - Report exactly what is unspecified: name the item and which artifact it is missing from
      - Direct the user to the correct upstream command:
        - Missing FR or behavioral requirement → `/speckit.clarify` or `/speckit.specify`
        - Missing Architecture Flow edge or component → `/speckit.plan`
        - Missing contract or data-model entity → `/speckit.plan`

   4. **Log Discovery**: Append `discovery_completed` to the task ledger. Append `lld_recorded` only for 3+ point tasks where sketch validity passed.

6. Execute implementation following the task plan:
   - **Codebase MCP tools (use when connected)** — see CLAUDE.md `### Codebase MCP Toolkit` for the current list of available servers and their tools. You MUST use `codegraph` first for discovery/scope (find symbols, callers/callees, imports, and impact scope) before writing. You MUST use `get_type`/`get_diagnostics` (codebase-lsp, if connected) second to verify exact types/diagnostics before edits and after edits in touched files. Do not mark a task `[X]` while known type errors remain in files the task owns.
   - **Phase-by-phase execution**: Complete each phase before moving to the next
   - **Per-story RED step (MANDATORY at the start of each User Story phase — before any task code)**:
     1. Write the failing story-level acceptance test derived from the "Independent Test Criteria" in tasks.md for this story. This is a pytest case (or equivalent) targeting the story's observable outcome — not a unit test.
     2. Run it. It MUST fail. If it passes before any implementation: **STOP** — the test is not testing the right thing or the story is already implemented. Investigate before proceeding.
     3. Commit the failing test: `T0XX-story-N-red: failing acceptance test for [story goal]`
     4. All `[H]` human tasks for this story MUST be completed and verified before the task loop begins (GREEN phase). The acceptance test can be written before `[H]` tasks exist — it will fail regardless. But no implementation task may start until all `[H]` tasks for this story are closed.
   - **Respect dependencies**: Run tasks in strict listed order
   - **Parallel execution (MANDATORY)**: Even tasks marked `[P]` MUST run with standard process (single commits etc) for full 1:1 traceability
   - **Follow TDD approach**: Execute test tasks before their corresponding implementation tasks
   - **File-based coordination**: Tasks affecting the same files must run sequentially
   - **Task checkmark timing (MANDATORY)**: Keep a task `[ ]` until `task_closed` is appended in the ledger. Only then mark the task `[X]` in tasks.md. Do NOT pre-mark completed work before offline QA closes the task.
   - **`[H]` human task execution**: `[H]` tasks run in parallel with implementation tasks for the same story — they do NOT block code tasks from starting. However, no implementation task that depends on the `[H]` result (e.g., requires the webhook URL to exist) may proceed until `human_action_verified` is logged. The story phase as a whole cannot close until all `[H]` tasks are `task_closed`.
     1. Read the task's runbook HUD at `.speckit/tasks/T0XX.md`.
     2. Present the runbook to the human; they complete it asynchronously.
     3. When the human signals completion, run the verification command from the HUD. If it fails: **STOP** — do not unblock dependent implementation tasks until it passes.
     4. Append `human_action_started`, `human_action_verified`, `task_closed` to the task ledger and mark `[X]` in tasks.md.
   - **Task ledger logging (MANDATORY)**: Log every transition to `.speckit/task-ledger.jsonl` via `python scripts/task_ledger.py append ...` using immutable events:
     - `task_started`
     - `discovery_completed` (Phase 1: Recon)
     - `lld_recorded` (3+ point tasks only)
     - `quality_guards_passed` (Phase 2: Domain/Engineering compliance)
     - `functional_goal_achieved` (Phase 3: Acceptance criteria met)
     - `tests_failed` / `tests_passed`
     - `human_action_started` / `human_action_verified` (`[H]` tasks only)
     - `offline_qa_started`
     - `offline_qa_passed` / `offline_qa_failed`
     - `fix_started` / `fix_completed` (if offline QA fails)
     - `commit_created`
     - `task_closed`
   - **Start gate (MANDATORY before coding each task)**: Run
     `python scripts/task_ledger.py assert-can-start --file .speckit/task-ledger.jsonl --tasks-file FEATURE_DIR/tasks.md --feature-id NNN --task-id T0XX --actor <agent-id>`
     and do not proceed if it fails.
   - **Per-task validation by category** — every task MUST be validated before entering offline QA handoff:
     - **Pure logic tasks** (rules, scoring, filters, CRUD, formulas): Unit tests ARE sufficient. Run the relevant tests; if they pass, the task is done.
     - **Module/wiring tasks** (imports, assembly, CLI skeleton): Smoke-test the import or entrypoint (e.g., `python -c "from module import Class"`, `uv run <entrypoint> --help`). A task that crashes on import is NOT complete.
     - **External integration tasks** (anything that calls an external service — IBKR API, database, HTTP, file I/O): Unit tests are NOT sufficient because they mock the external boundary. You MUST actually call the real service and verify a meaningful response. For example:
       - IBKR connect task → actually connect to Gateway and confirm `ibkr_connected` log
       - Option chain task → actually call `reqSecDefOptParams` and verify contracts are returned
       - Database task → actually run migrations and verify tables exist
       - Logging-path task → actually run the entrypoint and confirm startup exposes `run_id` + active `log_path`, and the latest-run pointer resolves to a real log file
       - **State safety and reconciliation guard (mandatory when local state mirrors live external state):**
         - Define the source of truth for each lifecycle field and verify reconcile executes before decision paths.
         - Do not emit log-only state transitions; persisted lifecycle updates MUST occur in the same flow.
         - Add or run at least one regression test for stale/orphan state (live missing/closed vs local active).
         - If source-of-truth drift remains unresolved after reconciliation, task validation FAILS.
       - **Local DB transaction integrity guard (mandatory when local DB mutations represent lifecycle/risk/financial state):**
         - Use explicit transaction boundaries for multi-step writes; cross-table updates MUST commit or roll back atomically.
         - Do not treat intent creation as terminal state completion; lifecycle state changes MUST reflect true execution state.
         - Add or run at least one regression test proving rollback/no-partial-write behavior on failure.
         - If impossible/partial local lifecycle states persist after a failed mutation path, task validation FAILS.
       - **Async process management guard (mandatory when asyncio/event loops are involved):**
         - Do not invoke sync wrappers that run or block event loops from inside active async code paths (for example sync IBKR request methods).
         - Use native async APIs with explicit `await`, and ensure spawned tasks/processes have explicit lifecycle handling (start, timeout/cancel, shutdown).
         - Add or run at least one regression test that executes the integration path while an event loop is already running to catch `"event loop is already running"` failures.
       - **Observability logging guard (mandatory when runtime logging semantics change):**
         - Keep runtime logs structured and machine-parseable for operational events (timestamp/level/event stable keys).
         - Verify run-scoped logging and latest-run pointer behavior with a real process run.
         - If startup does not emit active `run_id` + `log_path`, task validation FAILS.
       - If the external service is unavailable, **STOP and ask the human** to set it up. Do NOT mark the task `[X]` without live validation. Do NOT assume it works because the mock-based unit tests pass.

   **Per-task commit + Offline QA handoff (MANDATORY before marking `[X]`)**:

   After a task is validated (while still `[ ]`), **immediately commit locally** and run a separate offline QA process:
   1. Stage all files changed by this task (review the diff — never stage secrets or unrelated changes).
   2. Keep tasks.md unchanged in this commit (task remains `[ ]` until closure).
   3. Commit message format:
      ```
      T0XX <short task description>

      <what changed and why, 1-3 lines>

      ```
   4. Append `commit_created` event to the task ledger.
   5. Append `offline_qa_started`, then launch a **separate QA agent/process** dedicated to this task.
   6. Build a handoff payload JSON at `.speckit/offline-qa/<feature_id>_<task_id>_attempt_<n>.handoff.json` and run:
      `.venv/bin/python scripts/offline_qa.py --payload-file <handoff.json> --result-file .speckit/offline-qa/<feature_id>_<task_id>_attempt_<n>.result.json`
      If using `uv run` instead, prefer `UV_NO_CACHE=1 uv run python ...` when startup is slow due cache churn.
   7. Required handoff payload to QA agent/process:
      - `feature_id` and `task_id` (non-empty strings)
      - `hud_path` (Path to .speckit/tasks/T0XX.md containing ACs and Quality Guards)
      - `acceptance_criteria` (Extracted list from HUD)
      - `quality_guards` (Extracted list from HUD)
      - `changed_files` (non-empty string list)
      - `diff` (non-empty unified diff string)
      - `test_runs` (non-empty list of objects with `command` string, `exit_code` int, optional `output` string)
      - `known_risks` (optional string list)
      - Legacy `test_commands` is accepted for backward compatibility and normalized to `test_runs` with a warning.
   8. QA agent/process returns explicit verdict from result JSON:
      - `PASS` => append `offline_qa_passed` (with `qa_run_id`), then append `task_closed`, then update tasks.md to `[X]` and create a follow-up closure commit containing only the tasks.md checkmark and ledger event lines.
      - `FIX_REQUIRED` => append `offline_qa_failed` (with `qa_run_id`), append `fix_started`, implement fixes, append `fix_completed`, then re-run offline QA handoff for the same task.
      - Runner exit code is `0` on `PASS` and `1` on `FIX_REQUIRED`; treat non-zero as a blocked gate until fixed.
   9. **Lifecycle requirement**: QA agent/process MUST be explicitly opened for the task handoff and explicitly closed after verdict (no long-lived shared QA process across tasks).
   10. **Hard block (per-agent)**: Do NOT start another task for the same agent until its current task has `task_closed` in the ledger. Different agents may start `[P]` tasks in parallel when `assert-can-start` passes.
   11. **CodeGraph refresh (MANDATORY after task_closed)**: Run `scripts/cgc_safe_index.sh <files changed by this task>` scoped to only the files modified. This keeps symbol resolution current for subsequent tasks' CodeGraph Recon step. Do NOT run a full repo re-index.

   **Per-phase push + CI QA gate (MANDATORY)**:
   - Task commits remain local until the phase is complete and checkpoint layers pass.
   - After phase completion, push the phase branch, open/update a single phase PR, and run CI + Codex QA gate there.
   - Merge happens at the **phase checkpoint**, not per-task.

   **Phase checkpoint gate (MANDATORY — three layers)**:

   After all tasks in a phase are complete, validate the checkpoint described in the `**Checkpoint**:` line at the end of that phase in tasks.md. The checkpoint describes **observable behavior** that MUST be true before the next phase begins. It is a **gate, not documentation**.

   **Layer 1 — inline validation (do this immediately after completing the last task):**
   1. **Parse the checkpoint text** — it states what the system should do after this phase.
   2. **Run the software** — execute the application (with `--dry-run` or equivalent safe mode if available) and verify the checkpoint behaviors actually occur. Check logs, terminal output, or database state as evidence.
   3. **If external dependencies are required** that are not available: **STOP and ask the human** to set them up or confirm they are running. Do not skip the checkpoint.
   4. **State safety gate** (for live-vs-local state integrations): verify no unresolved source-of-truth drift leaves local records in active states.
   5. **Local DB transaction integrity gate** (for local persisted-state mutation paths): verify no partial writes or impossible lifecycle transitions remain after failure/retry paths.
   6. **Observability gate** (for logging/runtime visibility changes): verify startup emits `run_id` + active log path and that the active latest-run pointer resolves to a real log file with expected events after phase start.
   7. **If the checkpoint fails** — diagnose, fix, and re-run.
   8. **If the checkpoint passes** — proceed to Layer 2.

   **Layer 2 — `/speckit.checkpoint` (independent second pass):**
   After Layer 1 passes, invoke `/speckit.checkpoint Phase [N]` as a separate validation step. This catches mistakes that Layer 1 missed (e.g., the implementation agent believing its own work passed when it didn't).
   - **If checkpoint returns PASS**: Proceed to Layer 3 (if applicable) or the next phase.
   - **If checkpoint returns FAIL**: The phase is NOT complete. Fix the failures, then re-run both layers.
   - **If checkpoint requires human intervention**: Wait for the human to confirm before proceeding.

   **Layer 3 — `/speckit.e2e-run` (E2E validation for user story phases):**
   After Layer 2 passes on a **user story phase** (Phase 3+), invoke `/speckit.e2e-run [USn]` to run the E2E section for that story. This validates the story works end-to-end with real infrastructure, not just in isolation.
   - **Prerequisite**: `FEATURE_DIR/e2e.md` and a corresponding `scripts/e2e_*.sh` must exist. If they do not, run `/speckit.e2e` first; the phase is blocked until E2E artifacts exist.
   - **If E2E returns PASS**: Proceed to the next phase.
   - **If E2E returns FAIL/BLOCKED/SKIPPED**: The phase is NOT complete. Report failures, fix root causes, and re-run until PASS.
   - **Setup and Foundational phases** (Phases 1-2) do NOT require Layer 3 — they are validated by Layers 1-2 only.
   - **Preflight shortcut**: `/speckit.e2e-run preflight` is diagnostic only; it does not satisfy the story E2E acceptance gate.

   Unit tests passing is NECESSARY but NOT SUFFICIENT for a phase checkpoint. Unit tests validate components in isolation; checkpoints validate that components are wired together and the system behaves as specified end-to-end.

7. Implementation execution rules:
   - **Setup first**: Initialize project structure, dependencies, configuration
   - **Tests before code**: If you need to write tests for contracts, entities, and integration scenarios
   - **Core development**: Implement models, services, CLI commands, endpoints
   - **Integration work**: Database connections, middleware, logging, external services
   - **Polish and validation**: Unit tests, performance optimization, documentation

8. Progress tracking and error handling:
   - Report progress after each completed task
   - Mark each task `[X]` in tasks.md only after `task_closed` is appended for that task (see step 6)
   - Halt execution when the current task fails validation, CI, or QA gate
   - Enforce per-agent serialization (one open task per agent). Allow parallel execution across different agents for tasks marked `[P]` when `assert-can-start` passes and file ownership does not overlap.
   - Provide clear error messages with context for debugging
   - Suggest next steps if implementation cannot proceed

9. Completion validation:
   - Verify all required tasks are completed
   - Check that implemented features match the original specification
   - Validate that tests pass and coverage meets requirements
   - For logging/runtime visibility changes, validate run-scoped logs and latest-run pointer behavior from a real run and report the resolved active log path in the final summary
   - **Final E2E gate**: If `FEATURE_DIR/e2e.md` and a corresponding `scripts/e2e_*.sh` exist, invoke `/speckit.e2e-run full` to run the complete E2E pipeline:
     - This runs all sections: preflight → per-story → final full-feature
     - If external dependencies are unavailable, final completion is BLOCKED until dependencies are available and full E2E can run
     - Completion requires `/speckit.e2e-run full` to return PASS (no skip/blocked/fail)
   - Confirm the implementation follows the technical plan
   - Report final status with summary of completed work, including E2E results

10. **Retrospective: Estimate vs Actual** (if FEATURE_DIR/estimates.md exists):
    - For each completed task, assess actual complexity relative to the fibonacci estimate:
      - **Accurate**: Actual effort matched the estimate (within +-1 fibonacci step)
      - **Underestimated**: Actual effort exceeded the estimate by 2+ fibonacci steps — note why
      - **Overestimated**: Actual effort was less than estimated by 2+ fibonacci steps — note why
    - Append a `## Retrospective` section to estimates.md:

      ```markdown
      ## Retrospective

      **Date**: [DATE] | **Estimated Total**: [ORIG_SUM] | **Adjusted Total**: [ACTUAL_SUM]
      **Accuracy**: [ACCURATE_COUNT]/[TOTAL_COUNT] tasks within +-1 step

      | Task ID | Estimated | Actual | Delta | Notes |
      |---------|-----------|--------|-------|-------|
      | T001 | 2 | 2 | 0 | As expected |
      | T005 | 3 | 5 | +2 | Trello API pagination undocumented |
      | ... | ... | ... | ... | ... |

      ### Calibration Insights
      - [Pattern observations: e.g., "Integration tasks consistently underestimated by 1 step"]
      - [Codebase insights: e.g., "Existing parser patterns reduced greenfield effort"]
      ```

    - If no estimates.md exists, skip this step silently (estimation was not run for this feature)

Note: This command assumes a complete task breakdown exists in tasks.md. If tasks are incomplete or missing, suggest running `/speckit.solution` first to regenerate the task list.
