"""FastMCP stdio server that reports one stable process identity."""

from __future__ import annotations

import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP


class PersistenceProbeServer:
    """Expose one MCP tool that returns this server process identity."""

    def __init__(self, *, project_root: Path) -> None:
        """Capture a stable startup timestamp and register one probe tool."""
        self._project_root = project_root.resolve()
        self._pid = os.getpid()
        self._started_at = time.time()
        self.mcp = FastMCP("read-code-persistence-probe")
        self._register_tools()

    def _register_tools(self) -> None:
        """Register the single persistence probe tool."""
        server_ref = self

        @self.mcp.tool()
        async def get_process_identity() -> dict[str, object]:
            """Return the current server process identity for persistence checks."""
            return {
                "name": "read-code-persistence-probe",
                "project_root": str(server_ref._project_root),
                "pid": server_ref._pid,
                "started_at": server_ref._started_at,
            }


def create_server(*, project_root: Path | None = None) -> PersistenceProbeServer:
    """Create the FastMCP persistence probe server."""
    return PersistenceProbeServer(project_root=project_root or Path.cwd())


def main() -> None:
    """Run the persistence probe MCP server over stdio."""
    create_server().mcp.run()


if __name__ == "__main__":
    main()
