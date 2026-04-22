# Codex Agent Instructions for app-foundation

# Here are the critical principles:
## Human-First Decisions (NON-NEGOTIABLE)
- the human owner is the ultimate decision-maker
- ask targeted clarification when requirements are ambiguous
- do not assume engineer / architect / product-owner roles
- for destructive, security-sensitive, or hard-to-revert changes, propose a plan and wait for explicit approval
## I. Security First
## II. Reuse at Every Scale
## III. Spec and process-First (NON-NEGOTIABLE)
## IV. Test Driven Verification First (NON-NEGOTIABLE)
- Integration tests must not rely only on fake/mocked backends for critical runtime paths.
- For infrastructure-critical flows (for example `read-code`, vector index, and codegraph discovery), every mocked contract test must have at least one live-backend verification test.
- Do not label tests as integration if they only stub external/runtime dependencies; mark those as contract/simulation tests and keep live verification separate.
- For more details : 
- **Core Principles & 16 Domains**: [constitution.md](file:///Users/andreborczuk/app-foundation/constitution.md)
- **Command Definitions**: [.claude/commands/](file:///Users/andreborczuk/app-foundation/.claude/commands/)

## Audit Trail System
There are two event ledgers to track governance milestones and enforce state machine ordering.

- **Pipeline Ledger** (`.speckit/pipeline-ledger.jsonl`): Records feature-level phase transitions
- **Task Ledger** (`.speckit/task-ledger.jsonl`): Records task-scoped events

Each skill documents ledger usage in its own command file (`.claude/commands/speckit.*.md`).

### Ledger Access Pattern (All JSONL Audit Trails)

Never read `.speckit/*-ledger.jsonl` files directly. All access routes through script subcommands only:

- **Pipeline Ledger** (`.speckit/pipeline-ledger.jsonl`) — feature-level phase transitions:
  - **Check if a phase is complete**: `uv run python scripts/pipeline_ledger.py assert-phase-complete --feature-id <FEATURE_ID> --event <EVENT_NAME>`
  - **Record a phase event**: `uv run python scripts/pipeline_ledger.py append --feature-id <FEATURE_ID> --event <EVENT_NAME> --actor <ACTOR>`
  - **Validate ledger syntax**: `uv run python scripts/pipeline_ledger.py validate`
  - **Other queries**: Run `uv run python scripts/pipeline_ledger.py --help` to see all subcommands and valid event types.
- **Task Ledger** (`.speckit/task-ledger.jsonl`) — per-task execution events:
  - **Check if a task can start**: `uv run python scripts/task_ledger.py assert-can-start --file .speckit/task-ledger.jsonl --tasks-file <TASKS_FILE> --feature-id <FEATURE_ID> --task-id <TASK_ID> --actor <ACTOR>`
  - **Record a task event**: `uv run python scripts/task_ledger.py append --file .speckit/task-ledger.jsonl --feature-id <FEATURE_ID> --task-id <TASK_ID> --actor <ACTOR> --event <EVENT_NAME>`
  - **Validate ledger syntax**: `uv run python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl`
  - **Other queries**: Run `uv run python scripts/task_ledger.py --help` to see all subcommands and valid event types.

### Deterministic workflow gate checks
- Canonical command catalog lives in `constitution.md` `## Quality Gates`. Keep command docs and scripts aligned there.

### Progressive load routing
- Treat this file as the route map, not the full knowledge base.
- Prefer the smallest task-specific artifact first: `scripts/read-code.sh`, `scripts/read-markdown.sh`, or the relevant `.claude/commands/*.md`.
- Read `catalog.yaml` for system topology, services, resources, auth, hosting, or dependency questions.
- Read `specs/*/behavior-map.md` only for runtime behavior and `specs/*/tasks.md` only for task state and execution order.
- Use `codegraph` for relationship/blast-radius questions after a seam is anchored.
- Use `codebase-lsp` for exact type and diagnostic checks before or after edits.

### Function docs
- Function docstrings or comments are mandatory for new or modified functions.
- Keep them short, specific, and colocated with the function they describe.
- Any code edit that changes behavior should add or update nearby documentation explaining the function or work, unless the change is trivially self-evident.

## Technology choices
- all new code should be written in python so it is viable in codegraph. No bash or other direct shell scripting languages

## Operational Bootstrap

### Codebase MCP Toolkit

**CodeGraphContext** (server name: `codegraph`) — graph-based code intelligence via tree-sitter + Redis (FalkorDB module, via redislite):
- `find_code` — keyword/fuzzy search for symbols across the codebase
- `analyze_code_relationships` — 16 query types: find_callers, find_callees, find_all_callers, find_all_callees, find_importers, who_modifies, class_hierarchy, overrides, dead_code, call_chain, module_deps, variable_scope, find_complexity, find_functions_by_argument, find_functions_by_decorator
- `find_dead_code` — unused function detection
- `calculate_cyclomatic_complexity` / `find_most_complex_functions` — code quality metrics
- `execute_cypher_query` — raw Cypher queries against the graph

Registration: `uv run cgc mcp start` with `cwd: /Users/andreborczuk/app-foundation`
Requires one-time index: `scripts/cgc_index_repo.sh`

**codebase-lsp** (server name: `codebase-lsp`) — pyright-backed type inference and diagnostics:
- `get_type` — infer the Python type at a specific source location (file, line, column)
- `get_diagnostics` — return the full pyright diagnostic list for a Python file

Registration: `uv run python -m mcp_codebase` with `cwd: /Users/andreborczuk/app-foundation`

**GitHub** (server name: `github`) — GitHub API bridge for repository and issue management:
- Use for repository code/issue/PR discovery when remote context is required.
- Registration: `uv run --env-file .env npx -y @modelcontextprotocol/server-github` (`cwd: /Users/andreborczuk/app-foundation`)

**Mandatory workflow order**:
1. **Helper-driven read**: Start with `scripts/read-code.sh` / `scripts/read-markdown.sh` for anchored bounded reads.
2. **Semantic+exact semantics (internal)**: Those helpers run semantic lookup first, then exact seam anchoring.
3. **Discovery checks**: Use `codegraph` after the seam is anchored to map callers/callees/imports/blast radius (plus `github` if remote context is needed).
4. **Verification**: Use `codebase-lsp` to verify exact types/diagnostics before and after edits. Do not mark a task `[X]` while known type errors remain in files the task owns.

**CodeGraph safety guard (NON-NEGOTIABLE)**:
- Do not run `uv run cgc index --force ...` directly.
- Post-edit refreshes go through `uv run python scripts/hook_refresh_indexes.py` with the changed-path JSON payload on stdin; the hook fans out to codegraph/vector refreshes for the changed paths.
- For manual indexing, use `scripts/cgc_safe_index.sh` only.
- If codegraph discovery is stale or incomplete, run a scoped non-force refresh first:
  `scripts/cgc_safe_index.sh <scoped-path>` (example: `scripts/cgc_safe_index.sh src/clickup_control_plane`),
  then retry codegraph queries.
- Only fall back to `rg`/direct file inspection if scoped refresh still leaves discovery incomplete.
- Any force re-index requires explicit human approval and must be scoped (never full repo).
- Repository command wrapper note: `uv run cgc ...` is routed through `csp_trader.cgc_guard` (project script) and enforces these index guards.

**CodeGraph directories (canonical)**:
- `.codegraphcontext/` — single canonical CodeGraph home for this repo.
  - `config.yaml` and optional `.env`: repo-local configuration
  - `db/`: generated runtime/index artifacts (Kuzu/Falkor files, sockets)
  - `.uv-cache/`: CodeGraph uv cache when scripts set `CGC_UV_CACHE_DIR`

### Shell Script Compatibility (macOS-first)

Treat every generated shell script as macOS-first. Apply all three rules unconditionally — macOS uses BSD core utilities that differ from GNU/Linux.

- **No `head -n-1`**: GNU-only, fails on macOS. Use `sed '$d'` instead.
  ```bash
  # WRONG: echo \"$x\" | head -n-1
  echo \"$x\" | sed '$d'
  ```

- **`mktemp` — XXXXXX must be last**: Any suffix after `XXXXXX` (e.g. `.json`) causes `mkstemp failed` on macOS. Drop the extension.
  ```bash
  # WRONG: mktemp \"${TMPDIR:-/tmp}/file-XXXXXX.json\"
  mktemp \"${TMPDIR:-/tmp}/file-XXXXXX\"
  ```

- **Never pipe + heredoc to the same command**: The heredoc wins stdin; piped data is silently lost. Write data to a temp file and pass the path as an argument instead.
  ```bash
  # WRONG: echo \"$body\" | python3 - <<'PY' ... PY
  tmp=\"$(mktemp \"${TMPDIR:-/tmp}/data-XXXXXX\")\"
  printf '%s' \"$body\" > \"$tmp\"
  python3 - \"$tmp\" <<'PY'
  ...
  PY
  rm -f \"$tmp\"
  ```

- **Quote args consistently**: Prefer double quotes around arguments containing `'`; otherwise use POSIX escaping (`'\\''`).

### Markdown File Read Efficiency

For markdown files, use `scripts/read-markdown.sh`; the detailed vector-first anchoring and how-to live in `scripts/read_markdown.sh` and `scripts/read_markdown.py`.
- When the exact heading is not already known, run `read_markdown_headings` first, then `read_markdown_section` with the exact heading title.
- Prefer `--help` once for unfamiliar helper scripts before trialing flags.

### Code File Read Efficiency

For any code file, use `scripts/read-code.sh` to enforce symbol-first, windowed reads. 110 lines is the max context_lines:
```bash
source scripts/read-code.sh
read_code_symbols <file>
read_code_context <file> <symbol_or_pattern> [context_lines]
```
Examples:
- `read_code_symbols src/clickup_control_plane/webhook_auth.py`
- `read_code_context src/clickup_control_plane/webhook_auth.py \"def verify_signature\" 110`

Use this workflow:
1. Invoke `read_code_symbols` first to list deterministic file-local symbols (header/signature + line bounds) from the vector snapshot.
2. Use one of those exact symbols with `read_code_context` / `read_code_window` for seam anchoring.
3. The helper resolves semantic lookup first and then performs exact bounded reads.
4. Run codegraph discovery checks for blast radius only after the seam is confirmed.
5. Expand to additional windows only when needed to resolve ambiguity.
6. If read preflight reports a missing/stale vector DB, bootstrap it first: `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap`.
7. Read preflight is strict hard-fail for repo-local reads; do not continue on fallback warnings.

Full-file reads are disallowed unless the user explicitly requests full contents.

### Token efficiency

After each pipeline command or long running command, report if there were large token uses that could have been optimized and how. If there were not, report that

### Healing and improvment
- Do not swallow errors or inconsistencies with scripts. if things break do not just fall back to inventing new tools. stop and propose a fix

### Edit Efficiency

- Use `scripts/edit-code.sh` when you want deterministic validation/refresh/sync sequencing for a coherent edit unit:
```bash
source scripts/edit-code.sh
edit_validate --paths scripts/read_code.py tests/unit/test_read_code_index_refresh.py --tests tests/unit/test_read_code_index_refresh.py
edit_sync --paths scripts/read_code.py tests/unit/test_read_code_index_refresh.py --tests tests/unit/test_read_code_index_refresh.py --commit-message "Describe coherent edit"
```
- Read the exact seam once before editing.
- Work seam-by-seam: finish one seam before starting another.
- Default to one-file edit batches: complete one file’s coherent change + validation loop before moving to the next file.
- Prefer one high-quality seam read per active file (function/class level) and derive the full file edit plan from that snapshot.
- Apply one consolidated patch per file when possible instead of many tiny hunks.
- For multi-file work, prepare edits from initial seam reads, apply file-by-file, then run one targeted validation pass for the batch.
- Use `apply_patch` for small local edits.
- Use scripted transforms for repetitive mechanical edits across many files; do not hand-edit the same mechanical change file-by-file.
- Reread only on concrete signals: patch failure, failing tests/lint/LSP diagnostics, or explicit ambiguity from the diff.
- After each edit batch, run a validation loop before starting the next batch.
- Validation loop: targeted tests for the touched behavior via `uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>`, codebase-lsp diagnostics for touched Python files, and `uv run ruff check` on the touched Python paths when applicable.
- Do not advance past an edit batch until its validation loop passes or the failure is understood and intentionally deferred.
- Verify once after the patch set is complete as a final end-to-end pass, not instead of batch-level validation.
- Treat a completed edit as the basic unit of work: keep the patch set coherent, verify it, then hand it off as one synced change.

### Final Handoff

- When the user asks for a completed change, finish with local verification, run `uv run python scripts/hook_refresh_indexes.py` with the changed-path JSON payload on stdin, then commit and push so the branch is synced.
- Commit once per completed edit unit; small, well-described commits are the basic unit of maintainable code.
- Commit messages should describe one coherent edit unit clearly and narrowly.
- Do not split one logical edit across multiple unsynced handoffs unless the user explicitly wants an intermediate checkpoint.
- Edit-done checklist:
  - targeted tests for the touched behavior
  - tests run through `uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>`
  - `codebase-lsp` diagnostics for touched Python files
  - `uv run ruff check` on touched Python paths when applicable
  - `uv run python scripts/hook_refresh_indexes.py` with the changed-path JSON payload on stdin
  - commit the coherent edit unit
  - push so the branch is synced
