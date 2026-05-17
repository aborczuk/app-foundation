"""Compatibility wrapper for the project-local MCP backend server."""

from __future__ import annotations

from src.mcp_codebase.project_backend_server import ProjectBackendServer, create_server, main

__all__ = ["ProjectBackendServer", "create_server", "main"]
