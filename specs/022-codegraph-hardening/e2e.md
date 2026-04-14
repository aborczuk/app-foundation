# E2E Testing Pipeline: CodeGraph Reliability Hardening

Validates the local CodeGraph/Kuzu health and recovery surface end-to-end, including the doctor flow, recovery guidance, safe refresh/rebuild behavior, and timeout-budget checks.

---

## Prerequisites

- [External service 1]: [how to verify it's running]
- [Config file]: [how to create from example]
- [Env vars]: [which ones, what they do — NEVER include actual values]

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_022_codegraph_hardening.sh full <config>

# Preflight only (dry-run, no external deps needed beyond the app)
scripts/e2e_022_codegraph_hardening.sh preflight <config>

# Run specific user story section
scripts/e2e_022_codegraph_hardening.sh run <config>

# Print verification commands
scripts/e2e_022_codegraph_hardening.sh verify <config>

# CI-safe non-interactive checks only
scripts/e2e_022_codegraph_hardening.sh ci <config>
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate the app starts, loads config, and completes a cycle without side effects  
**External deps**: None (uses --dry-run or equivalent)

1. [Step]: [What to do]
   - Verify: [What "good" looks like]

---

## Section 2: [User Story 1 Title] (Priority: P1)

**Purpose**: [What this section validates]  
**External deps**: [What must be running]

**User asks before starting**:
- [ ] [External service] is running and accessible
- [ ] [Config] is set up correctly
- [ ] [Any other prerequisite the human must confirm]

**Steps**:
1. [Step]: [What to do]
   - Verify: [automated check — log event, DB query, exit code]
2. [Step]: [What to do]
   - **Human verify (only if needed)**: [thing only a human can check — UI state, external tool]
   - Reason manual is required: [why deterministic automation is not reliable yet]

**Pass criteria**: [Automated gates required; include human gate only where documented as non-automatable]

---

## Section N: [User Story N Title]

[Same pattern as Section 2]

---

## Section Final: Full Feature E2E

**Purpose**: Validate all user stories work together end-to-end  
**Runs**: After all stories are implemented, and after every significant change

**User asks before starting**:
- [ ] All per-story E2E sections have passed at least once
- [ ] [All external deps running]

**Steps**:
1. Run preflight (automated)
2. [Story 1 flow]
3. [Story 2 flow — building on state from story 1]
4. [Cross-story integration checks]
5. [Graceful shutdown / cleanup verification]

**Pass criteria**: [All automated gates pass; required human gates pass where no deterministic oracle exists]

---

## Verification Commands

```bash
[Useful commands for inspecting state — log tails, DB queries, etc.]
```

---

## Common Blockers

- **[Blocker]**: Symptom: [what you see]. Fix: [how to resolve].
