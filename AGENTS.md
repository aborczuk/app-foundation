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
- Any code edit that changes behavior should add or update documentation explaining the function or work (eg quickstart.md), unless the change is trivially self-evident.

## Technology choices
- all new code should be written in python so it is viable in codegraph. No bash or other direct shell scripting languages

## Operational Bootstrap

### Codebase MCP Toolkit

**CodeGraphContext** (server name: `codegraph`) — graph-based code intelligence via tree-sitter + Redis (FalkorDB module, via redislite).

Start server: `uv run cgc mcp start` (runs in foreground; stop with Ctrl+C or background with `&`)

**codebase-lsp** (server name: `codebase-lsp`) — pyright-backed type inference and diagnostics:
- `get_type` — infer the Python type at a specific source location (file, line, column)
- `get_diagnostics` — return the full pyright diagnostic list for a Python file

Registration: `uv run python -m mcp_codebase` with `cwd: /Users/andreborczuk/app-foundation`

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Operational Bootstrap

### Codebase Reading and Discovery

Use repository `read_code.py` instead of `grep`, `ripgrep`, `cat`, or broad shell search. Direct text-search tools are banned in this repo by hook.

Pick the query mode by what you need:

- `context` as the default lookup mode for natural-language descriptions, symbols, strings, or the best matching seam.
- `find` when you want exact structural matches or need to enumerate occurrences of a known symbol, pattern, or text.
- `analyze` after you have a candidate and need callers, callees, dependencies, or structural context.

Primary tools:

- `scripts/read_code.py` — unified reader for Python, shell, YAML, Markdown, and code-like files. It exposes both structural search and semantic context lookup.
- `codebase-lsp` — type inference and diagnostics for Python files.


### Code Reading Workflow

Read code by intent, not by guessing file windows.

1. **Start with `context` **
   - Use `uv run python scripts/read_code.py context` for EVERYTHING. natural-language queries, symbols, strings, markdown, or the best matching seam. It will get you to some starting confidence to explore from.


   Examples:

  ```bash
   uv run python scripts/read_code.py context "how read_code resolves semantic candidates"
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

4. **For code symbols, Find Call Sites and Usages with Graph Discovery (The Standard Next Step)**

   Once `context` or `find` returns a result with a `unit_id`, use read_code's analyze mode to find where it's called:

   ```bash
   uv run python scripts/read_code.py analyze callers "_resolve_pattern_anchor"      # Find all functions that call this
   uv run python scripts/read_code.py analyze calls "read_code_context"              # Find all functions this calls
   uv run python scripts/read_code.py analyze variable "vector_candidates"           # Find where a variable is used
   ```

   The compact match output will hint which analysis to run next.

5. **You can dig for more context within a file with the same function and optional file path**

   Examples:

   ```bash
   uv run python scripts/read_code.py context "_resolve_pattern_anchor" --path src/mcp_codebase/read_code.py
   ```

6. **Advanced Graph Analysis (when needed)**

   Use `read_code analyze` to map blast radius, inheritance, imports, dead-code, and other structural questions.

   - Do not use broad `find content` for reassurance once the relevant file or seam is already known; prefer `analyze` or a narrower `context` query.

   Examples:

   ```bash
   uv run python scripts/read_code.py analyze deps "src.mcp_codebase.read_code"      # Module dependencies
   uv run python scripts/read_code.py analyze tree "SomeClass"                        # Inheritance hierarchy
   uv run python scripts/read_code.py analyze dead-code                               # Unused functions
   ```

   **Find commands** (`read_code find`):
- `name <symbol>` — exact name match for functions, classes, variables
- `pattern <substring>` — substring matching across symbols
- `type <type_name>` — all elements of a specific type (function, class, etc.)
- `variable <name>` — find variables and their usage
- `content <query>` — full-text search of code and docstrings
- `decorator <name>` — find functions with a specific decorator
- `argument <param_name>` — find functions that take a specific parameter

Examples:
```bash
uv run python scripts/read_code.py find name "_emit_strict_resolution_failure"
uv run python scripts/read_code.py find pattern "vector_match"
uv run python scripts/read_code.py find content "semantic search"
```

**Analyze commands** (`read_code analyze`):
- `callers <symbol>` — find all functions that call this function
- `calls <symbol>` — find all functions this function calls
- `chain <func1> <func2>` — show call chain between two functions
- `deps <module>` — show dependencies and imports for a module
- `tree <class>` — show inheritance hierarchy for a class
- `complexity` — show cyclomatic complexity for functions
- `dead-code` — find potentially unused functions and classes
- `overrides <method>` — find all implementations of a method across classes
- `variable <name>` — analyze where a variable is defined and used

7. **After using context to get a seam, for Markdown symbols, use this dig workflow:**

   - Use `context` for bounded markdown discovery through the semantic reader first.

   - Use `read_markdown_headings` when you need markdown structure discovery: `uv run python scripts/read_markdown.py --headings <file>` — lists headings with line numbers.
   - Use `read_markdown_section` when you need an exact heading title: `uv run python scripts/read_markdown.py <file> "<exact heading title>"` — reads one markdown section. Use sparingly because it can be extra tokens.
   
   - This keeps markdown reads bounded and intent-driven, just like code reads.

8. If read preflight reports a missing/stale vector DB, bootstrap it first: `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap`.


### Edit Efficiency

- Use `scripts/edit_code.py` to edit code in this repo:
```bash
uv run python scripts/edit_code.py validate --paths <touched-paths> --tests <pytest-selectors>
uv run python scripts/edit_code.py sync --paths <touched-paths> --tests <pytest-selectors> --commit-message "<coherent-edit-message>"
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
- Validation loop: targeted tests for the touched behavior via `uv run --no-sync python scripts/pytest_guard.py run -- <pytest args>`, codebase-lsp diagnostics for touched Python files, and `uv run ruff check` (via `scripts/ruff_guard.py <python-paths>` when applicable).
- Guard I/O pattern for all new wrappers and validators:
  - accept narrow, structured inputs only; prefer explicit file paths, task ids, feature ids, or selectors over broad repo scans
  - print a compact summary first, then a bounded failure excerpt, and always provide a log or artifact path for the full output
  - never dump full success output by default
  - on failure, cap printed output and report how to retrieve the full artifact or raise the cap explicitly
  - prefer one-item-at-a-time or shortlist stepping for discovery-style outputs instead of full tables or long lists
  - if a wrapper emits a persisted artifact (log, payload, result), downstream steps should carry forward a compact decision summary and reread the full artifact only when it changed or a contradiction appears
- For task completion, use the unified handoff and closeout flow:
  ```bash
  uv run python scripts/edit_code.py sync --paths <paths> --tests <tests> --commit-message "<message>" --handoff --feature-id <FID> --task-id <TID>
  ```
- This unified command handles technical validation (tests/lint), behavioral QA (via `speckit_behavioral_qa.py`), ledger auditing, and GitHub syncing.
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
