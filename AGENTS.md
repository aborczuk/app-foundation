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


### Progressive load routing
- Treat this file as the route map, not the full knowledge base.
- Prefer the smallest task-specific artifact first: `scripts/read-code.sh`, `scripts/read-markdown.sh`, or the relevant `.claude/commands/*.md`.
- Read `catalog.yaml` for system topology, services, resources, auth, hosting, or dependency questions.
- Read `specs/*/behavior-map.md` only for runtime behavior and `specs/*/tasks.md` only for task state and execution order.
- Commands in pipeline: /Users/andreborczuk/app-foundation/command-manifest.yaml

### Function docs
- Function docstrings or comments are mandatory for new or modified functions.
- Keep them short, specific, and colocated with the function they describe.
- Any code edit that changes behavior should add or update nearby documentation (eg quickstart.md)explaining the function or work, unless the change is trivially self-evident.

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

**RG, grep and other direct tools are banned in this repo by hook. don't waste your time trying. Use instead:**

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
- Repository command wrapper note: `uv run cgc ...` is routed through `csp_trader.cgc_guard` (project script) and enforces these index guards.

**CodeGraph directories (canonical)**:
- `.codegraphcontext/` — single canonical CodeGraph home for this repo.
  - `config.yaml` and optional `.env`: repo-local configuration
  - `db/`: generated runtime/index artifacts (Kuzu/Falkor files, sockets)
  - `.uv-cache/`: CodeGraph uv cache when scripts set `CGC_UV_CACHE_DIR`


### Markdown File Read Efficiency

For markdown files, use `scripts/read-markdown.sh`; the detailed vector-first anchoring and how-to live in `scripts/read_markdown.sh` and `scripts/read_markdown.py`.
- When the exact heading is not already known, run `read_markdown_headings` first, then `read_markdown_section` with the exact heading title.
- Prefer `--help` once for unfamiliar helper scripts before trialing flags.
- Single-file serialization is required: do not run parallel markdown reads against the same file.
- Avoid overlapping section pulls from the same file in the same step; reuse already-read context instead.

### Code File Read Efficiency

For any code file, use `scripts/read-code.sh` to enforce semantic-first, windowed reads. 80 lines is the max context_lines budget:
```bash
source scripts/read-code.sh
read_code_context <file> <symbol_or_pattern> [context_lines]
```
Examples:
- `read_code_context src/clickup_control_plane/webhook_auth.py \"def verify_signature\" 80`

Use this workflow:
1. If file seam/anchor is unknown, run `read_code_context` with the best likely anchor and use semantic ranking (`--next-candidate` / `--candidate-index`) to iterate candidates.
2. If file seam/anchor is already known, go directly to `read_code_context` / `read_code_window` with bounded context.
3. Use exact symbols (or known anchors) with `read_code_context` / `read_code_window` for seam anchoring.
4. The helper resolves semantic lookup first and then performs exact bounded reads.
   - `read_code_context` applies a fixed asymmetric split: small pre-anchor context and larger post-anchor context
5. Run codegraph discovery checks for blast radius only after the seam is confirmed.
6. Expand to additional windows only when needed to resolve ambiguity.
7. If read preflight reports a missing/stale vector DB, bootstrap it first: `uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap`.
8. Read preflight hard-fail is vector-owned for repo-local reads; do not continue when vector health is failing.
9. Codegraph read preflight is session-scoped availability probe only (no per-read codegraph refresh).
10. Vector stale handling is scope-aware and explicit:
   - stale + overlap with requested scope => synchronous scoped refresh, then proceed/fail
   - stale + no overlap => warning remains visible, no refresh is launched, read proceeds
   - missing/unavailable/probe-failed => hard fail with remediation

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
- Anchor policy is semantic-first: if semantic returns a strong candidate, that candidate is the anchor of record and the bounded window is rendered from that line.
- Codegraph refresh is discovery-owned: run codegraph refresh when invoking codegraph discovery features, not as a per-read window preflight.
- Use broad discovery only when the target file is unknown; once the file is known, semantic retrieval must stay file-scoped for seam anchoring.
- If the selected semantic candidate is weak, evaluate the next ranked semantic candidate(s) before strict matching.
- Strict matching is fallback-only and should run only when semantic cannot provide a strong anchor; strict ambiguity must not block a strong semantic anchor.
- Symbol dumps are not part of standard workflow; use semantic anchor + bounded window reads instead.
- Break-glass symbol dumps live only in `scripts/read_code_debug.py` and require explicit maintenance intent.
- `context_lines` is a total context budget with a fixed small-before/larger-after split.
- The confidence cutoff for inline body output is `90/100` when `--inline-body` is requested.
- A non-top candidate body should only be returned through the bounded follow-up helper path.
- Keep the shell wrapper, Python helper, and docs aligned with the same contract when the behavior changes.

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

### Token efficiency

After each pipeline command or long running command, report if there were large token uses that could have been optimized and how. If there were not, report that
- Large-token operations must be explicitly called out immediately after execution (for example: large `read_code_symbols` dumps, broad codegraph content searches, or full-table outputs).
- Prefer bounded reads and narrow queries first; escalate to broad outputs only when smaller reads cannot resolve the decision.
- Read budget guard is mandatory: cap combined helper read output at 160 lines per step (markdown + code).
- If the step budget is reached, stop new reads and reuse previously captured context first.
- Only exceed the budget on explicit necessity (`changed_file` or unresolved `ambiguity`), and state the reason before the extra read.

### Healing and improvment
- Do not swallow errors or inconsistencies with scripts. if things break do not just fall back to inventing new tools. stop and propose a fix
