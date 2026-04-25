---
description: Create or update the feature specification from a natural language feature description.
handoffs: 
  - label: Research Prior Art & Integration Options
    agent: speckit.research
    prompt: Research patterns, prior art, and integration options for the spec...
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

The text the user typed after `/speckit.specify` in the triggering message **is** the feature description. If the message starts with `--update-current-spec`, treat that as a mode flag and treat the remaining text as the feature description delta. Do not ask the user to repeat it unless the resulting description is empty.

Given that feature description, do this:

1. **Determine execution mode and parse description**:
   - If `$ARGUMENTS` contains `--update-current-spec`, run in **update mode**.
   - Otherwise run in **default mode** (new feature branch/spec creation).
   - Strip the `--update-current-spec` flag from `$ARGUMENTS` before analysis.
   - If the remaining description is empty: ERROR "No feature description provided"
   - Use the current checkout only.
   - Do not create temp worktrees or alternate checkout paths.
   - If the current checkout is dirty, stop and ask the user to commit, stash, or discard the changes first.

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
   c. Run this script once per feature. For single quotes in args like "I'm Groot", escape as `'\''` or use double quotes.
   d. Stay in the current checkout; do not route branch creation through temp worktrees or spare checkouts. If the checkout is dirty, abort and ask for commit/stash/discard before proceeding.

4. **If in update mode (`--update-current-spec`) resolve existing spec paths**:
   - Run:

     ```bash
     .specify/scripts/bash/check-prerequisites.sh --json --paths-only
     ```

   - Parse `FEATURE_DIR` and `FEATURE_SPEC` from JSON output.
   - Set `SPEC_FILE=FEATURE_SPEC`.
   - If `SPEC_FILE` does not exist, **STOP** and tell the user:
     > "No existing spec.md was found for this branch. Run `/speckit.specify` without `--update-current-spec` first."

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
    8. Return: SUCCESS (spec ready for research)

8. Write the specification to SPEC_FILE using the template structure, replacing placeholders with concrete details derived from the feature description (arguments) while preserving section order and headings.
   - In **default mode**, this writes the newly created spec file.
   - In **update mode**, this updates the existing `spec.md` in-place.
   - Populate the Delivery Routing & Rough Size section with a machine-readable `routing` + `risk` JSON block so downstream gates can branch without re-parsing prose.

9. **Specification Quality Validation**: After writing the initial spec, validate it against quality criteria:

   a. **Validate Routing Contract**:

      1. Run: `uv run python scripts/speckit_spec_gate.py validate-routing --spec-file "$SPEC_FILE" --json`
         - Confirms the machine-readable `routing` + `risk` block exists
         - Parses the JSON block and rejects placeholder-only or incomplete routing values

   b. **Create Spec Quality Checklist**: Pre-scaffold the checklist file from the template:

      1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.specify --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
         - Reads `command-manifest.yaml` to resolve which artifacts speckit.specify owns
         - Copies `.specify/templates/requirements-checklist-template.md` to `$FEATURE_DIR/checklists/requirements.md`
         - Performs scalar substitutions: `[FEATURE_NAME]` → the feature name, `[DATE]` → today's date, etc.

      2. The checklist is now pre-structured with validation items covering:
         - Content Quality: no implementation details, focused on user value, non-technical language
         - Requirement Completeness: testable FRs, measurable success criteria, edge case coverage, boundary assumptions
         - Feature Readiness: FR coverage, user scenarios, no implementation leakage, external integration verification
         - All 32 checklist items are pre-populated; you only fill in the checkbox marks and address findings

   b. **Run Validation Check**: Review the spec against each checklist item:
      - For each item, determine if it passes or fails
      - Document specific issues found (quote relevant spec sections)
      - If scope exclusions reference external tools/packages ("covered by X", "handled by X"), fail validation unless those tools have been verified as installable — run the appropriate registry check (`npm view`, `pip index versions`, `gh api repos/`) and confirm the tool exists. A GitHub repo alone is not sufficient; the package must be installable from its claimed registry.
      - If live-vs-local state is in scope, fail validation unless requirements explicitly cover source-of-truth ownership, reconcile-before-decision expectation, stale fallback, and fail policy
      - If local DB mutation paths are in scope, fail validation unless requirements explicitly cover transaction boundaries, rollback/no-partial-write behavior, and retry/idempotency expectations
      - If venue-constrained entities are in scope, fail validation unless requirements explicitly cover metadata-first valid-object discovery, validated live-data request boundaries, and discovery-failure policy

   c. **Handle Validation Results**:

      - **If all items pass**: Mark checklist complete and proceed to step 10

      - **If items fail (excluding [NEEDS CLARIFICATION])**:
        1. List the failing items and specific issues
        2. Update the spec to address each issue
        3. Re-run validation until all items pass (max 3 iterations)
        4. If still failing after 3 iterations, document remaining issues in checklist notes and warn user

      - **If [NEEDS CLARIFICATION] markers remain**:
        1. Extract markers and group into at most 3 high-impact questions.
        2. Ask all questions together using a compact table: `Option | Answer | Implications`.
        3. Include options `A/B/C/Custom` and wait for user selections.
        4. Replace markers with selected answers and re-run validation.

   d. **Update Checklist**: After each validation iteration, update the checklist file with current pass/fail status

10. **T-shirt size estimate**: After spec validation passes, produce a rough complexity estimate for the feature as a whole. This is NOT task-level — it is an epic-level signal for prioritization across features.

   - Evaluate based on: number of user stories, number of edge cases, number of external integrations, breadth of acceptance criteria, and data model complexity (entity count, relationship density)
   - Assign one of: **XS** (single concern, 1 story, no integrations), **S** (1-2 stories, minimal edge cases), **M** (2-3 stories, some integrations or data model), **L** (3-5 stories, multiple integrations, non-trivial data model), **XL** (5+ stories, complex integrations, significant edge cases, multiple actors)
   - Output as: `**Estimated Size:** [XS/S/M/L/XL] — [1-sentence rationale]`
   - This estimate is informational only — it does NOT block any workflow step

11. **Emit pipeline event**:
   
   Emit `backlog_registered` to `.speckit/pipeline-ledger.jsonl`:
   ```json
    {"event": "backlog_registered", "feature_id": "NNN", "phase": "spec", "actor": "<agent-id>", "timestamp_utc": "...", "routing": {"research_route": "skip", "plan_profile": "skip", "sketch_profile": "core", "tasking_route": "required", "estimate_route": "required_after_tasking", "routing_reason": "...", "conditional_sketch_sections": []}, "risk": {"requirement_clarity": "low", "repo_uncertainty": "low", "external_dependency_uncertainty": "low", "state_data_migration_risk": "low", "runtime_side_effect_risk": "low", "human_operator_dependency": "low"}}
    ```

12. Report completion with branch name, spec file path, checklist results, t-shirt size estimate, and readiness for the next phase (`/speckit.research`).
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
