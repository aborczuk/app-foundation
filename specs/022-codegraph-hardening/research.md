# Research: CodeGraph Reliability Hardening

Investigation of prior art, integration patterns, and reusable code/packages that can reduce scope.

---

## Zero-Custom-Server Assessment

What no-server integration options exist? For each, which FRs does it cover?

| Option | FRs covered | How it works | Gap (uncovered FRs) |
|--------|-------------|--------------|---------------------|
| Existing MCP codebase tools (`get_type`, `get_diagnostics`) | FR-002, FR-004, FR-006 | Persistent Pyright LSP for hover-based discovery plus per-call diagnostics subprocess with explicit error envelopes and path validation. | FR-001 health signal, FR-003 last-good snapshot recovery, FR-005 safe rebuild orchestration |
| Safe indexing shell wrappers (`scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh`) | FR-003, FR-004, FR-005, FR-006 | Guarded indexing path refuses unsafe full-repo force rebuilds by default and centralizes repo-local cache / DB locations. | FR-001 deterministic health check output, FR-003 snapshot preservation semantics still need explicit doctor behavior |
| Existing validation harness (`scripts/validate_doc_graph.sh`) | FR-004, FR-006 | Repository-level validation entrypoint for governance/doc graph checks; useful as a smoke-test pattern for reliability gates. | FR-001 graph health classification, FR-003 recovery / rollback semantics |

---

## Repo Assembly Map

Assemble pieces from multiple repositories to cover all FRs. Each row = one repo/file that covers one or more FRs.

| Source (owner/repo) | File(s) to copy/adapt | FRs covered | Notes |
|---------------------|----------------------|-------------|-------|
| `aborczuk/app-foundation` | `src/mcp_codebase/pyright_client.py`, `src/mcp_codebase/type_tool.py`, `src/mcp_codebase/diag_tool.py` | FR-002, FR-004, FR-006 | Existing local MCP discovery path already returns structured error envelopes and keeps Pyright lifecycle isolated. Adapt for explicit healthy/stale/locked status reporting. |
| `aborczuk/app-foundation` | `src/mcp_codebase/security.py` | FR-002, FR-006 | Path canonicalization already distinguishes invalid argument vs out-of-scope vs missing file, which is useful for clear failure modes. |
| `aborczuk/app-foundation` | `src/mcp_codebase/server.py`, `scripts/cgc_safe_index.sh`, `scripts/cgc_index_repo.sh` | FR-001, FR-003, FR-005 | Existing lifecycle and indexing entrypoints are the likely place to add doctor/smoke/rebuild orchestration. |
| `aborczuk/app-foundation` | `scripts/validate_doc_graph.sh` | FR-004, FR-006 | Good repository-level smoke-test / governance validation pattern, though it is not yet a CodeGraph doctor command. |

If no relevant repositories are found, write:
- No relevant code repositories found after searching: [queries run]

**After assembly**: which FRs remain uncovered and require net-new code?
- FR-001: No deterministic CodeGraph health command currently exists; current tools expose discovery and validation, not a single health/status classifier.
- FR-003: Last-known-good snapshot preservation / explicit recovery semantics are not yet surfaced as a first-class CodeGraph doctor flow.
- FR-005: Safe rebuild exists as a guarded index script, but a full safe refresh/recover workflow still needs orchestration and explicit reporting.

---

## Package Adoption Options

Installable packages only (verified via `pip index versions`, `npm view`, or `gh api repos/`). Unverified entries belong in Repo Assembly Map.

| Package | Version | FRs covered | Integration effort | Installability check |
|---------|---------|-------------|-------------------|---------------------|
| None verified in this environment | n/a | n/a | n/a | `pip index versions kuzu` and `pip index versions pyright` both failed due DNS / network resolution errors, so no package adoption options were verified |

---

## Conceptual Patterns

Non-code synthesis from web research. Standard approaches, common patterns, known mistakes.

- **Pattern**: Persistent LSP client with bounded restart / recovery loop — keeps interactive discovery available while isolating hover/diagnostic failures — covers: FR-002, FR-004, FR-006 — requires custom server: yes
  - Source: https://github.com/microsoft/pyright
- **Pattern**: Embedded single-file graph database with WAL / shadow files and explicit lock behavior — preserves last good state and makes stale-lock conditions detectable — covers: FR-003, FR-005 — requires custom server: no
  - Source: https://docs.kuzudb.com/developer-guide/files/
- **Pattern**: Concurrency-aware database access with explicit lock error reporting — prefer clear lock failures over silent corruption or opaque crashes — covers: FR-001, FR-002, FR-006 — requires custom server: no
  - Source: https://docs.kuzudb.com/concurrency/

---

## Search Tools Used

Log which tools and queries ran. Used to diagnose shallow results in future debugging.

- Code Discovery: `find`, `scripts/read-code.sh` on `src/mcp_codebase/server.py`, `pyright_client.py`, `type_tool.py`, `diag_tool.py`, `security.py`; `scripts/cgc_safe_index.sh`; `scripts/cgc_index_repo.sh`; `scripts/validate_doc_graph.sh`
- Package Discovery: `python3 -m pip index versions kuzu`, `python3 -m pip index versions pyright` (both failed with DNS/network resolution errors)
- Conceptual Patterns: WebSearch queries for Kuzu on-disk files, Kuzu concurrency, and Pyright language-server docs; web results used from Kuzu official docs and Pyright repo
- Local Context Mapping: `specs/022-codegraph-hardening/spec.md`, `specs/022-codegraph-hardening/plan.md`, `.claude/commands/speckit.research.md`, `.specify/command-manifest.yaml`

---

## Unanswered Questions

Anything still unknown after all research. These become [NEEDS CLARIFICATION] in plan.md.

- Which user-facing surface should expose the new health/doctor result first: CLI, MCP tool, or both?
- Should a stale graph prefer read-only fallback to direct file reads, or always require an explicit refresh before browsing resumes?
