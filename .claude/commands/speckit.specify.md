---
description: Create or update the feature specification from a natural language feature description.
handoffs: 
  - label: Build Technical Plan
    agent: speckit.plan
    prompt: Create a plan for the spec. I am building with...
  - label: Clarify Spec Requirements
    agent: speckit.clarify
    prompt: Clarify specification requirements
    send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Compact Contract (Load First)

Run these steps first; only load **Expanded Guidance** when a gate fails or user asks for detail.

1. Parse mode from `$ARGUMENTS` (`default` vs `--update-current-spec`).
2. Default mode: create branch/spec once with `.specify/scripts/bash/create-new-feature.sh --json --short-name ...`.
3. Update mode: resolve existing paths via `.specify/scripts/bash/check-prerequisites.sh --json --paths-only`.
4. Run code discovery (`codegraph` first, fallback grep) before writing any spec text.
5. Write spec from template, scaffold requirements checklist, then run:
   - `python scripts/speckit_spec_gate.py checklist-status --feature-dir "$FEATURE_DIR" --json`
   - `python scripts/speckit_spec_gate.py extract-clarifications --spec-file "$SPEC_FILE" --json`
6. If clarifications exist, validate question-table format before asking:
   - `python scripts/speckit_spec_gate.py validate-clarification-questions --markdown-file <draft.md> --json`
7. Branch on reason codes from `docs/governance/gate-reason-codes.yaml`; emit `backlog_registered` only after gates pass.

## Expanded Guidance (Load On Demand)

The text the user typed after `/speckit.specify` in the triggering message **is** the feature description. If the message starts with `--update-current-spec`, treat that as a mode flag and treat the remaining text as the feature description delta. Do not ask the user to repeat it unless the resulting description is empty.

Given that feature description, do this:

1. **Determine execution mode and parse description**:
   - If `$ARGUMENTS` contains `--update-current-spec`, run in **update mode**.
   - Otherwise run in **default mode** (new feature branch/spec creation).
   - Strip the `--update-current-spec` flag from `$ARGUMENTS` before analysis.
   - If the remaining description is empty: ERROR "No feature description provided"

2. **If in default mode, generate a concise short name** (2-4 words):
   - Extract the highest-signal keywords from the feature description.
   - Prefer `action-noun` style and preserve technical acronyms.
   - Keep it short and unique within existing branch/spec naming.

3. **If in default mode, create the feature branch/spec once using the script**:

   a. Run (pass only `--json` and `--short-name`; never pass `--number`):

      ```bash
      .specify/scripts/bash/create-new-feature.sh --json --short-name "your-short-name" "Feature description"
      ```

   b. Parse JSON output and treat it as authoritative for `BRANCH_NAME`, `FEATURE_DIR`, and `SPEC_FILE`.
   c. Run this script once per feature. Use shell quoting per CLAUDE.md "Shell Script Compatibility".

4. **If in update mode (`--update-current-spec`) resolve existing spec paths**:
   - Run:

     ```bash
     .specify/scripts/bash/check-prerequisites.sh --json --paths-only
     ```

   - Parse `FEATURE_DIR` and `FEATURE_SPEC` from JSON output.
   - Set `SPEC_FILE=FEATURE_SPEC`.
   - If `SPEC_FILE` does not exist: stop (`missing_spec_file`).

5. **Codebase discovery scan (mandatory before writing any spec)**:

   Before writing anything, use `codegraph` to verify whether the described capability already exists in the codebase. Extract 3–5 key domain terms from the feature description (e.g., entity names, action verbs, integration targets) and run `find_code` for each.

   ```
   mcp__codegraph__find_code(query="<term>")
   ```

   Run all term searches in parallel. Then evaluate results:

   - **If matches found**: Read the matched files to understand what already exists. Report findings to the user before proceeding. The spec must account for existing code — either by extending it, replacing it (with justification), or scoping around it. Do NOT write a spec that ignores or duplicates existing capability.
   - **If no matches found**: Confirm in the spec output that no existing implementation was found, and proceed.
   - **If codegraph is unavailable** (MCP server not running): Fall back to `Grep` for the same terms across `src/` and `tests/`. Do NOT skip the search entirely.

   This step satisfies the CLAUDE.md mandatory workflow order: "Use `codegraph` first for discovery and scope."

6. Load `.specify/templates/spec-template.md` to understand required sections.

7. Follow this execution flow:

    1. Parse user description from Input
       If empty: ERROR "No feature description provided"
    2. Extract key concepts from description
       Identify: actors, actions, data, constraints
    3. For unclear aspects:
       - Always err on the side of asking rather than doing without override
       - mark with [NEEDS CLARIFICATION: specific question]
       - Refer to the constituion.md principles
       - Prioritize clarifications by impact: scope > security/privacy > user experience > technical details
       - For automation/orchestration features: the specific tool, command, or agent that executes
         the primary automated work MUST appear as a Functional Requirement — do not defer this to
         an adopted dependency or boundary assumption's internals. If unknown, mark as
         [NEEDS CLARIFICATION: what tool/agent/command executes the actual automated work?]
    4. Fill User Scenarios & Testing section
       If no clear user flow: ERROR "Cannot determine user scenarios"
    5. Generate Functional Requirements
       Each requirement must be testable
       Use reasonable defaults for unspecified details (document assumptions in Assumptions section)
    6. Define Success Criteria
       Create measurable, technology-agnostic outcomes
       Include both quantitative metrics (time, performance, volume) and qualitative measures (user satisfaction, task completion)
       Each criterion must be verifiable without implementation details
    7. Identify Key Entities (if data involved)
    8. Return: SUCCESS (spec ready for planning)

8. Write the specification to SPEC_FILE using the template structure, replacing placeholders with concrete details derived from the feature description (arguments) while preserving section order and headings.
   - In **default mode**, this writes the newly created spec file.
   - In **update mode**, this updates the existing `spec.md` in-place.

9. **Specification Quality Validation**: After writing the initial spec, validate it against quality criteria:

   a. **Create Spec Quality Checklist**: Pre-scaffold checklist from template:

      1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.specify --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
         - Reads `.specify/command-manifest.yaml` to resolve which artifacts speckit.specify owns
         - Copies `.specify/templates/requirements-checklist-template.md` to `$FEATURE_DIR/checklists/requirements.md`
         - Performs scalar substitutions: `[FEATURE_NAME]` → the feature name, `[DATE]` → today's date, etc.

   b. **Run deterministic checklist + clarification extraction**:
      ```bash
      python scripts/speckit_spec_gate.py checklist-status --feature-dir "$FEATURE_DIR" --json
      python scripts/speckit_spec_gate.py extract-clarifications --spec-file "$SPEC_FILE" --json
      ```

   c. **Apply quality invariants, then re-run deterministic checks**:
      - Verify installable external-package claims (`npm view`, `pip index versions`, `gh api repos/`) when exclusions reference external tools.
      - If live-vs-local state is in scope, requirements must include ownership, reconciliation order, stale fallback, and fail policy.
      - If local DB mutation paths are in scope, requirements must include transaction boundaries and rollback/no-partial-write behavior.
      - If venue-constrained entities are in scope, requirements must include metadata-first discovery + validated live-data request policy.
      - Re-run `checklist-status` after each edit iteration (max 3).

   d. **Handle deterministic results**:

      - If `checklist-status` exits non-zero: fix checklist/spec issues and re-run (max 3 iterations).
      - If still failing after 3 iterations: document unresolved items in checklist notes and warn user.

      - If `extract-clarifications` reports markers:
        1. Group into at most 3 questions and draft one markdown block containing all questions.
        2. Validate draft format before presenting:
           ```bash
           python scripts/speckit_spec_gate.py validate-clarification-questions --markdown-file <draft.md> --json
           ```
        3. If format check fails, fix format and re-run.
        4. Present validated questions, collect responses, replace markers, then re-run `extract-clarifications`.

   e. **Update checklist file** after each iteration with current pass/fail state.

10. **T-shirt size estimate**: After spec validation passes, produce a rough complexity estimate for the feature as a whole. This is NOT task-level — it is an epic-level signal for prioritization across features.

   - Evaluate based on: number of user stories, number of edge cases, number of external integrations, breadth of acceptance criteria, and data model complexity (entity count, relationship density)
   - Assign one of: **XS** (single concern, 1 story, no integrations), **S** (1-2 stories, minimal edge cases), **M** (2-3 stories, some integrations or data model), **L** (3-5 stories, multiple integrations, non-trivial data model), **XL** (5+ stories, complex integrations, significant edge cases, multiple actors)
   - Output as: `**Estimated Size:** [XS/S/M/L/XL] — [1-sentence rationale]`
   - This estimate is informational only — it does NOT block any workflow step

11. **Final ask-alignment pass (required)**:

   - Run one final pass comparing the completed spec against the original ask text parsed from Step 1 (after stripping `--update-current-spec`).
   - Confirm all explicit asks are represented in the spec (or explicitly marked out-of-scope/assumption), and no contradictory scope was introduced.
   - If drift or omission is found, update the spec immediately and re-run deterministic checks from Step 9 before continuing.

12. **Emit pipeline event**:
   
   Emit `backlog_registered` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "backlog_registered", "feature_id": "NNN", "phase": "spec", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

13. Report completion with branch name, spec file path, checklist results, t-shirt size estimate, ask-alignment result (`pass`/`corrected`), and readiness for the next phase (`/speckit.clarify` or `/speckit.plan`).
   - In **update mode**, explicitly report that existing spec scope was updated in-place (no new branch created).

**NOTE:** In default mode, the script creates and checks out a new branch and initializes the spec file before writing. In update mode, no new branch is created.

## General Guidelines

## Quick Guidelines

- Focus on **WHAT** users need and **WHY**.
- Avoid HOW to implement (no tech stack, APIs, code structure).
- Written for business stakeholders, not developers.
- DO NOT create any checklists that are embedded in the spec. That will be a separate command.

### Section Requirements

- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### Brevity Principle

Every section must earn its tokens. Apply these rules when generating or updating a spec:

- **Tables over prose**: structured comparisons, lists of fields, acceptance scenarios → table format
- **No redundancy across sections**: if a constraint is in Requirements, don't restate it in Edge Cases
- **One example maximum per concept**: illustrate once, not repeatedly with variations
- **Remove filler**: avoid "This feature will...", "The system should be able to...", "It is important that..." — state the requirement directly

### For AI Generation

- Document assumptions in the Assumptions section.
- Prioritize clarifications: scope > security/privacy > UX > technical details.
- Treat vague requirements as checklist failures and resolve them.
- Use reasonable defaults unless legally/financially risky.

### Success Criteria Guidelines

Success criteria must be measurable, technology-agnostic, user-focused, and verifiable.
