---
description: Identify underspecified areas in the current plan and generated artifacts by asking targeted technical clarification questions and encoding answers back into plan artifacts. Auto-invoked by /speckit.plan; callable standalone.
handoffs:
  - label: Run Feasibility Check
    agent: speckit.feasibilityspike
    prompt: planreview complete — open feasibility questions exist. Run feasibility spike.
    send: true
  - label: Begin Solution Phase
    agent: speckit.solution
    prompt: planreview complete — no open feasibility questions. Begin solution phase.
    send: false
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

Goal: Detect and reduce technical ambiguity or missing precision in the active feature plan and its generated artifacts, then record resolved answers directly into the relevant plan files.

Note: This review is expected to run AFTER `/speckit.plan` completes and BEFORE `/speckit.solution`. If the user explicitly states they are skipping plan review (e.g., trivial plan, no new dependencies), you may proceed but must warn that task generation may produce underspecified or incorrect tasks.

Execution steps:

1. Run `.specify/scripts/bash/check-prerequisites.sh --json --paths-only` from repo root **once**. Parse fields:
   - `FEATURE_DIR`
   - `IMPL_PLAN` (plan.md path)
   - (Optionally capture `FEATURE_SPEC`, `TASKS`.)
   - If JSON parsing fails, abort and instruct user to re-run `/speckit.plan` or verify feature branch environment.
   - Use shell quoting per CLAUDE.md "Shell Script Compatibility".

2. Load plan artifacts from FEATURE_DIR:
   - **Required**: plan.md
   - **Load if present**: research.md, data-model.md, contracts/*, quickstart.md

2b. **Catalog cross-reference** (MANDATORY after loading plan artifacts):
   - Read `catalog.yaml` from repo root if it exists.
   - For each external service node in the Architecture Flow diagram in plan.md:

   | Situation | Action |
   |-----------|--------|
   | Service in Architecture Flow, **no catalog entry** | Auto-add to `plan.md ## Open Feasibility Questions`: `- [ ] **FQ-NNN**: Execution model for [service] is not catalogued — execution constraints, auth, and infrastructure are unknown. Probe: [describe minimal test of the core capability needed by this feature]. Blocking: [which architecture component depends on this capability]`. Also flag that a catalog-entry task must be emitted by /speckit.tasking. |
   | Service in catalog with **known constraints** | Cross-check plan's intended usage against those constraints. If conflict: add as CRITICAL finding in the domain coverage table (step 4). |
   | **New service** being added by this feature (not yet in catalog) | Expected — note that a catalog-entry task is a required deliverable; not a hard block. |

   - If catalog.yaml does not exist: note in the report that catalog.yaml is absent; no block.

3. **ERROR check first** — abort if any of the following are found:
   - Any remaining `NEEDS CLARIFICATION` markers in plan.md or generated artifacts — these are unresolved Phase 0 items that must be fixed in the plan before review can proceed; instruct user to re-run `/speckit.plan`
   - Any empty cells in the Constitution Check table — these are required gate items
   - Any empty cells in the `Behavior Map Sync Gate` table in plan.md — this gate must be completed before task generation
   - Missing or empty contract sections in plan.md for:
     - `Repeated Architectural Unit Recognition`
     - `Pipeline Architecture Model`
     - `Artifact / Event Contract Architecture`
     - `Handoff Contract to Sketch`

4. **Ambiguity scan** — build an internal prioritized queue of candidate questions. Do NOT output the queue. Scan for:

   **Technical Context gaps**:
   - Dependencies listed without version floors (e.g., `httpx` with no minimum version pinned)
   - Target platform stated vaguely (e.g., "macOS/Linux" without specifying minimum OS version if relevant)
   - Performance goals without measurable thresholds
   - Constraints listed as intentions rather than hard limits

   **Architecture ambiguities**:
   - Module boundaries implied but not explicit (e.g., "parser handles edge cases" — which ones?)
   - Data flow edges in Architecture Flow diagram that cross trust boundaries without documented validation strategy
   - Entity state transitions in data-model.md that lack a defined error/rollback path

   **Plan architecture-contract gaps**:
   - `Repeated Architectural Unit Recognition` does not define stable repeated-unit boundaries or abstraction rules
   - `Pipeline Architecture Model` does not define deterministic stage boundaries/ownership
   - `Artifact / Event Contract Architecture` does not define required contracts, producers/consumers, or validation ownership
   - `Handoff Contract to Sketch` does not clearly constrain what sketch MUST preserve and what it MAY extend

   **State safety & reconciliation gaps** (mandatory when local state mirrors live external state):
   - Source-of-truth ownership per lifecycle field is missing or ambiguous
   - Reconciliation checkpoints are missing before risk/scoring/side-effect decisions (startup, reconnect, pre-decision)
   - Stale data fallback and fail policy are unspecified when live refresh is unavailable
   - Drift paths allow local active state to persist when live state is closed/missing

   **Local DB transaction-integrity gaps** (mandatory when local DB mutations represent lifecycle/risk/financial state):
   - Transaction boundaries for multi-step writes are missing or ambiguous
   - Rollback/no-partial-write behavior is unspecified for failure paths
   - Retry/idempotency behavior is unspecified for duplicate callbacks/replayed events
   - Flows can mark terminal lifecycle states without confirmed commit outcomes

   **Venue-constrained discovery gaps** (mandatory when integrations rely on venue-constrained entities):
   - Metadata source for valid-object discovery is missing or ambiguous
   - Live-data requests are generated from synthetic identifiers/objects without metadata validation
   - Discovery-failure policy is unspecified (fail-closed vs explicit unavailable handling)

   **Contract gaps**:
   - Interface contracts missing error response schemas
   - Tool argument types or validation rules not specified

   **Research gaps**:
   - Decisions in research.md marked as chosen but missing rationale
   - Alternatives considered section absent where a non-obvious choice was made
   - Dependency Security section absent or incomplete (missing version pin or CVE rationale for any dependency)

   **Spec traceability**:
   - Functional requirements from spec.md with no corresponding design decision in plan.md
   - Constraints or non-goals in spec.md not reflected in Technical Context

   **Behavior-map sync gaps**:
   - Runtime/config/operator-flow impact is not explicitly assessed in plan.md
   - Impact is identified but no behavior-map update target is specified (`specs/001-auto-options-trader/behavior-map.md`)

   **Domain coverage scan (MANDATORY)**:

   The 17 Domains (`.claude/domains/`) define architectural principles for each concern area. At plan stage, the goal is not to run their subchecklists (those are task-level) but to verify the plan's Architecture Flow and Technical Context address each relevant domain's **core principles and best practices**.

   Step 1 — Identify touched domains from the Architecture Flow and spec (no file reading yet). Mark touched if the signal applies:

   | # | Domain | Touched if… |
   |---|--------|-------------|
   | 01 | API & integration | calls or exposes any external API/service |
   | 02 | Data modeling | new entities, fields, or state transitions |
   | 03 | Data storage | reads or writes any persistent store |
   | 04 | Caching & performance | latency targets or high-frequency data access |
   | 05 | Client/UI | any user-facing interface |
   | 06 | Edge & delivery | routes traffic, serves assets, or sits behind proxy/CDN |
   | 07 | Compute & orchestration | spawns background jobs, workers, or scheduled tasks |
   | 08 | Networking | inter-service communication or service discovery |
   | 09 | Environment & config | new env vars, secrets, or config keys |
   | 10 | Observability | new runtime paths, logging, or metrics |
   | 11 | Resilience | retry, timeout, fallback, or failure recovery paths |
   | 12 | Testing | always |
   | 13 | Identity & access | any authentication or authorization surface |
   | 14 | Security controls | sensitive data, external inputs, or trust boundaries |
   | 15 | Build & deployment | changes CI/CD, deploy scripts, or release process |
   | 16 | Ops & governance | changes runbooks, operator flows, or on-call surface |
   | 17 | Code patterns | introduces new modules, classes, or public symbols |

   Step 2 — For each touched domain, read its file and check **core principles and best practices only** against the plan. Do NOT evaluate subchecklists — those belong at task level. Flag any core principle that the Architecture Flow or Technical Context does not address. Each gap becomes a candidate question in the ambiguity queue (step 5).

   **Domain 01 mandatory FQ promotion (MANDATORY)**: After reading Domain 01, if any async external service node in the Architecture Flow has:
   - Only an outbound edge (no labeled return path edge), OR
   - An execution capability claim that has not been proven (e.g., "service executes CLI subprocess" with no prior spike evidence)

   Then **automatically write** an entry to `plan.md ## Open Feasibility Questions` — do NOT merely add it to Complexity Tracking or the ambiguity queue. These entries cannot be bypassed. Format:
   ```
   - [ ] **FQ-NNN**: Can [service] execute [capability]?
         Probe: [specific test to run — e.g., "provision instance and attempt subprocess.run(['echo','ok'])"]
         Blocking: [which architecture component depends on this capability]
   ```
   Each async return path gap generates a second paired entry:
   ```
   - [ ] **FQ-NNN**: What is the callback/return contract from [service] back to the system after [operation] completes?
         Probe: [describe how the return signal can be observed — endpoint, webhook, polling]
         Blocking: [downstream component that receives the return signal]
   ```

   Step 3 — After scanning all touched domains, add a `## Domain Coverage` table to the plan review output:

   | Domain | Touched | Core Principles Addressed | Gaps Found |
   |--------|---------|--------------------------|------------|
   | 01 API & integration | Yes | ✅ / ⚠️ / ❌ | <gap description or "None"> |
   | ... | ... | ... | ... |

   Any `❌` row is a hard block — the gap must be resolved (either in the plan or via a question to the user) before task generation proceeds. `⚠️` rows are deferred risks that must be flagged in Complexity Tracking.

   **Token efficiency rule**: Only read domain files for touched domains. Never load all 16 globally.

   **Risk assessment**:
   - For each major design decision in plan.md (architecture pattern, dependency choice, integration approach), evaluate:
     - **Novelty risk**: Is this pattern/library new to the codebase, or proven here?
     - **Dependency risk**: Maintenance status, breaking change history, bus factor of the library
     - **Integration risk**: How many trust boundaries does this decision cross?
     - **Reversibility**: How hard is it to change this decision later if it proves wrong?
   - For any decision rated high-risk on 2+ dimensions, ask the user: "Is there a lower-risk alternative?" and present one if identifiable
   - Record risk assessments in Complexity Tracking (add a Risk column) for high-risk items only — do not clutter with low-risk items

5. **Sequential questioning loop** (interactive):
   - Present EXACTLY ONE question at a time
   - For each question, analyze options and provide a **Recommended** answer with brief reasoning (1-2 sentences)
   - Format as: `**Recommended:** [answer] — [reasoning]`
   - For multiple-choice: render options as a Markdown table with a **Story Points** column — estimate the Fibonacci story point delta for each option relative to the current plan baseline (values: 1, 2, 3, 5, 8, 13); allow user to reply with option letter, "yes"/"recommended" to accept, or a short custom answer:

   | Option | Description | Story Points |
   |--------|-------------|--------------|
   | A | <Option A description> | +N pts |
   | B | <Option B description> | +N pts |

   - For short-answer: format as `**Suggested:** [answer] — [reasoning]`; include a one-line story point estimate (e.g., "Est. impact: +0 pts"); allow "yes"/"suggested" to accept
   - Record each accepted answer in working memory; do NOT write to disk until step 6
   - Stop when queue is empty, no material ambiguities remain, or user signals completion ("done", "good", "proceed")
   - Never reveal future queued questions in advance

6. **Write answers back to plan artifacts** after each accepted answer (incremental, atomic saves):
   - Version pin resolved → update `**Technology Direction**` in plan.md Technical Context (note: Technology Selection is filled by /speckit.feasibilityspike, not here)
   - Architecture ambiguity resolved → update the relevant module entry in Project Structure or add an annotation to the Architecture Flow section
   - Repeated-unit ambiguity resolved → update `Repeated Architectural Unit Recognition`
   - Pipeline-stage ambiguity resolved → update `Pipeline Architecture Model`
   - Artifact/event contract ambiguity resolved → update `Artifact / Event Contract Architecture`
   - Plan-to-sketch contract ambiguity resolved → update `Handoff Contract to Sketch`
   - State safety/reconciliation ambiguity resolved → update the `State Ownership/Reconciliation Model` and related invariants in plan.md
   - Local DB transaction ambiguity resolved → update the `Local DB Transaction Model` and related invariants in plan.md
   - Venue-constrained discovery ambiguity resolved → update the `Venue-Constrained Discovery Model` and related live-data request boundaries in plan.md
   - Contract gap resolved → update the relevant file in contracts/
   - Dependency Security gap resolved → update the Dependency Security section in research.md
   - Spec traceability gap → add a note in Technical Context or Complexity Tracking linking spec requirement to design decision
   - Behavior-map sync gap resolved → update `Behavior Map Sync Gate` status/notes in plan.md (including explicit note if behavior-map update is required)
   - Risk assessment finding → add a row to Complexity Tracking with a Risk column annotation; if a lower-risk alternative was accepted, update the corresponding design decision in plan.md
   - Preserve all existing section structure; do not reorder unrelated content
   - Only allowed new content: in-place updates to existing fields or appended rows in existing tables

7. **Validation after each write**:
   - No NEEDS CLARIFICATION markers remain in any updated file
   - No contradictory statements introduced (e.g., two different version pins for same library)
   - Markdown structure valid; no new headings created outside existing plan structure
   - No empty cells remain in the `Behavior Map Sync Gate` table
   - For live-vs-local integrations, no unresolved source-of-truth drift path remains and reconcile checkpoints are explicit
   - For local DB mutation paths, no unresolved transaction-boundary/rollback/idempotency ambiguity remains
   - For venue-constrained integrations, live-data request paths are constrained to metadata-discovered valid objects and discovery-failure policy is explicit

8. **Report completion**:
   - Number of questions asked and answered
   - Files updated (list paths)
   - Any items deferred (low-impact ambiguities the user chose to skip) — note them explicitly
   - If any deferred items could affect task generation, flag them as risks
   - **Plan architecture contract status**: report PASS/PASS WITH NOTES/FAIL for:
     - `Repeated Architectural Unit Recognition`
     - `Pipeline Architecture Model`
     - `Artifact / Event Contract Architecture`
     - `Handoff Contract to Sketch`
   - **Open Feasibility Questions status**: State explicitly whether `plan.md ## Open Feasibility Questions` is empty or non-empty. If non-empty: report the count of FQs written, and which services/capabilities they probe.
   - Emit `planreview_completed` to `.speckit/pipeline-ledger.jsonl`:
     ```json
     {"event": "planreview_completed", "feature_id": "NNN", "phase": "plan", "fq_count": N, "questions_asked": N, "actor": "<agent-id>", "timestamp_utc": "..."}
     ```
   - **If called standalone**:
     - If FQs exist: suggest `/speckit.feasibilityspike` as next step.
     - If no FQs: suggest `/speckit.solution` as next step.
   - **If called as sub-process of `/speckit.plan`**: return control to plan (which auto-invokes feasibilityspike if FQs exist).

## Behavior rules

- Questions are **implementation-facing only** — no business intent or product decisions; those belong in `/speckit.clarify`
- If no material ambiguities found, respond: "No technical ambiguities detected. Plan is ready for task generation." and suggest proceeding to `/speckit.solution`
- Do not invent ambiguities; only flag items genuinely missing precision needed for implementation
- Clarification retries for a single question do not count as new questions
- Respect user early termination signals ("stop", "done", "proceed")
- If unresolved high-impact items remain after user signals done, flag them under Deferred with rationale and risk assessment
- Unresolved live-vs-local drift ambiguity is always high impact and must be flagged as a risk if deferred
- Unresolved local DB transaction-integrity ambiguity is always high impact and must be flagged as a risk if deferred
- Unresolved venue-constrained discovery ambiguity is always high impact and must be flagged as a risk if deferred
