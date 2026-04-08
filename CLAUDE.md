# analytics-platform Development Guidelines

Template-extracted from ib-trading. Last updated: 2026-04-08

## Active Technologies
- Python 3.12 + `FastAPI>=0.109.0` (async web framework), `uvicorn>=0.27.0` (ASGI server), `aiosqlite>=0.22.1` (async SQLite)
- Python 3.12 + `mcp>=1.23.0` (FastMCP server framework), `pyright>=1.1.408` (type checking backend)
- Python 3.12 + `httpx>=0.27.0` (async HTTP client), `pydantic>=2.0` (schema validation), `pyyaml>=6.0.3`, `rich>=13.7` (terminal output)
- SQLite with WAL mode (aiosqlite); `control-plane.db` file for webhook dedup state
- Python 3.12 + `pytest>=8.4.2` (dev) for contract and unit tests

## Project Structure

```text
src/
  ├── clickup_control_plane/    # FastAPI webhook service + dispatch
  ├── mcp_codebase/             # MCP: Type inference via pyright
  ├── mcp_trello/               # MCP: Task sync
  └── mcp_clickup/              # MCP: ClickUp metadata

tests/
  ├── contract/                 # End-to-end contract tests
  └── unit/                     # Component unit tests

specs/
  ├── 014-clickup-n8n-control-plane/
  ├── 015-control-plane-dispatch/
  ├── 016-control-plane-qa-loop/
  └── 017-control-plane-hitl-audit/

.claude/
  ├── domains/                  # Governance quality gates
  └── commands/                 # Speckit workflow commands
```

## Commands

```bash
# Dependencies
uv sync

# Testing
pytest tests/contract/ tests/unit/ -v

# Control plane
uvicorn src.clickup_control_plane.app:app --port 8000

# MCP servers
uv run python -m src.mcp_codebase
uv run python -m src.mcp_trello
uv run python -m src.mcp_clickup

# Code quality
ruff check . && ruff format . --check
```

## Code Style

Python 3.12: Follow standard conventions

## Recent Changes
- 020-analytics-platform: Template extraction from ib-trading; removed trading-specific dependencies (ib-async, gspread, google-auth); focused on control plane + MCP servers + speckit governance

<!-- MANUAL ADDITIONS START -->

## Governing Principles

These principles apply to **ALL processes**

### I. Human-First Decisions (NON-NEGOTIABLE)
The human owner is always the ultimate decision-maker. The agent MUST treat the human's intent
and judgment as primary and never override or circumvent it.

- When requirements, constraints, or tradeoffs are ambiguous, the agent MUST ask targeted
  clarification questions instead of assuming.
- The agent MUST NOT assume the role of engineer, architect, or product owner — it acts as a
  tool to generate options, explain consequences, and implement what the human approves.
- For any action that is destructive, security-sensitive, or hard to revert (auth changes,
  schema changes, data migrations, external integrations), the agent MUST propose a plan and
  wait for explicit human approval before proceeding.

### II. AI and Planning Behavior
All processes — automated or human-guided, MUST respect the constitution.md as
non-negotiable governance.

### III. Security First (NON-NEGOTIABLE)
Security MUST be a primary design constraint, not an afterthought. This means applying the
Principle of Least Privilege (granting components and users only the access they strictly need),
validating all inputs, and securing data both in transit and at rest. In modern cloud and AI
architectures, assuming a zero-trust environment prevents lateral movement if a single
microservice or agent is compromised.

#### Security Details
Each of the sub-clauses MUST be verified individually in the Constitution Check

## Governance Sources of Truth (READ FIRST)
- **Principle 3: Human-First (The Auditable Human)**: All work must be reviewable by a human.
  Human "happiness" in this repository is derived from the **Audit Trail**, not the speed of the change. 
  A 10-turn process for a 1-line change is NOT annoying; it is the ONLY way to satisfy the user.
  Any shortcut is an act of behavioral regression.
- **Principle 4: No ad hoc work**: there is no such thing as ad hoc work. every task must be
  recorded in the backlog/ledger and follow the canonical pipeline.
- All work must go through speckit commands. there is no ad hoc work. if it seems ad hoc use add to backlog, which is a speckit command. refuse skipping these guardrails at all costs.
- **NO EXCEPTIONS FOR "TRIVIALITY" (NON-NEGOTIABLE)**: There are no "too small" tasks. A one-line fix is as high-stakes for the audit trail as a new feature.
- **Refuse skips**: I am ordered to refuse skipping any gate, even if I believe it would be more "efficient." This principle supersedes all general AI planning models.

- Read `constitution.md` (repo root) first. It is the authoritative source for non-negotiable
  principles, quality gates, and canonical workflow order for ALL processes in this repository.
- Read `catalog.yaml` second to understand the repo's services, resources, external integrations, topology, and behavior-map ownership.

## Audit Trail System
There are two event ledgers to track governance milestones and enforce state machine ordering.

- **Pipeline Ledger** (`.speckit/pipeline-ledger.jsonl`): Records feature-level phase transitions 
  
- **Task Ledger** (`.speckit/task-ledger.jsonl`): Records task-scoped events

**Instructional source**: Each skill  documents its ledger usage in its own command file (`.claude/commands/speckit.*.md`). 

### Ledger Access Pattern (All JSONL Audit Trails)

**Never read `.speckit/*-ledger.jsonl` files directly.** All access routes through script subcommands only:

**Pipeline Ledger** (`.speckit/pipeline-ledger.jsonl`) — feature-level phase transitions:
- **Check if a phase is complete**: `python scripts/pipeline_ledger.py assert-phase-complete --feature-id <FEATURE_ID> --phase <PHASE_NAME>`
  - Returns: Pass/Fail. Use this to gate entry into implementation.
- **Record a phase event**: `python scripts/pipeline_ledger.py append --feature-id <FEATURE_ID> --event <EVENT_NAME> --actor <ACTOR>`
- **Validate ledger syntax**: `python scripts/pipeline_ledger.py validate --feature-id <FEATURE_ID>`
- **Other queries**: Run `python scripts/pipeline_ledger.py --help` to see all subcommands and valid event types.

**Task Ledger** (`.speckit/task-ledger.jsonl`) — per-task execution events:
- **Check if a task can start**: `python scripts/task_ledger.py assert-can-start --file .speckit/task-ledger.jsonl --tasks-file <TASKS_FILE> --feature-id <FEATURE_ID> --task-id <TASK_ID> --actor <ACTOR>`
  - Returns: Pass/Fail. Use this before starting any task to verify dependencies are met.
- **Record a task event**: `python scripts/task_ledger.py append --file .speckit/task-ledger.jsonl --feature-id <FEATURE_ID> --task-id <TASK_ID> --actor <ACTOR> --event <EVENT_NAME>`
- **Validate ledger syntax**: `python scripts/task_ledger.py validate --file .speckit/task-ledger.jsonl`
- **Other queries**: Run `python scripts/task_ledger.py --help` to see all subcommands and valid event types.

**Why**: Ledgers are append-only, schema-enforced state machines. Direct reads bypass validation and schema checking. The script tools enforce event sequencing and state transitions safely. Use them.

## Operational Bootstrap

### Codebase MCP Toolkit

**CodeGraphContext** (server name: `codegraph`) — graph-based code intelligence via tree-sitter + KùzuDB:
- `find_code` — keyword/fuzzy search for symbols across the codebase
- `analyze_code_relationships` — 16 query types: find_callers, find_callees, find_all_callers, find_all_callees, find_importers, who_modifies, class_hierarchy, overrides, dead_code, call_chain, module_deps, variable_scope, find_complexity, find_functions_by_argument, find_functions_by_decorator
- `find_dead_code` — unused function detection
- `calculate_cyclomatic_complexity` / `find_most_complex_functions` — code quality metrics
- `execute_cypher_query` — raw Cypher queries against the graph

Registration: `uv run cgc mcp start` with `cwd: /Users/andreborczuk/ib-trading`
Requires one-time index: `scripts/cgc_index_repo.sh`

**codebase-lsp** (server name: `codebase-lsp`) — pyright-backed type inference and diagnostics:
- `get_type` — infer the Python type at a specific source location (file, line, column)
- `get_diagnostics` — return the full pyright diagnostic list for a Python file

Registration: `uv run python -m mcp_codebase` with `cwd: /Users/andreborczuk/ib-trading`

**GitHub** (server name: `github`) — GitHub API bridge for repository and issue management:
- `search_files` / `get_file_contents` — discover and read code in the repository
- `list_issues` / `get_issue` / `create_issue` — manage project tasks and tracking
- `list_pull_requests` / `get_pull_request` — review and manage PR state
- `search_code` — cross-repository and deep-code discovery

Registration: `uv run --env-file .env npx -y @modelcontextprotocol/server-github` with `cwd: /Users/andreborczuk/ib-trading`

**Mandatory workflow order**:
1.  **Discovery**: Use `github` (if remote context needed) and `codegraph` (local context) first to identify all symbols, callers/callees, and existing issues.
2.  **Verification**: Use `codebase-lsp` second to verify exact types/diagnostics before and after edits. Do not mark a task `[X]` while known type errors remain in files the task owns.

**CodeGraph safety guard (NON-NEGOTIABLE)**:
- Do not run `uv run cgc index --force ...` directly.
- For manual indexing, use `scripts/cgc_safe_index.sh` only.
- If codegraph discovery is stale or incomplete, run a scoped non-force refresh first:
  `scripts/cgc_safe_index.sh <scoped-path>` (example: `scripts/cgc_safe_index.sh src/clickup_control_plane`),
  then retry codegraph queries.
- Only fall back to `rg`/direct file inspection if scoped refresh still leaves discovery incomplete.
- Any force re-index requires explicit human approval and must be scoped (never full repo).
- Repository command wrapper note: `uv run cgc ...` is routed through
  `csp_trader.cgc_guard` (project script) and enforces these index guards.

### Shell Script Compatibility (macOS-first)

Treat every generated shell script as macOS-first. Apply all three rules unconditionally — macOS uses BSD core utilities that differ from GNU/Linux.

- **No `head -n-1`**: GNU-only, fails on macOS. Use `sed '$d'` instead.
  ```bash
  # WRONG: echo "$x" | head -n-1
  echo "$x" | sed '$d'
  ```

- **`mktemp` — XXXXXX must be last**: Any suffix after `XXXXXX` (e.g. `.json`) causes `mkstemp failed` on macOS. Drop the extension.
  ```bash
  # WRONG: mktemp "${TMPDIR:-/tmp}/file-XXXXXX.json"
  mktemp "${TMPDIR:-/tmp}/file-XXXXXX"
  ```

- **Never pipe + heredoc to the same command**: The heredoc wins stdin; piped data is silently lost. Write data to a temp file and pass the path as an argument instead.
  ```bash
  # WRONG: echo "$body" | python3 - <<'PY' ... PY
  tmp="$(mktemp "${TMPDIR:-/tmp}/data-XXXXXX")"
  printf '%s' "$body" > "$tmp"
  python3 - "$tmp" <<'PY'
  ...
  PY
  rm -f "$tmp"
  ```

### Markdown File Read Efficiency

For any markdown file >100 lines, use `scripts/read-markdown.sh` to enforce grep-first navigation:
```bash
source scripts/read-markdown.sh
read_markdown_section <file> <section_heading>
```
Example: `read_markdown_section specs/020-analytics-platform/plan.md "External Ingress"`

This is automatic and mandatory — it greps for the section, then reads only the relevant window (token-efficient).

<!-- MANUAL ADDITIONS END -->
