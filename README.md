# app-foundation

Event-driven application template for Python projects integrating task management automation and code analysis tooling.

**Template Source**: Extracted from [ib-trading](https://github.com/aborczuk/ib-trading) as a reusable foundation for future projects.

## Quick Start

### Prerequisites
- Python 3.12+
- `uv` package manager
- Optional: Docker for n8n deployment

### Clone and Bootstrap

```bash
git clone https://github.com/YOUR-ORG/app-foundation.git
cd app-foundation
uv sync
```

### Start Services

```bash
# Control plane (webhook receiver)
uvicorn src.clickup_control_plane.app:app --host 0.0.0.0 --port 8000

# MCP servers (in separate terminals)
uv run python -m src.mcp_codebase
uv run python -m src.mcp_trello
uv run python -m src.mcp_clickup
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# Contract tests only
pytest tests/contract/ -v

# Unit tests only
pytest tests/unit/ -v
```

## Project Structure

- **src/** — Application code
  - `clickup_control_plane/` — FastAPI webhook service + n8n dispatcher
  - `mcp_*/` — MCP server implementations (Codebase, Trello, ClickUp)
- **tests/** — Contract and unit test suites
- **specs/** — Architecture and governance documentation (014-017)
- **.claude/** — Development governance (domains, speckit commands)
- **.speckit/** — Task and pipeline audit ledgers

## Codebase Vector Index

### Purpose

Provide a repo-local semantic index for bounded helper reads and deterministic symbol/section anchoring.
The index is backed by Chroma + `fastembed` and stored under `.codegraphcontext/db/vector-index/`.

### Inputs

- source files with indexable suffixes (`.py`, `.pyi`, `.md`, `.markdown`, `.mdown`, `.sh`, `.bash`, `.zsh`, `.yaml`, `.yml`)
- repository git state (commit drift + path drift signals)
- helper scope path (`scripts/read-code.sh` or `scripts/read-markdown.sh` request target)

### Execution

1. Build or refresh snapshots with `src.mcp_codebase.indexer` (`build`, `refresh`, `status`, `watch`).
2. Extract structured units from Python, Markdown, Shell, and YAML via `src/mcp_codebase/index/extractors/`.
3. Compute stale status using git-first drift detection with mtime fallback only when git signals are unavailable.
4. During helper preflight, apply scope-aware stale handling:
   - overlap => synchronous scoped refresh
   - no overlap => warning + background scoped refresh + proceed
   - missing/unavailable/probe-failed => fail with remediation

### Output requirements

- quickstart: use `specs/020-codebase-vector-index/quickstart.md` for operator bootstrap and run flow
- verification: run `scripts/e2e_020_codebase_vector_index.sh` and integration coverage in:
  - `tests/integration/test_codebase_vector_index.py`
  - `tests/integration/test_codebase_vector_index_performance.py`
- caveats:
  - stale warnings remain visible (no suppression)
  - codegraph discovery remains language-scoped; non-codegraph types rely on vector/local anchoring
- traceability:
  - spec: `specs/020-codebase-vector-index/spec.md`
  - tasks: `specs/020-codebase-vector-index/tasks.md`
  - implementation/e2e trail: `specs/020-codebase-vector-index/e2e.md`

## Customization

### For a New Project

1. **Update governance files**:
   - `CLAUDE.md` — Replace "app-foundation" with your project name
   - `constitution.md` — Title only (body is domain-agnostic)
   - `catalog.yaml` — Update system name and environment configs
   - `pyproject.toml` — Update project name and description

2. **Configure secrets**:
   - Copy `.env.control-plane.example` to `.env` (local dev)
   - Set `CLICKUP_API_TOKEN`, `CLICKUP_WEBHOOK_SECRET`, `TRELLO_API_KEY`, etc.

3. **Deploy control plane**:
   - Run `docker-compose -f docker-compose.n8n.yml up` for n8n
   - Configure ClickUp webhook in ClickUp Settings → Webhooks
   - Point webhook to your control plane `/webhook` endpoint (port 8000)

4. **Run speckit pipeline**:
   ```bash
   /speckit.specify "Your feature description"
   /speckit.research
   /speckit.plan
   # ... continue with speckit workflow
   ```

## Testing

Contract tests verify the control plane webhook → dispatch flow with mocked ClickUp events:

```bash
pytest tests/contract/test_clickup_control_plane_contract.py -v
```

Unit tests cover component logic:

```bash
pytest tests/unit/ -v
```

## Configuration

### Environment Variables

**Required**:
- `CLICKUP_API_TOKEN` — ClickUp workspace API token
- `CLICKUP_WEBHOOK_SECRET` — HMAC signing secret (from ClickUp webhook registration)

**Optional**:
- `CONTROL_PLANE_DB_PATH` — SQLite database path (default: `.speckit/control-plane.db`)
- `TRELLO_API_KEY` — Trello API key (for MCP Trello server)
- `TRELLO_TOKEN` — Trello auth token
- `TRELLO_BOARD_ID` — Default Trello board ID

### Control Plane Routes

- `POST /webhook` — Receive ClickUp webhook events (HMAC-verified)
- `POST /control-plane/build-spec` — Dispatch to n8n build-spec workflow
- `POST /control-plane/qa-loop` — Dispatch to n8n qa-loop workflow

## Governance

This repository follows the **app-foundation Pipeline Constitution** — a zero-trust, human-first, security-first development process. See `constitution.md` for non-negotiable governance principles.

Task management and pipeline governance is driven by speckit — a specification-driven workflow for feature development. All work is tracked in `.speckit/` ledgers (append-only audit trail).

## Deployment

### Production Environment

See `docker-compose.n8n.yml` for n8n reference deployment. Suggested platforms:
- **Control Plane**: AWS ECS, Digital Ocean App Platform, or Heroku
- **n8n**: Self-hosted Docker on Digital Ocean or AWS EC2

### Local Development

All services run locally with mocked external integrations:

```bash
# Terminal 1: Control plane
uvicorn src.clickup_control_plane.app:app --host 0.0.0.0 --port 8000

# Terminal 2: MCP Codebase
uv run python -m src.mcp_codebase

# Terminal 3: Tests
pytest tests/ -v
```

## License

[Copy license from ib-trading or create new per your project]

## Related Projects

- **ib-trading** (source template): [GitHub link](https://github.com/aborczuk/ib-trading)
- **speckit** (governance pipeline): Integrated in `.claude/commands/`
- **FastMCP**: MCP server framework
- **FastAPI**: Async web framework

---

**Template maintained by**: [Your name/team]  
**Last updated**: 2026-04-08  
**Version**: 1.0.0
