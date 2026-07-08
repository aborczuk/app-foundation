# Shell Hook Guards

This document describes the shell-command guard layer that sits in front of repo-local command execution.

It complements:

- [`docs/governance/read-code-stdio-worker.md`](/Users/andreborczuk/app-foundation/docs/governance/read-code-stdio-worker.md) for search and read-code backend behavior
- [`docs/governance/pipeline-driver-readme.md`](/Users/andreborczuk/app-foundation/docs/governance/pipeline-driver-readme.md) for phase gates and pipeline orchestration

## Purpose

The shell hook guards enforce repo-local command policy before Bash commands run.

They exist to:

- keep code and document reads on the bounded `read_code` and markdown-helper path
- force validation commands through deterministic wrappers
- keep high-volume shell output bounded
- prevent direct shell workflows from bypassing repo-specific process rules

This repo also has a `PostToolUse` edit hook path that runs after `Edit` and `Write`
actions to validate changed files and refresh read-code state.

## Active Hook Entry Point

The active Codex hook registration file is:

- [`.codex/hooks.json`](/Users/andreborczuk/app-foundation/.codex/hooks.json)

Repo-local ownership matters here:

- this repo should not depend on `~/.codex/hooks.json` for its core guard behavior
- the repo-local hook file is the intended source of truth for SessionStart, PreToolUse, and PostToolUse registration in this checkout
- user-level Codex hooks may still exist, but they are not the governance contract for this repo

The active shell guard entrypoint for Bash commands is:

- [`scripts/hook_pretool_dispatch.py`](/Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py)

The dispatcher is registered through the repo-local Codex `PreToolUse` Bash hook and runs the repo guard checks in one process.

## Ownership Split

The shell hook layer owns:

- command-family deny and redirect policy
- bounded-read enforcement for code and docs
- wrapper-only enforcement for selected validation commands

The shell hook layer does not own:

- semantic search ranking, vector retrieval, or reranking
- graph/AST discovery
- pipeline phase routing or ledger state

Those responsibilities remain with:

- `read_code` and MCP/codegraph tooling for search and structural discovery
- pipeline driver and gate scripts for phase progression

## Guard Families

### 1. Read and search guards

Primary enforcement file:

- [`scripts/hook_enforce_code_reads.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_code_reads.py)

This guard enforces the repo reading contract:

- broad root-level `find` scans over code/doc files are denied
- legacy `read_code_symbols` usage is denied
- direct shell reads of repo-local code/doc files are denied
- repo-local `read_code` helper windows over the configured max line count are denied
- repo-local `read_code` helper usage with `--allow-fallback` is denied

Accepted read paths are:

- `read_code_context`
- `read_code_find`
- `read_code_analyze`
- `read_code_window`
- `uv run python scripts/read_markdown.py --headings <file>`
- `uv run python scripts/read_markdown.py <file> "<heading>"`

This guard is the shell-policy layer behind the repo instruction to avoid `grep`, `rg`, `cat`, and broad shell search for normal codebase reading.

### 2. Grep and broad shell-search guards

Primary enforcement file:

- [`scripts/hook_pretool_dispatch.py`](/Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py)

The dispatcher denies:

- direct `grep`
- direct `rg`
- direct `git grep`

The intended replacement is semantic or bounded repo-local reading, not unrestricted text search.

### 3. Refresh-index guard

Primary enforcement file:

- [`scripts/hook_enforce_refresh_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_refresh_guard.py)

This guard denies direct `hook_refresh_indexes.py` usage outside the deterministic edit workflow.

The intended path is:

- `edit_sync`
- `edit_refresh --paths <paths>`

That keeps refresh execution in sequence with validation and edit handoff.

### 4. Type-check guard

Primary enforcement file:

- [`scripts/hook_enforce_pyright_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_pyright_guard.py)

This guard denies direct `pyright` execution.

The intended path is:

- `edit_validate --paths <paths> --tests <selectors>`
- `edit_sync`

That keeps type-checking inside the repo’s deterministic edit validation order.

### 5. Ruff guard

Primary enforcement file:

- [`scripts/hook_enforce_ruff_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_ruff_guard.py)

This guard denies direct `ruff` execution unless the command already routes through the repo wrapper.

The intended path is:

- `edit_validate`
- `uv run --no-sync python scripts/ruff_guard.py <python-paths>`

The wrapper exists to keep lint scope narrow and output bounded.

### 6. Git diff guard

Primary enforcement file:

- [`scripts/hook_enforce_git_diff_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_git_diff_guard.py)

This guard denies direct `git diff`.

The intended path is:

- `python scripts/git_diff_guard.py [diff args]`
- `uv run --no-sync python scripts/git_diff_guard.py [diff args]`

The wrapper exists so diff output stays compact and review-oriented.

### 7. Git worktree and low-level Git safety guard

Primary enforcement file:

- [`scripts/hook_pretool_dispatch.py`](/Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py)

The dispatcher denies:

- `git worktree`
- detached or orphan `git switch` / `git checkout`
- low-level ref plumbing such as `git update-ref` and `git symbolic-ref`

This keeps the repo on named-branch workflows only.

## Command Model

The shell guard layer currently follows a deny-or-wrapper policy:

- deny direct raw command
- require the repo-approved helper or wrapper

For read/search behavior, that means the hook policy is intentionally downstream of the richer repo read stack:

- shell guard decides whether the shell command shape is allowed
- `read_code` / markdown helpers perform the actual bounded read
- MCP/codegraph/vector infrastructure provides the semantic and structural retrieval backend

## Output-Bounding Policy

The guards are designed to support a compact-output operating model:

- direct wide file reads are denied
- direct broad search is denied
- direct diff/lint/type-check commands are denied
- wrapper commands are preferred because they can bound scope and failure output

This is why the wrappers are the intended execution path rather than an optional convenience layer.

## PostToolUse Edit Path

Primary edit hook files:

- [`.codex/hooks.json`](/Users/andreborczuk/app-foundation/.codex/hooks.json)
- [`scripts/hook_posttool_edit_validation.py`](/Users/andreborczuk/app-foundation/scripts/hook_posttool_edit_validation.py)
- [`scripts/hook_refresh_indexes.py`](/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py)

For `Edit|Write` events, the repo-local Codex hook configuration routes through one repo-local script:

- collect repo-local changed paths from the hook payload
- run guarded `ruff` validation for changed Python files
- run guarded `pyright` validation for changed Python files
- run Python docstring validation for changed Python files
- refresh CodeGraph for the smallest covering repo-local scope
- refresh the vector index only for supported changed file types

This path is intentionally fail-closed:

- validation failure stops the edit flow before refresh success can be reported
- refresh failure stops the edit flow even if validation passed
- non-Python edits skip Python-only validation but still run scoped refreshes when applicable

Current local registration shape:

- `SessionStart` with matcher `startup|resume` routes to `.codex/hooks/session_start_context.py`
- `PreToolUse` with matcher `Bash` routes to `scripts/hook_pretool_dispatch.py`
- `PostToolUse` with matcher `Edit|Write` routes to `scripts/hook_posttool_edit_validation.py`

## Practical Reading Order

If you need to trace shell-command policy, read these files in order:

1. [`AGENTS.md`](/Users/andreborczuk/app-foundation/AGENTS.md)
2. [`scripts/hook_pretool_dispatch.py`](/Users/andreborczuk/app-foundation/scripts/hook_pretool_dispatch.py)
3. [`scripts/hook_enforce_code_reads.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_code_reads.py)
4. [`scripts/hook_enforce_refresh_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_refresh_guard.py)
5. [`scripts/hook_enforce_pyright_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_pyright_guard.py)
6. [`scripts/hook_enforce_ruff_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_ruff_guard.py)
7. [`scripts/hook_enforce_git_diff_guard.py`](/Users/andreborczuk/app-foundation/scripts/hook_enforce_git_diff_guard.py)
8. [`docs/governance/read-code-stdio-worker.md`](/Users/andreborczuk/app-foundation/docs/governance/read-code-stdio-worker.md)

That order moves from high-level repo policy to dispatcher logic, then per-command guard rules, then the underlying read backend that the guards are trying to protect.
