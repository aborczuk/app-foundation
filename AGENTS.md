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

Requires one-time index: `scripts/cgc_index_repo.sh`

**codebase-lsp** (server name: `codebase-lsp`) — pyright-backed type inference and diagnostics:
- `get_type` — infer the Python type at a specific source location (file, line, column)
- `get_diagnostics` — return the full pyright diagnostic list for a Python file

Registration: `uv run python -m mcp_codebase` with `cwd: /Users/andreborczuk/app-foundation`


**RG, grep and other direct tools are banned in this repo by hook. don't waste your time trying. Use instead:**

## Operational Bootstrap

### Codebase Reading and Discovery

Use repository read helpers instead of grep, ripgrep, cat, or broad shell search. Direct text-search tools are banned in this repo by hook.

Primary tools:

- `scripts/read_code.py` — read Python, shell, YAML, and code-like files.
- `scripts/read_markdown.py` — read Markdown files.
- `codegraph` — graph discovery after a relevant code anchor is found.
- `codebase-lsp` — type inference and diagnostics for Python files.

### Code Reading Workflow

Read code by intent, not by guessing file windows.

1. **Start with a natural-language query**
   - Use `uv run python scripts/read_code.py context` with a natural-language query, symbol name, or behavior description.
   - Let the helper perform semantic lookup first and return the best matching result.

   Examples:

  ```bash
   uv run python scripts/read_code.py context "how read-code resolves semantic candidates"
   uv run python scripts/read_code.py context "_resolve_pattern_anchor"
  ```
2. **Inspect ranked results sequentially**
    - It returns one result at a time.
    - If the first result is not the right seam, step through candidates by using --next-candidate or --candidate-index N.

   Examples:

   ```bash
   uv run python scripts/read_code.py context "semantic candidate resolution" --next-candidate
   uv run python scripts/read_code.py context "semantic candidate resolution" --candidate-index 2
   ```
3. **Dig for Body**
    - If you believe it is the right candidate, send --inline-body to get the body of the function

   Examples:

   ```bash
   uv run python scripts/read_code.py context "_resolve_pattern_anchor" --inline-body
   ```

4. **Optionally Use CodeGraph only after the seam is known and if more comprehensive understanding is required**

   - Use `codegraph` to map blast radius, callers, callees, inheritance, imports, or dead-code questions.

   - Do not use broad `cgc find content` for reassurance once the relevant file or seam is already known.

   Examples:

   ```bash
   uv run cgc analyze callers "_resolve_pattern_anchor"
   uv run cgc analyze calls "read_code_context"
   uv run cgc analyze deps "src.mcp_codebase.read_code"
   ```

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
5. Optionally use window in read-markdown.py or read-code.py to extend the context

6. If read preflight reports a missing/stale vector DB, bootstrap it first: `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap`.


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
