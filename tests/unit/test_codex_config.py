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


def test_codex_config_registers_semble_mcp_server() -> None:
    """The repo-local Codex config should retain Semble's registered command."""
    config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))
    semble = config["mcp_servers"]["semble"]

    assert semble["command"] == "uv"
    assert semble["args"] == ["run", "semble", "--content", "all"]
    assert semble["cwd"] == "/Users/andreborczuk/app-foundation"
    assert semble["tools"]["search"]["approval_mode"] == "auto"
    assert semble["tools"]["find_related"]["approval_mode"] == "auto"


def test_codex_config_registers_codegraph_and_codebase_lsp_servers() -> None:
    """The repo-local config should register the code intelligence MCP servers."""
    config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))
    codegraph = config["mcp_servers"]["codegraph"]
    codebase_lsp = config["mcp_servers"]["codebase-lsp"]

    assert codegraph == {
        "command": "uv",
        "args": ["run", "cgc", "mcp", "start"],
        "cwd": "/Users/andreborczuk/app-foundation",
    }
    assert codebase_lsp["command"] == "uv"
    assert codebase_lsp["args"] == ["run", "python", "-m", "mcp_codebase"]
    assert codebase_lsp["cwd"] == "/Users/andreborczuk/app-foundation"
    assert codebase_lsp["tools"]["get_diagnostics"]["approval_mode"] == "approve"


def test_codex_config_makes_semble_discovery_automatic() -> None:
    """Semble's read-only discovery tools should not require approval."""
    config = tomllib.loads(Path(".codex/config.toml").read_text(encoding="utf-8"))
    semble_tools = config["mcp_servers"]["semble"]["tools"]

    assert semble_tools["search"]["approval_mode"] == "auto"
    assert semble_tools["find_related"]["approval_mode"] == "auto"


def test_agents_language_guidance_prefers_codegraph_compatible_languages() -> None:
    """The technology guidance should prefer compatible languages and forbid shell code."""
    instructions = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "codegraph acceptable language, preferring more common languages like python" in instructions
    assert "No bash or other direct shell scripting languages" in instructions
