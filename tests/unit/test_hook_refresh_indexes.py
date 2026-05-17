"""Regression tests for the post-edit index refresh hook."""

from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path


def test_hook_refresh_indexes_loads_without_pydantic(monkeypatch) -> None:
    """The hook should still import when the host interpreter lacks repo-only deps."""

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

    assert module.DEFAULT_EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"
    assert module.DEFAULT_EMBEDDING_CACHE_DIR == Path(
        ".codegraphcontext/global/db/vector-index/fastembed-cache"
    )
