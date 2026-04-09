---
description: Execute the implementation planning workflow. Produces plan.md then auto-invokes planreview and feasibilityspike as sub-processes. Plan phase is not complete until both finish.
model: opus
handoffs:
  - label: Create Checklist
    agent: speckit.checklist
    prompt: Create a checklist for the following domain...
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Compact Contract (Load First)

Run these steps first; only load **Expanded Guidance** when a gate fails or the user asks for detail.

1. Run `.specify/scripts/bash/setup-plan.sh --json`; parse `FEATURE_SPEC`, `IMPL_PLAN`, `SPECS_DIR`, `BRANCH`.
2. Derive `FEATURE_DIR="$(dirname "$FEATURE_SPEC")"` and run deterministic gates:
   - `python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json`
   - `python scripts/speckit_plan_gate.py spec-core-action --spec-file "$FEATURE_SPEC" --legacy-ok --json`
   - `python scripts/speckit_plan_gate.py research-prereq --feature-dir "$FEATURE_DIR" --json`
3. Generate/update plan artifacts from template flow (`plan.md`, `data-model.md`, `contracts/`, `quickstart.md`), then run:
   - `python scripts/speckit_plan_gate.py plan-sections --plan-file "$IMPL_PLAN" --json`
   - `python scripts/speckit_plan_gate.py design-artifacts --feature-dir "$FEATURE_DIR" --json`
4. Emit `plan_started`; run `/speckit.planreview`; if open FQs remain run `/speckit.feasibilityspike`; emit `plan_approved` only on success.
5. On any non-zero gate result, route by reason code using `docs/governance/gate-reason-codes.yaml`.

## Expanded Guidance (Load On Demand)

1. **Setup**: Run `.specify/scripts/bash/setup-plan.sh --json` from repo root and parse JSON for FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, BRANCH. Use shell quoting per CLAUDE.md "Shell Script Compatibility".

1a. **Specification checklist gate (MANDATORY — hard block)**:
   - Derive `FEATURE_DIR` from `FEATURE_SPEC` (parent directory of `spec.md`).
   - Run:
     ```bash
     python scripts/speckit_gate_status.py --mode plan --feature-dir "$FEATURE_DIR" --json
     ```
   - If command exits non-zero: stop and route by reason (`missing_requirements_checklist`, `incomplete_checklist_items`).
   - On success, continue.

1b. **Core mechanism clarity gate (MANDATORY)**:
   - Run:
     ```bash
     python scripts/speckit_plan_gate.py spec-core-action --spec-file "$FEATURE_SPEC" --legacy-ok --json
     ```
   - Legacy specs (`specs/000`-`specs/017`) downgrade `missing_named_automated_action` and missing FR section to warnings.
   - Newer specs still hard-block on non-zero with `missing_named_automated_action`.
   - Record the matched line; this action must appear as a node with inbound trigger edge in Architecture Flow.

1c. **Research prerequisite gate (MANDATORY)**:
   - Run:
     ```bash
     python scripts/speckit_plan_gate.py research-prereq --feature-dir "$FEATURE_DIR" --json
     ```
   - If command exits non-zero: stop and require `/speckit.research` completion before planning.

2. **Load context**: Read FEATURE_SPEC and `constitution.md` (repo root). Load IMPL_PLAN template (already copied).

3. **Execute plan workflow**: Follow the structure in IMPL_PLAN template to:
   - Fill Technical Context: **Technology Direction** (category + constraints, NOT specific library names — those go in Technology Selection after feasibilityspike); mark unknowns as "NEEDS CLARIFICATION"
   - Fill External Ingress + Runtime Readiness Gate (no blank statuses; unresolved rows become implementation blockers)
   - Fill async process model details for any event-loop/background-worker integrations (or mark N/A)
   - Fill state ownership/reconciliation model details for any live-vs-local state integrations (or mark N/A)
   - Fill local DB transaction model details for any local persisted-state mutations (or mark N/A)
   - Fill Constitution Check section from constitution
   - Evaluate gates (ERROR if violations unjustified)
   - Phase 0: Generate research.md (resolve all NEEDS CLARIFICATION)
   - Phase 1: Generate data-model.md, contracts/, quickstart.md
   - Phase 1: Update agent context by running the agent script
   - Re-evaluate Constitution Check post-design
   - Validate plan section completeness (required headings + ingress gate statuses):
     ```bash
     python scripts/speckit_plan_gate.py plan-sections --plan-file "$IMPL_PLAN" --json
     ```
   - Validate required Phase 1 artifacts:
     ```bash
     python scripts/speckit_plan_gate.py design-artifacts --feature-dir "$FEATURE_DIR" --json
     ```

4. **Emit pipeline event** and **auto-invoke sub-processes**:

   a. Emit `plan_started` to `.speckit/pipeline-ledger.jsonl`:
      ```json
      {"event": "plan_started", "feature_id": "NNN", "phase": "plan", "actor": "<agent-id>", "timestamp_utc": "..."}
      ```

   b. Report Phase 1 artifacts: branch, IMPL_PLAN path, generated files (data-model.md, contracts/, quickstart.md).

   c. **Auto-invoke `/speckit.planreview`** (MANDATORY — do not skip): run planreview now. The plan phase is not done until planreview completes at least one pass.

   d. After planreview completes: check `## Open Feasibility Questions` in plan.md.
      - If any `- [ ]` items exist: **auto-invoke `/speckit.feasibilityspike`**.
      - If section is empty or all items `[x]`: skip feasibilityspike.

   e. After both sub-processes finish: emit `plan_approved` to `.speckit/pipeline-ledger.jsonl`:
      ```json
      {"event": "plan_approved", "feature_id": "NNN", "phase": "plan", "feasibility_required": true/false, "actor": "<agent-id>", "timestamp_utc": "..."}
      ```

   f. Report: "Plan phase complete. Technology Direction filled, Technology Selection [confirmed / TBD pending spike]. Suggested next: `/speckit.solution`."

   **Hard rule**: If feasibilityspike fails, do not emit `plan_approved`; route back to plan with spike evidence.

## Phases

### Phase 0: Research prerequisite

0. **Research gate execution**:
   - Use `speckit_plan_gate.py research-prereq` result from step 1c as the deterministic source of truth.
   - Load `research.md` only when gate passes; Repo Assembly Map remains mandatory architecture input.

1. **Codebase research** (if `codebase-lsp` MCP server is connected):
   see CLAUDE.md `### Codebase MCP Toolkit` for the current list of available servers and their tools. You MUST use `codegraph` first for discovery/scope (find symbols, callers/callees, imports, and impact scope) before writing, then `codebase-lsp`:
   - Use `get_type` to understand existing type signatures before designing new interfaces or extensions.
   - Use `get_diagnostics` to check whether proposed changes introduce type errors in affected files.

2. **Resolve any remaining unknowns** from Technical Context:
   - For each NEEDS CLARIFICATION still unresolved after research.md: ask user before proceeding
   - For each dependency → confirm it appears in research.md Package Adoption Options

**Output**: research.md loaded; all NEEDS CLARIFICATION resolved

### Phase 1: Design & Contracts

**Prerequisites:** `research.md` complete

1. **Generate data-model.md** by pre-scaffolding from template:
   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]" ARTIFACT="data-model"`
      - Pre-structures the file with Entities, Relationships, State Transitions, Storage & Indexing, Concurrency & Locking sections.
   2. Fill in the `[placeholder]` sections only — structure is pre-seeded.

2. **Define interface contracts** (if project has external interfaces) → `/contracts/`:
   - Identify what interfaces the project exposes to users or other systems
   - Document the contract format appropriate for the project type
   - Examples: public APIs for libraries, command schemas for CLI tools, endpoints for web services, grammars for parsers, UI contracts for applications
   - Skip if project is purely internal (build scripts, one-off tools, etc.)

2a. **Generate quickstart.md** by pre-scaffolding from template:
   1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.plan --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]" ARTIFACT="quickstart"`
      - Pre-structures the file with Prerequisites, Installation, Run, Smoke Test, Common Issues, Next Steps sections.
   2. Fill in the `[placeholder]` slots only — structure is pre-seeded.

2b. **Architecture ensemble (MANDATORY for features with external service integrations)**:

   Generate THREE candidate architectures in parallel sub-agents, each given a different constraint:
   - **Candidate A ("no server")**: Only tokens + hosted services. Custom HTTP server FORBIDDEN.
     GitHub Actions, n8n community nodes, ClickUp automations, Zapier, Make.com — whatever exists.
     Use all relevant repos from the Repo Assembly Map in research.md.
   - **Candidate B ("minimal service")**: Custom service only for logic hosted services cannot
     express. Every custom component must cite the specific FR it cannot cover without it.
   - **Candidate C ("full service")**: Whatever the planner judges cleanest, no constraint.

   For each candidate:
   - Which FRs are covered by existing code from the Repo Assembly Map? Name the source and file.
   - Which FRs require net-new code? List them — these are the true implementation tasks.
   - Maintenance surface: what does the team own long-term?

   **Synthesis gate** (MUST present to user before committing to an architecture):
   - If Candidate A covers all FRs: A is the only recommendation. User must explicitly ask for B or C.
   - If Candidate A has gaps: show the specific uncoverable FRs. Show what Candidate B adds to close
     them. Let user choose before proceeding to C.
   - Only if A+B both leave uncoverable FR gaps: proceed with Candidate C.

   Record all three candidates in research.md under `## Architecture Candidates`.
   The winning candidate's component list becomes the nodes in the Architecture Flow diagram.

3. **Generate Architecture Flow diagram** → update `## Architecture Flow` in plan.md:
   - Map every component from Project Structure as a node
   - Label edges with the data or event passing between components
   - Annotate key entity state transitions from data-model.md
   - Validate: every Project Structure component appears; every data-model.md entity state appears
   - ERROR if either check fails — plan cannot proceed to tasks without a complete diagram

4. **Security boundary review** → update all Principle I (Security Details) sub-clause rows in the Constitution Check:
   - Load the current sub-clauses for Principle I from `constitution.md` (repo root)
     (sub-clauses are labeled I-a, I-b, … and may grow over time — verify all that are present)
   - Using the Architecture Flow diagram as input, trace every edge that crosses a trust boundary
     (external APIs, file system, environment variables, tool arguments, network calls)
   - For each sub-clause, evaluate it against every trust boundary crossing in the diagram
   - Update each I-* row in the Constitution Check table with ✅ Pass, ⚠️ Conditional, or ❌ Fail
   - Any sub-clause that is not ✅ Pass must have a mitigation documented in Complexity Tracking
   - ERROR if any I-* row is left blank

5. **Dependency security audit** → record findings in `## Technical Context` and `research.md`:
   - For every library listed in Technical Context, search for known CVEs and security advisories
   - For each dependency: record the minimum safe version required and any relevant CVEs found
   - If a CVE affects the chosen version and a fix exists: update the plan to pin to the safe version — ERROR if no safe version exists and the library cannot be replaced
   - If a CVE does not affect the target platform or deployment context: document why it is out of scope
   - Update `research.md` with a **Dependency Security** section listing each dependency, its pinned version, any CVEs evaluated, and rationale for the version choice

6. **Async lifecycle design review**:
   - Identify every event loop, spawned task, and background process in the feature flow.
   - Define ownership boundaries and lifecycle states: start, ready, timeout/cancel, graceful shutdown, force-kill fallback.
   - Document forbidden sync-in-async boundary calls (sync wrappers that spin nested loops).
   - Define required observability signals and regression tests for loop/lifecycle failures.

7. **State safety design review**:
   - Identify every entity that exists in both local persisted state and live external state.
   - Define source-of-truth ownership per lifecycle field and required reconciliation checkpoints.
   - Define stale/orphan handling policy and observability signals for drift detection.
   - Define required regression tests proving no unresolved drift leaves local records active.

8. **Local DB transaction design review**:
   - Identify every flow that mutates local DB lifecycle/risk/financial state.
   - Define explicit transaction boundaries for multi-step writes (single-table and cross-table).
   - Define rollback behavior, retry/idempotency semantics, and observability signals for commit/rollback outcomes.
   - Define required regression tests proving no partial writes persist after failure paths.

9. **Agent context update**:
   - Run `.specify/scripts/bash/update-agent-context.sh claude`
   - These scripts detect which AI agent is in use
   - Update the appropriate agent-specific context file
   - Add only new technology from current plan
   - Preserve manual additions between markers

**Output**: data-model.md, /contracts/*, quickstart.md, Architecture Flow in plan.md, async process model + state ownership/reconciliation model + local DB transaction model in technical context, agent-specific file (research.md updated with Dependency Security section)

## Key rules

- Use absolute paths
- ERROR on gate failures or unresolved clarifications

## Brevity Principle

Every plan artifact must earn its tokens. Apply when generating research.md, plan.md, data-model.md, contracts/, and quickstart.md:

- **Tables over prose**: component lists, dependency comparisons, entity fields, gate statuses → table format
- **No redundancy between artifacts**: if a constraint is in plan.md Technical Context, don't restate it in research.md or quickstart.md
- **Architecture Flow is the source of truth for component relationships** — prose descriptions of the same relationships elsewhere should be removed
- **One rationale per decision**: record why a choice was made once, in research.md; don't repeat reasoning in plan.md and quickstart.md
- **Remove filler**: avoid "This plan describes...", "The purpose of this section is to..." — state the content directly
