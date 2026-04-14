"""Test module."""

from __future__ import annotations

import sys
from pathlib import Path

# pytest configuration for mcp_trello tests
# asyncio_mode = "auto" is set in pyproject.toml [tool.pytest.ini_options]

# Ensure repo-local imports like `src.mcp_codebase.*` resolve during pytest
# collection when the runner does not automatically include the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_STR = str(REPO_ROOT)
if REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, REPO_ROOT_STR)
