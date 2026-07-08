"""Regression tests for the post-edit index refresh hook."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path
from typing import Any


def _load_hook_module(monkeypatch) -> Any:
    """Load the refresh hook while simulating an environment without pydantic."""
    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pydantic":
            raise ModuleNotFoundError("No module named 'pydantic'", name="pydantic")
        return original_import(name, globals, locals, fromlist, level)

    hook_path = Path(__file__).resolve().parents[2] / "scripts" / "hook_refresh_indexes.py"
    module_name = "hook_refresh_indexes_no_pydantic"

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "src.mcp_codebase.index.config", raising=False)
    monkeypatch.delitem(sys.modules, "src.mcp_codebase", raising=False)

    spec = importlib.util.spec_from_file_location(module_name, hook_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hook_refresh_indexes_loads_without_pydantic(monkeypatch) -> None:
    """The hook should still import when the host interpreter lacks repo-only deps."""
    module = _load_hook_module(monkeypatch)

    assert module.DEFAULT_EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"
    assert module.DEFAULT_EMBEDDING_CACHE_DIR == Path(
        ".codegraphcontext/global/db/vector-index/fastembed-cache"
    )


def test_collect_changed_paths_parses_apply_patch_payload(monkeypatch) -> None:
    """The refresh hook should derive changed files from apply_patch payloads."""
    module = _load_hook_module(monkeypatch)
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {
            "patch": (
                "*** Begin Patch\n"
                "*** Update File: /Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py\n"
                "@@\n"
                "-old\n"
                "+new\n"
                "*** End Patch\n"
            ),
        },
    }

    changed_paths = module._collect_changed_paths(payload)

    assert changed_paths == [
        Path("/Users/andreborczuk/app-foundation/scripts/hook_refresh_indexes.py")
    ]
