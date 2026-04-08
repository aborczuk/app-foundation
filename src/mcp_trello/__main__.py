"""Entry point for running the MCP Trello Bridge server.

Allows invocation via:
    python -m mcp_trello
    python -m mcp_trello.server
"""

from src.mcp_trello.server import main

if __name__ == "__main__":
    main()
