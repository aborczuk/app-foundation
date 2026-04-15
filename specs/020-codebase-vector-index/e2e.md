# E2E Testing Pipeline: Codebase Vector Index

This pipeline validates the full local vector-index workflow end to end:
local repo content is indexed into the vector database, queries return actionable
symbol/section results, refreshes preserve the last good snapshot, and freshness
reporting exposes staleness before agents trust results.

---

## Prerequisites

- `.codegraphcontext/config.yaml`: repo-local config must exist and be readable.
- `uv`: required to run the project interpreter and the E2E script.
- Local repository checkout: required so `pipeline_driver.py` and the tests can
  inspect the current working tree.

---

## Recommended Pipeline (Run This)

Use the pipeline script instead of manual commands:

```bash
# Full E2E flow
scripts/e2e_020_codebase_vector_index.sh full <config>

# Preflight only (dry-run, no side effects)
scripts/e2e_020_codebase_vector_index.sh preflight <config>

# Run specific user story sections
scripts/e2e_020_codebase_vector_index.sh run <config>

# Print verification commands
scripts/e2e_020_codebase_vector_index.sh verify <config>

# CI-safe non-interactive checks only
scripts/e2e_020_codebase_vector_index.sh ci <config>
```

---

## Section 1: Preflight (Dry-Run Smoke Test)

**Purpose**: Confirm the driver resolves the feature and the repo-local config is
usable without mutating the index.
**External deps**: None beyond the repo checkout and `uv`.

1. Run the pipeline driver in dry-run mode for the current feature.
   - Verify: JSON output reports `phase=solution` or later with `dry_run=true`
     and no ledger writes.

---

## Section 2: User Story 1 - Semantic Symbol Lookup

**Purpose**: Validate ranked code-symbol search returns file path, line range,
signature, and docstring-ready provenance.
**External deps**: Local index build and the code-symbol query surface.

**User asks before starting**:
- [ ] Repo checkout is current enough to build the index
- [ ] Local index artifacts are writable under `.codegraphcontext/`

**Steps**:
1. Build or refresh the local index over `src/` and `tests/`.
   - Verify: build completes successfully and writes metadata.
2. Query a known code concept.
   - Verify: top result includes name, docstring, signature, file path, and line
     range.
3. Query nonsense input.
   - Verify: empty result set is returned without error.

**Pass criteria**: Code-symbol lookup returns a ranked, provenance-rich result and
the empty-query path fails closed to an empty list.

---

## Section 3: User Story 2 - Markdown Section Discovery

**Purpose**: Validate markdown topic search returns breadcrumb, preview, and file
path enough for direct section reads.
**External deps**: Local markdown indexing over `specs/` and `.claude/`.

**User asks before starting**:
- [ ] Repo markdown sources are present
- [ ] The index includes markdown sections from `specs/` and `.claude/`

**Steps**:
1. Query a governance/spec topic phrase.
   - Verify: returned result includes header breadcrumb, content preview, and
     file path.
2. Consume the result with the markdown read helper.
   - Verify: breadcrumb + path are sufficient for direct section reading.

**Pass criteria**: Markdown discovery returns breadcrumb-rich sections that map
directly to a read target.

---

## Section 4: User Story 3 - Incremental Update on Code Change

**Purpose**: Validate local edits trigger incremental refresh and interrupted
refreshes preserve the last good snapshot.
**External deps**: Watcher or on-demand refresh path and write access to the
index store.

**User asks before starting**:
- [ ] Refresh trigger can observe local file edits
- [ ] The repository can write a staged snapshot under `.codegraphcontext/`

**Steps**:
1. Edit a source file and trigger refresh.
   - Verify: the updated symbol is present in query results after refresh.
2. Simulate an interrupted refresh.
   - Verify: the previous snapshot remains queryable and no partial state is
     exposed.
3. Confirm generated artifacts remain excluded.
   - Verify: `__pycache__` and `.pyc` paths never appear in the index.

**Pass criteria**: Refresh is incremental, safe, and preserves the active snapshot
on failure.

---

## Section 5: User Story 4 - Staleness Check

**Purpose**: Validate freshness reporting tells the caller when the index lags
behind HEAD.
**External deps**: Current HEAD comparison and stored index metadata.

**User asks before starting**:
- [ ] The index was built at a known commit
- [ ] The repo can advance to a later commit for the check

**Steps**:
1. Advance the working tree from the recorded build commit.
   - Verify: status reports the index as stale with a commit delta.
2. Check status without changing HEAD.
   - Verify: status reports the index as up to date.

**Pass criteria**: Freshness is visible and actionable from the service and
operator workflow.

---

## Section 6: Full Feature E2E

**Purpose**: Validate the entire vector-index workflow together.
**Runs**: After the per-story sections pass.

**Steps**:
1. Run preflight.
2. Run the code-symbol lookup checks.
3. Run the markdown section checks.
4. Run the refresh/recovery checks.
5. Run the staleness check.
6. Validate the pipeline ledger.

**Pass criteria**: All story sections pass, the ledger validates, and the final
workflow stays local-only and deterministic.

---

## Verification Commands

```bash
uv run python scripts/pipeline_driver.py --feature-id 020 --dry-run --json
uv run python -m pytest tests/integration/test_codebase_vector_index.py -q
uv run python scripts/pipeline_ledger.py validate
```

---

## Common Blockers

- **Config missing**: Symptom: preflight fails before any story section starts.
  Fix: create or repair `.codegraphcontext/config.yaml`.
- **Index stale**: Symptom: query results point to older symbols or sections.
  Fix: run the refresh/update path and re-run preflight.
- **Refresh interrupted**: Symptom: active snapshot is missing or partial.
  Fix: rerun refresh; the previous snapshot should still be queryable.
