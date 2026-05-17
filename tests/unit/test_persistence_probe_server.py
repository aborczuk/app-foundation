"""Unit tests for the read-code persistence probe MCP server."""

from __future__ import annotations

from pathlib import Path

from src.mcp_codebase.persistence_probe_server import create_server


def test_create_server_captures_one_stable_identity() -> None:
    """The probe server should capture one PID and startup timestamp at construction."""
    server = create_server(project_root=Path.cwd())

    assert server._pid > 0
    assert isinstance(server._started_at, float)
    assert server.mcp.name == "read-code-persistence-probe"
