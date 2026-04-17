---
description: Split an XL (or L) spec into smaller, independently deliverable phase specs, each sized L or smaller.
handoffs:
  - label: Specify Phase 1
    agent: speckit.specify
    prompt: Specify phase 1 of the split
  - label: Run Planning on Split Phases
    agent: speckit.plan
    prompt: Build a technical plan for the first phase spec
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty). If the user names a specific spec (e.g., "008") or provides a phase breakdown suggestion, use it.

## Outline

Goal: Take an oversized spec (XL or L with many stories) and split it into 2–4 smaller, independently shippable phase specs — each targeted at **L or smaller**. Each phase spec must deliver standalone user value (not just "infrastructure for the next phase").

This command operates on the **current feature branch's spec**, or on a spec identified by number/name in `$ARGUMENTS`.

---

### Execution Steps

1. **Identify the source spec**:
   - Feature purpose: carry the one-line feature purpose from `spec.md` through this step.

   a. Run prerequisites check:
      ```
      .specify/scripts/bash/check-prerequisites.sh --json
      ```
      Parse `FEATURE_DIR` and `BRANCH_NAME`. Derive path to `spec.md`.

   b. If `$ARGUMENTS` contains a number (e.g., "008") or a branch name, use that to locate the spec instead:
      - Find the matching directory under `specs/` (e.g., `specs/008-*`)
      - Read `spec.md` from that directory

   c. If no spec is found, abort with: `ERROR: No spec found. Run /speckit.specify first or provide a valid feature number.`

2. **Read and analyze the source spec**:

   Load the full `spec.md`. Extract:
   - Feature name and one-line purpose
   - All user stories with their priority labels (P1, P2, …) and acceptance scenarios
   - All functional requirements (FR-NNN)
   - Key entities
   - Constraints and non-goals
   - Resolved decisions and open questions
   - T-shirt size (from spec or checklist notes) — if not present, estimate it now using the same rubric as `/speckit.specify`

   If the spec is **M or smaller**, abort with:
   `ERROR: This spec is already [M/S/XS] — splitting is only warranted for L or XL specs. Proceed directly to /speckit.plan.`

3. **Propose a phase split**:

   Apply these splitting rules in order of preference:

   **Rule 1 — Split by user story priority**:
   - Phase 1: P1 story only (plus all shared infrastructure needed by P1)
   - Phase 2: P2 story (may reuse Phase 1 infrastructure)
   - Phase 3+: P3, P4, … stories in priority order
   - Stop splitting when each phase would be **L or smaller**

   **Rule 2 — Split by capability layer** (use only if user stories cannot be cleanly separated):
   - Phase 1: Data ingestion and model registration (can be tested with a read-only query)
   - Phase 2: Core scenario execution (depends on Phase 1 models existing)
   - Phase 3: Conversational/multi-turn interface (depends on Phase 2 execution)

   **Rule 3 — Hybrid** (combine the above if neither alone produces clean phases):
   - Identify which stories share infrastructure that must be built first
   - Group those into a foundational phase; split remaining stories into their own phases

   **Split constraints** (non-negotiable):
   - Every phase must be **independently deployable and testable** — Phase N+1 may depend on Phase N being deployed, but must NOT require Phase N+2 to exist.
   - Every phase must deliver **standalone user value** — "setup for the next phase" is not a valid phase.
   - No functional requirement from the source spec may be dropped. Every FR-NNN must appear in exactly one phase.
   - Shared infrastructure (data model, registries, auth) goes in Phase 1 only and is explicitly listed as a dependency of subsequent phases.
   - The phase split must be presented to the user for approval **before** any new spec files are written.

4. **Present the proposed split to the user**:

   Output a structured proposal in this format:

   ```
   ## Proposed Phase Split: [Source Feature Name]

   Source spec: specs/[NNN]-[name]/spec.md
   Source size: [XL/L]
   Proposed phases: [N]

   ---

   ### Phase 1 — [Short Phase Name] (Estimated: [S/M/L])

   **Delivers**: [One sentence of standalone user value]
   **User Stories included**: [P1, P2, ...]
   **Functional Requirements**: [FR-001, FR-002, ...]
   **Key Entities owned**: [Entity names]
   **Dependencies**: None (foundational)

   ---

   ### Phase 2 — [Short Phase Name] (Estimated: [S/M/L])

   **Delivers**: [One sentence of standalone user value]
   **User Stories included**: [P3, ...]
   **Functional Requirements**: [FR-007, FR-008, ...]
   **Key Entities owned**: [Entity names]
   **Dependencies**: Phase 1 deployed

   ---

   [Continue for each phase]

   ---

   ## FR Coverage Check

   All [N] functional requirements from source spec accounted for: ✓

   | FR      | Phase |
   | :------ | :---- |
   | FR-001  | 1     |
   | FR-002  | 1     |
   | ...     | ...   |

   ---

   Reply with:
   - **"approve"** to proceed with creating phase specs as proposed
   - **"adjust [phase] [change]"** to modify the split before proceeding (e.g., "adjust phase 2 move FR-009 to phase 3")
   - **"cancel"** to abort without creating any files
   ```

5. **Wait for user approval** before proceeding. Do NOT create any files until the user replies "approve" or an adjusted variant.

6. **On approval — create phase specs**:

   For each phase in the approved split:

   a. Determine the next available feature number:
      - Check `specs/` directories and local git branches for the highest existing number
      - Assign sequentially: if source was 008, phases become 009, 010, 011, …

   b. Run create script for each phase:
      ```
      .specify/scripts/bash/create-new-feature.sh --json --number [N] --short-name "[phase-short-name]" "[Phase description]"
      ```
      Capture `SPEC_FILE` and `BRANCH_NAME` from JSON output.

   c. Write a complete, self-contained `spec.md` for the phase using the spec template structure:
      - **Feature name**: "[Source Feature Name] — Phase [N]: [Phase Short Name]"
      - **One-Line Purpose**: Scoped to only what this phase delivers
      - **Consumer & Context**: Same as source spec
      - **User Scenarios**: Only the stories assigned to this phase, renumbered P1, P2, … within the phase
      - **Flowchart**: Covers only this phase's flows
      - **Data & State Preconditions**: Include "Phase [N-1] is deployed and its [entities] exist" as explicit preconditions for phases 2+
      - **Inputs & Outputs**: Scoped to this phase
      - **Constraints & Non-Goals**: Inherit applicable constraints from source; add "Out of scope: [list of features deferred to later phases]"
      - **Requirements**: Only the FR-NNN assigned to this phase; renumber FR-001, FR-002, … within the phase
      - **Key Entities**: Only entities owned by this phase
      - **Success Criteria**: Scoped to this phase's deliverables
      - **Definition of Done**: Single sentence for this phase only
      - **Resolved Decisions**: Carry over relevant resolved decisions from source spec
      - Do NOT include open questions that were resolved; do NOT create new open questions unless the split itself introduced genuine new ambiguity

   d. Create the checklists directory and write `checklists/requirements.md` for each phase spec, pre-validated (all items unchecked — this is a new spec that has not yet been reviewed).

   e. Check out the first phase branch after all specs are written:
      ```
      git checkout [first-phase-branch]
      ```

7. **Update the source spec**:

   Add a `## Split Into Phases` section at the bottom of the source spec's `spec.md`:

   ```markdown
   ## Split Into Phases

   This spec was split on [DATE] because its XL size warranted independent delivery phases.
   The source spec is retained for reference but superseded by the phase specs below.

   | Phase | Branch | Spec | Estimated Size |
   | :---- | :----- | :--- | :------------- |
   | Phase 1 — [Name] | `[branch]` | [spec.md](../../[NNN]-[name]/spec.md) | [S/M/L] |
   | Phase 2 — [Name] | `[branch]` | [spec.md](../../[NNN]-[name]/spec.md) | [S/M/L] |
   ```

   Also update the source spec's **Status** header field from `Draft` to `Superseded`.

8. **Report completion**:

   Output a summary:
   ```
   ## Split Complete

   Source spec [NNN]-[name] (XL) → [N] phase specs

   | Phase | Branch | Size | Status |
   | :---- | :----- | :--- | :----- |
   | 1 — [Name] | `[branch]` | [S/M/L] | Ready for /speckit.plan |
   | 2 — [Name] | `[branch]` | [S/M/L] | Ready for /speckit.plan |

   Currently checked out: [first-phase-branch]
   Next step: /speckit.plan (for Phase 1)
   ```

---

## Behavior Rules

- **Never write files before user approves the split proposal** — the proposal step is a hard gate.
- **No scope drop**: Every FR from the source spec must appear in exactly one phase spec. Verify this with the FR Coverage Check table.
- **No scope addition**: Phase specs must not introduce new requirements not present in the source spec. If the split reveals a genuine gap, note it as an Open Question in that phase's spec — do not silently add scope.
- **Source spec is preserved**: The source spec is marked Superseded but never deleted. It serves as the canonical record of the original intent.
- **Phase numbering within each spec restarts**: User stories restart at P1; functional requirements restart at FR-001. The phase label ("Phase 2") distinguishes them from other features.
- **Shared infrastructure rule**: If two phases need the same entity or capability, it belongs to the earlier phase. The later phase lists it as a precondition, not a requirement.
- **Each phase must be L or smaller**: If a proposed phase is still XL after splitting, split it again before writing files.
- **Idempotent detection**: If the source spec already has a `## Split Into Phases` section, report the existing split and ask the user if they want to re-split or proceed to the next step.
