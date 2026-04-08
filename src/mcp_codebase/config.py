"""Runtime configuration constants for codebase-lsp MCP server."""

from __future__ import annotations

from pathlib import Path

# Project root — overridable at server construction time; default to cwd
PROJECT_ROOT: Path = Path.cwd().resolve()

# Pyright LSP subprocess
PYRIGHT_LSP_COMMAND = "pyright-langserver"
PYRIGHT_LSP_ARGS = ("--stdio",)
LSP_INITIALIZE_TIMEOUT_S = 30
LSP_REQUEST_TIMEOUT_S = 10
LSP_SHUTDOWN_TIMEOUT_S = 5
MAX_RESTART_COUNT = 3

# Diagnostics subprocess
PYRIGHT_CLI_COMMAND = "pyright"
DIAGNOSTICS_TIMEOUT_S = 15

# Logging
LOG_BASE_DIR = Path("logs/codebase-lsp")
