"""Unit tests for the read-code persistence probe MCP server."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.mcp_codebase.persistence_probe_server import create_server


def _extract_tool_payload(tool_result: object) -> dict[str, object]:
    """Extract the JSON object returned by one MCP tool call."""
    if isinstance(tool_result, tuple) and len(tool_result) == 2 and isinstance(tool_result[1], dict):
        return tool_result[1]

    structured = getattr(tool_result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    content = getattr(tool_result, "content", None)
    if content and getattr(content[0], "text", None):
        import json

        payload = json.loads(content[0].text)
        if isinstance(payload, dict):
            return payload

    raise AssertionError("get_process_identity did not return a JSON object")


def test_create_server_captures_one_stable_identity() -> None:
    """The probe server should expose one bounded, stable identity snapshot."""
    server = create_server(project_root=Path.cwd())
    first = asyncio.run(server.mcp.call_tool("get_process_identity", {}))
    second = asyncio.run(server.mcp.call_tool("get_process_identity", {}))
    first_payload = _extract_tool_payload(first)
    second_payload = _extract_tool_payload(second)

    assert first_payload == second_payload
    assert set(first_payload) == {"name", "project_root", "pid", "started_at"}
    assert first_payload["name"] == "read-code-persistence-probe"
    assert first_payload["project_root"] == str(Path.cwd())
    assert first_payload["pid"] > 0
    assert isinstance(first_payload["started_at"], float)
