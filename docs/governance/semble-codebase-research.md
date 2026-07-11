# Semble Codebase Research Governance

## Purpose

Semble provides the first-pass codebase research backend for agents in this repository: it turns a focused query into bounded file and line anchors before any local file window, read-code semantic lookup, or CodeGraph structural analysis spends additional tokens.

## Active Design

- Server entrypoint: `uv run semble`
- Transport: MCP stdio when launched by Codex or Claude from repo configuration
- Process owner: the current agent session that loads the `semble` MCP server
- Registered MCP tools: `search` and `find_related`
- CLI diagnostic surface: `uv run --no-sync semble search ...` and `uv run --no-sync semble find-related ...`
- Workspace cache: `/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache`

Repo MCP configuration must set:

```text
command = "uv"
args = ["run", "semble"]
cwd = "/Users/andreborczuk/app-foundation"
SEMBLE_CACHE_LOCATION = "/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache"
```

Do not run Semble through `uvx` for this repo. `uvx` uses user-level tool directories that are outside the managed workspace sandbox and can create recurring permission failures.

## Key Runtime Symbols

- `.codex/config.toml` / `mcp_servers.semble`: Codex MCP registration and workspace cache environment.
- `.claude/settings.json` / `mcpServers.semble`: Claude MCP registration and workspace cache environment.
- `semble.mcp:create_server`: upstream Semble MCP server factory.
- `semble.mcp:_IndexCache`: upstream in-process index cache for the lifetime of the MCP server.
- `semble.cache:resolve_cache_folder`: upstream cache location resolver; this must respect `SEMBLE_CACHE_LOCATION`.
- `semble.index.dense:load_model`: upstream model loader for the active dense model.
- `.codegraphcontext/semble-cache/`: repo-local on-disk Semble index cache; ignored by Git.

## Model And Runtime Policy

- Active model: `minishlab/potion-code-16M-v2`
- Backend wrapper: Semble uses `model2vec.StaticModel` through `semble.index.dense.load_model`.
- Device selection policy: Semble/model2vec owns device selection internally; this repo does not override device or precision.
- Precision policy: Semble/model2vec default precision; this repo does not set a precision flag.
- Cache/warmup policy: first Semble search loads the model and builds an index for the requested repo/content set; later MCP calls reuse the in-process index and the workspace on-disk cache.

## Ownership Split

Semble owns:

- first-pass candidate search
- related-code candidate discovery from an anchored file and line
- repo index build and reuse inside the Semble MCP process
- on-disk Semble cache layout under `SEMBLE_CACHE_LOCATION`

Agents own:

- writing focused queries
- keeping `max_snippet_lines=0` until a candidate is chosen
- opening only bounded local windows for selected anchors
- deciding when to pivot from related-code discovery to structural analysis

`scripts/read_code.py` owns:

- bounded local file windows after Semble anchoring
- fallback semantic lookup when Semble is unavailable
- existing scratchpad candidate stepping for read-code results

CodeGraph owns:

- callers, callees, dependencies, hierarchy, and blast-radius analysis
- graph refresh and stale-state handling

## Current Reuse Boundary

Guaranteed now:

- One loaded Semble MCP server can reuse its in-process model and index cache during that agent session.
- Separate Semble CLI calls reuse the repo-local on-disk cache when `SEMBLE_CACHE_LOCATION` points at `.codegraphcontext/semble-cache`.
- The workspace cache avoids user-level cache permission errors for Semble index writes.

Not guaranteed now:

- A new Codex or Claude session automatically sees Semble until the session reloads MCP configuration.
- A separate CLI invocation shares the MCP process memory cache.
- Semble's index freshness is the same as CodeGraph freshness; each system owns its own cache/freshness boundary.
- Semble replaces CodeGraph structural analysis.

## Verified Behavior

The install was verified with the repo-managed runtime:

```bash
SEMBLE_CACHE_LOCATION=/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache \
  uv run --no-sync semble search "spec workflow governance" . -k 5 --max-snippet-lines 0 --content code docs config
```

This returned bounded file and line anchors without body dumps.

The related-code surface was verified with:

```bash
SEMBLE_CACHE_LOCATION=/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache \
  uv run --no-sync semble find-related scripts/hook_pretool_dispatch.py 1 . -k 2 --max-snippet-lines 0 --content code config
```

This returned related file and line anchors.

The MCP-style entrypoint was verified by launching `uv run semble` with the workspace cache environment and confirming the process stayed running without stderr cache-permission errors.

## Runtime Setup

1. Ensure `pyproject.toml` and `uv.lock` include `semble[mcp]`.
2. Ensure `.codex/config.toml` and `.claude/settings.json` register `semble` with `uv run semble`.
3. Ensure both MCP entries set `SEMBLE_CACHE_LOCATION=/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache`.
4. Restart or reload the agent session so the `semble` MCP server is visible.
5. Warm the index with a bounded anchor-only search:

   ```bash
   SEMBLE_CACHE_LOCATION=/Users/andreborczuk/app-foundation/.codegraphcontext/semble-cache \
     uv run --no-sync semble search "task validator format gate" . -k 5 --max-snippet-lines 0 --content code docs config
   ```

## Expected Cold Starts

1. First run after dependency install may download the active model from Hugging Face.
2. First search for this repo/content set builds the Semble index and writes it to `.codegraphcontext/semble-cache`.
3. Repeated MCP calls in the same session should reuse the in-process index.
4. Repeated CLI probes should reuse the workspace on-disk index but still start a new Python process.

## Operational Risks

- If `SEMBLE_CACHE_LOCATION` is missing, Semble may try to write under `~/Library/Caches/semble`, which is outside the managed workspace sandbox.
- If Semble is launched with `uvx`, uv may try to write under user-level tool directories outside the managed workspace sandbox.
- If a model download is interrupted, the Hugging Face model snapshot can be partial; remove only the Semble model cache and rerun.
- Semble query strings passed through shell commands can still trip repo shell guards if they include denied command names; prefer MCP tools when the session exposes them.
- Semble scores are ranking signals, not absolute confidence values.

## Agent Discovery Contract

1. Run Semble `search` first with a focused query and `max_snippet_lines=0`.
2. If a candidate is close but incomplete, run Semble `find_related` from the candidate file and line.
3. Open a bounded local window only for the selected anchor.
4. Use `scripts/read_code.py context` only when Semble is unavailable or when a focused semantic follow-up is needed.
5. Use CodeGraph only after anchoring when the question is structural: callers, callees, dependencies, hierarchy, or blast radius.

## Where To Change It

- MCP registration: `.codex/config.toml` and `.claude/settings.json`
- Dependency/runtime version: `pyproject.toml` and `uv.lock`
- Workspace cache ignore: `.gitignore`
- Agent instructions: `AGENTS.md`
- Shell-denial guidance: `scripts/hook_pretool_dispatch.py` and `scripts/hook_enforce_code_reads.py`
- Upstream Semble cache/model behavior: installed `semble` package or upstream `MinishLab/semble`
