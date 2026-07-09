from __future__ import annotations

import tomllib
from pathlib import Path


def test_codex_config_registers_context7_mcp_server() -> None:
    """The repo-local Codex config should register Context7 as a remote MCP server."""
    config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))
    context7 = config["mcp_servers"]["context7"]

    assert context7["url"] == "https://mcp.context7.com/mcp"
    assert context7["tools"]["resolve-library-id"]["approval_mode"] == "auto"
    assert context7["tools"]["query-docs"]["approval_mode"] == "auto"


def test_codex_config_registers_composio_mcp_server() -> None:
    """The repo-local Codex config should let Codex use Composio OAuth."""
    config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))
    composio = config["mcp_servers"]["composio"]

    assert composio["url"] == "https://connect.composio.dev/mcp"
    assert "http_headers" not in composio
    assert "env_http_headers" not in composio
