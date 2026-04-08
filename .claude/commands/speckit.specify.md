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

## Outline

The text the user typed after `/speckit.specify` in the triggering message **is** the feature description. If the message starts with `--update-current-spec`, treat that as a mode flag and treat the remaining text as the feature description delta. Do not ask the user to repeat it unless the resulting description is empty.

Given that feature description, do this:

1. **Determine execution mode and parse description**:
   - If `$ARGUMENTS` contains `--update-current-spec`, run in **update mode**.
   - Otherwise run in **default mode** (new feature branch/spec creation).
   - Strip the `--update-current-spec` flag from `$ARGUMENTS` before analysis.
   - If the remaining description is empty: ERROR "No feature description provided"

2. **If in default mode, generate a concise short name** (2-4 words) for the branch:
   - Analyze the feature description and extract the most meaningful keywords
   - Create a 2-4 word short name that captures the essence of the feature
   - Use action-noun format when possible (e.g., "add-user-auth", "fix-payment-bug")
   - Preserve technical terms and acronyms (OAuth2, API, JWT, etc.)
   - Keep it concise but descriptive enough to understand the feature at a glance
   - Examples:
     - "I want to add user authentication" → "user-auth"
     - "Implement OAuth2 integration for the API" → "oauth2-api-integration"
     - "Create a dashboard for analytics" → "analytics-dashboard"
     - "Fix payment processing timeout bug" → "fix-payment-timeout"

3. **If in default mode, check for existing branches before creating new one**:

   a. Run the script — pass only `--json` and `--short-name`; do NOT pass `--number`. The script auto-detects the globally highest number across all branches and all specs directories and increments it:

      ```bash
      .specify/scripts/bash/create-new-feature.sh --json --short-name "your-short-name" "Feature description"
      ```

      - Bash example: `.specify/scripts/bash/create-new-feature.sh --json --short-name "user-auth" "Add user authentication"`

   **IMPORTANT**:
   - Never pass `--number` manually — the script computes the correct global sequential number automatically
   - You must only ever run this script once per feature
   - The JSON is provided in the terminal as output - always refer to it to get the actual content you're looking for
   - The JSON output will contain BRANCH_NAME and SPEC_FILE paths
   - For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot")

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
    8. Return: SUCCESS (spec ready for planning)

8. Write the specification to SPEC_FILE using the template structure, replacing placeholders with concrete details derived from the feature description (arguments) while preserving section order and headings.
   - In **default mode**, this writes the newly created spec file.
   - In **update mode**, this updates the existing `spec.md` in-place.

9. **Specification Quality Validation**: After writing the initial spec, validate it against quality criteria:

   a. **Create Spec Quality Checklist**: Pre-scaffold the checklist file from the template:

      1. Run: `python .specify/scripts/pipeline-scaffold.py speckit.specify --feature-dir $FEATURE_DIR FEATURE_NAME="[Feature Name]"`
         - Reads `.specify/command-manifest.yaml` to resolve which artifacts speckit.specify owns
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
        1. Extract all [NEEDS CLARIFICATION: ...] markers from the spec
        2. For each clarification needed (max 3), present options to user in this format:

           ```markdown
           ## Question [N]: [Topic]
           
           **Context**: [Quote relevant spec section]
           
           **What we need to know**: [Specific question from NEEDS CLARIFICATION marker]
           
           **Suggested Answers**:
           
           | Option | Answer | Implications |
           |--------|--------|--------------|
           | A      | [First suggested answer] | [What this means for the feature] |
           | B      | [Second suggested answer] | [What this means for the feature] |
           | C      | [Third suggested answer] | [What this means for the feature] |
           | Custom | Provide your own answer | [Explain how to provide custom input] |
           
           **Your choice**: _[Wait for user response]_
           ```

        3. **CRITICAL - Table Formatting**: Ensure markdown tables are properly formatted:
           - Use consistent spacing with pipes aligned
           - Each cell should have spaces around content: `| Content |` not `|Content|`
           - Header separator must have at least 3 dashes: `|--------|`
           - Test that the table renders correctly in markdown preview
        4. Number questions sequentially
        5. Present all questions together before waiting for responses
        6. Wait for user to respond with their choices for all questions (e.g., "Q1: A, Q2: Custom - [details], Q3: B")
        7. Update the spec by replacing each [NEEDS CLARIFICATION] marker with the user's selected or provided answer
        8. Re-run validation after all clarifications are resolved

   d. **Update Checklist**: After each validation iteration, update the checklist file with current pass/fail status

10. **T-shirt size estimate**: After spec validation passes, produce a rough complexity estimate for the feature as a whole. This is NOT task-level — it is an epic-level signal for prioritization across features.

   - Evaluate based on: number of user stories, number of edge cases, number of external integrations, breadth of acceptance criteria, and data model complexity (entity count, relationship density)
   - Assign one of: **XS** (single concern, 1 story, no integrations), **S** (1-2 stories, minimal edge cases), **M** (2-3 stories, some integrations or data model), **L** (3-5 stories, multiple integrations, non-trivial data model), **XL** (5+ stories, complex integrations, significant edge cases, multiple actors)
   - Output as: `**Estimated Size:** [XS/S/M/L/XL] — [1-sentence rationale]`
   - This estimate is informational only — it does NOT block any workflow step

11. **Emit pipeline event**:
   
   Emit `backlog_registered` to `.speckit/pipeline-ledger.jsonl`:
   ```json
   {"event": "backlog_registered", "feature_id": "NNN", "phase": "spec", "actor": "<agent-id>", "timestamp_utc": "..."}
   ```

12. Report completion with branch name, spec file path, checklist results, t-shirt size estimate, and readiness for the next phase (`/speckit.clarify` or `/speckit.plan`).
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

When creating this spec from a user prompt:


2. **Document assumptions**: Record reasonable defaults in the Assumptions section
3. **Prioritize clarifications**: scope > security/privacy > user experience > technical details
4. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
5. **Common areas needing clarification** (only if no reasonable default exists):
   - Feature scope and boundaries (include/exclude specific use cases)
   - User types and permissions (if multiple conflicting interpretations possible)
   - Security/compliance requirements (when legally/financially significant)

**Examples of reasonable defaults** (don't ask about these):

- Data retention: Industry-standard practices for the domain
- Performance targets: Standard web/mobile app expectations unless specified
- Error handling: User-friendly messages with appropriate fallbacks
- Authentication method: Standard session-based or OAuth2 for web apps
- Integration patterns: Use project-appropriate patterns (REST/GraphQL for web services, function calls for libraries, CLI args for tools, etc.)

### Success Criteria Guidelines

Success criteria must be:

1. **Measurable**: Include specific metrics (time, percentage, count, rate)
2. **Technology-agnostic**: No mention of frameworks, languages, databases, or tools
3. **User-focused**: Describe outcomes from user/business perspective, not system internals
4. **Verifiable**: Can be tested/validated without knowing implementation details

**Good examples**:

- "Users can complete checkout in under 3 minutes"
- "System supports 10,000 concurrent users"
- "95% of searches return results in under 1 second"
- "Task completion rate improves by 40%"

**Bad examples** (implementation-focused):

- "API response time is under 200ms" (too technical, use "Users see results instantly")
- "Database can handle 1000 TPS" (implementation detail, use user-facing metric)
- "React components render efficiently" (framework-specific)
- "Redis cache hit rate above 80%" (technology-specific)
