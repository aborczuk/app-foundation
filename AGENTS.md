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

### Function docs
- Function docstrings or comments are mandatory for new or modified functions.
- Keep them short, specific, and colocated with the function they describe.
- Any code edit that changes behavior should add or update nearby documentation (eg quickstart.md)explaining the function or work, unless the change is trivially self-evident.

## Technology choices
- all new code should be written in python so it is viable in codegraph. No bash or other direct shell scripting languages

## Operational Bootstrap

### Codebase MCP Toolkit

**CodeGraphContext** (server name: `codegraph`) — graph-based code intelligence via tree-sitter + Redis (FalkorDB module, via redislite).

Start server: `uv run cgc mcp start` (runs in foreground; stop with Ctrl+C or background with `&`)

**Find commands** (`cgc find`):
- `name <symbol>` — exact name match for functions, classes, variables
- `pattern <substring>` — substring matching across symbols
- `type <type_name>` — all elements of a specific type (function, class, etc.)
- `variable <name>` — find variables and their usage
- `content <query>` — full-text search of code and docstrings
- `decorator <name>` — find functions with a specific decorator
- `argument <param_name>` — find functions that take a specific parameter

Examples:
```bash
uv run cgc find name "_emit_strict_resolution_failure"
uv run cgc find pattern "vector_match"
uv run cgc find content "semantic search"
```

**Analyze commands** (`cgc analyze`):
- `callers <symbol>` — find all functions that call this function
- `calls <symbol>` — find all functions this function calls
- `chain <func1> <func2>` — show call chain between two functions
- `deps <module>` — show dependencies and imports for a module
- `tree <class>` — show inheritance hierarchy for a class
- `complexity` — show cyclomatic complexity for functions
- `dead-code` — find potentially unused functions and classes
- `overrides <method>` — find all implementations of a method across classes
- `variable <name>` — analyze where a variable is defined and used

Examples:
```bash
uv run cgc analyze callers "_resolve_pattern_anchor"
uv run cgc analyze calls "read_code_context"
uv run cgc analyze dead-code
```

Requires one-time index: `scripts/cgc_index_repo.sh`

**codebase-lsp** (server name: `codebase-lsp`) — pyright-backed type inference and diagnostics:
- `get_type` — infer the Python type at a specific source location (file, line, column)
- `get_diagnostics` — return the full pyright diagnostic list for a Python file

Registration: `uv run python -m mcp_codebase` with `cwd: /Users/andreborczuk/app-foundation`


**RG, grep and other direct tools are banned in this repo by hook. don't waste your time trying. Use instead:**

**Mandatory workflow order**:
1. **Semantic search**: 
   - **Code**: `uv run python scripts/read_code.py context <query>` for natural language queries or symbol names.
   - **Markdown**: `uv run python scripts/read_markdown.py --headings <file>` for discovery, then `uv run python scripts/read_markdown.py <file> "<heading>"` for sections.
   - Both run semantic vector lookup first, then exact anchor matching. Return file path, signature/heading, summary, and confidence scores.
2. **Intensive read**: Add flags like `--inline-body` to get full function bodies, `--next-candidate`/`--candidate-index N` to walk ranked alternatives, `--show-shortlist` to see top candidates.
3. **Discovery checks**: Use `codegraph` after finding code to map callers/callees/imports/blast radius (plus `github` if remote context is needed).

**CodeGraph directories (canonical)**:
- `.codegraphcontext/` — single canonical CodeGraph home for this repo.
  - `config.yaml` and optional `.env`: repo-local configuration
  - `db/`: generated runtime/index artifacts (Kuzu/Falkor files, sockets)
  - `.uv-cache/`: CodeGraph uv cache when scripts set `CGC_UV_CACHE_DIR`


### Markdown File Read Efficiency

For markdown files, use `uv run python scripts/read_markdown.py` with vector-first anchoring:
- For discovery: `uv run python scripts/read_markdown.py --headings <file>` lists all headings first.
- For sections: `uv run python scripts/read_markdown.py <file> "<heading>"` retrieves specific sections.
- Single-file serialization is required: do not run parallel markdown reads against the same file.
- Avoid overlapping section pulls from the same file in the same step; reuse already-read context instead.

### Code File Read Efficiency

For any code file, use `uv run python scripts/read_code.py` to enforce semantic-first, windowed reads. 80 lines is the max context_lines budget:
```bash
uv run python scripts/read_code.py context <symbol_or_pattern> [--path <file>] [context_lines]
uv run python scripts/read_code.py window <file> <start_line> [line_count]
```
Examples:
- `uv run python scripts/read_code.py context "def verify_signature" --path src/clickup_control_plane/webhook_auth.py 80`
- `uv run python scripts/read_code.py window src/clickup_control_plane/webhook_auth.py 42 60`

Use this workflow:
1. If file seam/anchor is unknown, run `read_code.py context` with your best anchor guess and use `--next-candidate` / `--candidate-index` to iterate ranked candidates.
2. If file seam/anchor is already known, go directly to `read_code.py context` or `read_code.py window` with bounded context.
3. Use exact symbols (or known anchors) with `read_code.py context` / `read_code.py window` for seam anchoring.
4. The helper resolves semantic lookup first and then performs exact bounded reads (context defaults to compact output; use `--inline-body` for full bodies).
5. Run codegraph discovery checks for blast radius only after the seam is confirmed.
6. Expand to additional windows only when needed to resolve ambiguity.
7. If read preflight reports a missing/stale vector DB, bootstrap it first: `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap`.

Verification/read intensity must scale with task size:
- Single-constant or single-branch edits: one anchor read plus at most one follow-up window; avoid broad discovery.
- Single-file, moderate edits: bounded seam windows and candidate stepping; avoid broad reads.
- Multi-file/refactor/blast-radius changes: use codegraph discovery after seam confirmation to map impact.
- Do not use broad `uv run cgc find content ...` for reassurance when file + seam are already known.
- Single-file serialization is required for code reads as well: do not run parallel `read_code_*` calls against the same file.

### Read-Code Rules

Use the shortlist/body contract when reading code with the helper.

- `read_code_context` defaults to resolved anchor + bounded window output (no shortlist by default).
- The visible shortlist is capped at 5 candidates when `--show-shortlist` is requested.
- Use `--next-candidate` (or `--candidate-index N`) to step ranked candidates without forcing shortlist output.
- Use broad discovery only when the target file is unknown; once the file is known, semantic retrieval must stay file-scoped for seam anchoring.
- If the selected semantic candidate is weak, evaluate the next ranked semantic candidate(s) before strict matching.
- `context_lines` is a total context budget with a fixed small-before/larger-after split.

Full-file reads are disallowed unless the user explicitly requests full contents.

### Edit Efficiency

- Use `scripts/edit-code.sh` to edit code in this repo:
```bash
source scripts/edit-code.sh
edit_validate --paths <touched-paths> --tests <pytest-selectors>
edit_sync --paths <touched-paths> --tests <pytest-selectors> --commit-message "<coherent-edit-message>"
```
- Replace `<touched-paths>` with the files changed in the edit batch, and `<pytest-selectors>` with the minimal targeted tests for that batch.
- Read the exact seam once before editing.
- Work seam-by-seam: finish one seam before starting another.
- Default to the smallest coherent edit batch that keeps the seam clear: one file when practical, or a tightly related set of files when that avoids repeated refresh/index overhead.
- Prefer one high-quality seam read per active file (function/class level) and derive the full file edit plan from that snapshot.
- Apply one consolidated patch per file when possible instead of many tiny hunks.
- For multi-file work, prepare edits from initial seam reads, apply file-by-file, then run one targeted validation pass for the batch.
- Use `apply_patch` for small local edits.
- Use scripted transforms for repetitive mechanical edits across many files; do not hand-edit the same mechanical change file-by-file.
- Reread only on concrete signals: patch failure, failing tests/lint/LSP diagnostics, or explicit ambiguity from the diff.
- After each edit batch, run a validation loop before starting the next batch.
- Validation loop: targeted tests for the touched behavior via `uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>`, codebase-lsp diagnostics for touched Python files, and `uv run --no-sync python scripts/ruff_guard.py <python-paths>` when applicable.
- Raw `ruff` CLI invocations are blocked by PreToolUse hook; use `edit_validate` or `scripts/ruff_guard.py`.
- Raw `pytest`, `pyright`, and `hook_refresh_indexes.py` CLI invocations are blocked by PreToolUse hook; use `edit_validate` / `edit_sync` flow (or `scripts/pytest_guard.py` where explicitly needed).
- Raw `git diff` CLI invocations are blocked by PreToolUse hook; use `python scripts/git_diff_guard.py [diff args]` for bounded diff inspection.
- Do not advance past an edit batch until its validation loop passes or the failure is understood and intentionally deferred.
- Verify once after the patch set is complete as a final end-to-end pass, not instead of batch-level validation.
- Treat a completed edit as the basic unit of work: keep the patch set coherent, verify it, then hand it off as one synced change.
- If codegraph is only needed after the batch, prefer finishing the batch first and then running the refresh hook once; if a later codegraph read overlaps the changed scope, the read helper's stale detection will force the needed scoped refresh before you rely on it.

### Final Edit Handoff

- Finish with local verification, run `uv run python scripts/hook_refresh_indexes.py` once with the batch's changed-path JSON payload on stdin, then commit and push so the branch is synced.
- Commit once per completed edit unit; small, well-described commits are the basic unit of maintainable code.
- Commit messages should describe one coherent edit unit clearly and narrowly.
- Do not split one logical edit across multiple unsynced handoffs unless the user explicitly wants an intermediate checkpoint.
- Edit-done checklist:
  - targeted tests for the touched behavior
  - tests run through `uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>`
  - `codebase-lsp` diagnostics for touched Python files
  - `uv run --no-sync python scripts/ruff_guard.py <python-paths>` on touched Python paths when applicable
  - `uv run python scripts/hook_refresh_indexes.py` with the changed-path JSON payload on stdin
  - commit the coherent edit unit
  - push so the branch is synced
