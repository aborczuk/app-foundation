# E2E Testing Pipeline: Read-Code Anchor Output Simplification

This pipeline validates the feature end to end: helper-first reads, shortlist-plus-confidence output, body-first behavior for highly confident hits, and the bounded follow-up path for non-top candidates.

---

## Prerequisites

- `uv`: check with `uv --version`
- Repository checkout: make sure you are at the repo root
- Read helper shell scripts: `scripts/read-code.sh` and `scripts/read-markdown.sh`
- A populated codebase index for semantic retrieval
- Repo-local `uv` cache support via `scripts/uv_cache_dir.sh`

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_025_intent_anchor_routing.sh config.yaml full

# Preflight only (dry-run, no external deps needed beyond the app)
scripts/e2e_025_intent_anchor_routing.sh config.yaml preflight

# Run specific user story section
scripts/e2e_025_intent_anchor_routing.sh config.yaml run

# Print verification commands
scripts/e2e_025_intent_anchor_routing.sh config.yaml verify

# CI-safe non-interactive checks only
scripts/e2e_025_intent_anchor_routing.sh config.yaml ci
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Validate the repo-local helper path works and the read helpers can load without a cache permission failure.

**External deps**: None beyond the repository and `uv`.

1. Source `scripts/uv_cache_dir.sh`.
   - Verify: `UV_CACHE_DIR` points at `.codegraphcontext/.uv-cache`.
2. Run a bounded symbol listing against `scripts/read_code.py`.
   - Verify: the helper returns deterministic symbols.

---

## Section 2: Ranked Shortlist and Inline Top Body (Priority: P1)

**Purpose**: Validate shortlist output, normalized confidence, and body-first behavior for the highest-confidence match.

**External deps**: Healthy vector index.

**User asks before starting**:
- [ ] `uv` is available
- [ ] The vector index is healthy
- [ ] `scripts/read-code.sh` is sourced

**Steps**:
1. Run `read_code_context scripts/read_code.py "read_code_context" 125`.
   - Verify: output remains bounded and symbol-anchored.
2. Confirm the shortlist/body contract is visible in the helper output.
   - Verify: the top candidate is preferred when confidence is high enough.

**Pass criteria**: The helper returns the shortlist contract deterministically and does not exceed the bounded read limit.

---

## Section 3: Bounded Follow-Up Body Helper (Priority: P2)

**Purpose**: Validate a non-top shortlist candidate can be revisited through a bounded follow-up path.

**External deps**: Healthy vector index.

**User asks before starting**:
- [ ] The shortlist/body contract from Section 2 has been exercised
- [ ] The helper can resolve the relevant symbol

**Steps**:
1. Re-run the helper with an alternate anchored symbol or candidate.
   - Verify: the follow-up read is still bounded and does not require a full-file read.

**Pass criteria**: Follow-up access stays scoped and bounded.

---

## Section 4: Agent Rules and Quickstart (Priority: P3)

**Purpose**: Validate the repo guidance points readers to the correct cache-safe helper path and read limits.

**External deps**: None beyond the repository.

**User asks before starting**:
- [ ] `AGENTS.md` is readable
- [ ] `specs/025-intent-anchor-routing/quickstart.md` is present

**Steps**:
1. Read the read-code guidance from `AGENTS.md`.
   - Verify: the max context limit is `125` and the repo-local cache helper is documented.
2. Confirm the quickstart explains the feature at a glance.
   - Verify: it links to `tasks.md` and the spec folder.

**Pass criteria**: The operator guidance matches the current helper behavior.

---

## Section Final: Full Feature E2E

**Purpose**: Validate all sections together.

**Runs**: After all stories are implemented, and after every significant change.

**User asks before starting**:
- [ ] All per-story sections have passed at least once
- [ ] The vector index is healthy

**Steps**:
1. Run preflight.
2. Run Sections 2 through 4.
3. Verify the helper and docs agree on the cache-safe read workflow.

**Pass criteria**: All automated checks pass and the guidance matches the implementation.

---

## Verification Commands

```bash
source scripts/uv_cache_dir.sh
source scripts/read-code.sh
read_code_symbols scripts/read_code.py
read_code_context scripts/read_code.py "read_code_context" 125
source scripts/read-markdown.sh
read_markdown_section AGENTS.md "Code File Read Efficiency"
```

---

## Common Blockers

- **Stale vector index**: Symptom: helper emits stale warnings or refuses to anchor. Fix: refresh the scoped index and retry.
- **UV cache permission issue**: Symptom: `uv` tries to use `~/.cache/uv` and fails. Fix: source `scripts/uv_cache_dir.sh` or export `UV_CACHE_DIR` before launching `uv`.
- **Missing helper script**: Symptom: the e2e pipeline script is absent or named unexpectedly. Fix: keep the canonical file at `scripts/e2e_025_intent_anchor_routing.sh`.
