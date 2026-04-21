"""Smoke tests for the post-edit index refresh hook."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from src.mcp_codebase.index.config import DEFAULT_EMBEDDING_CACHE_DIR, DEFAULT_EMBEDDING_MODEL_NAME


def _load_hook_module():
    """Load the refresh hook script as a module for direct function testing."""
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "hook_refresh_indexes.py"
    spec = importlib.util.spec_from_file_location("hook_refresh_indexes", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_refresh_vector_skips_when_embedding_model_cache_is_missing(monkeypatch, tmp_path) -> None:
    """Keep the hook from trying a network-backed model lookup on a cold cache."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    warnings: list[str] = []
    refresh_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_emit_warning", warnings.append)
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda *args, **kwargs: refresh_calls.append((args, kwargs)),
    )

    hook._refresh_vector([repo_root / "src" / "example.py"])

    assert refresh_calls == []
    assert warnings
    assert "embedding model cache for" in warnings[0]
    assert str(repo_root / DEFAULT_EMBEDDING_CACHE_DIR) in warnings[0]
    assert DEFAULT_EMBEDDING_MODEL_NAME in warnings[0]


def test_refresh_vector_uses_offline_mode_when_embedding_model_cache_is_present(monkeypatch, tmp_path) -> None:
    """Keep edit-time refresh local once the embedding cache has been primed."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    model_cache_dir = repo_root / DEFAULT_EMBEDDING_CACHE_DIR / f"models--{DEFAULT_EMBEDDING_MODEL_NAME.replace('/', '--')}"
    model_cache_dir.mkdir(parents=True)
    (model_cache_dir / "snapshot.json").write_text("{}", encoding="utf-8")
    warnings: list[str] = []
    refresh_calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_emit_warning", warnings.append)
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda command, label, env_overrides=None: refresh_calls.append((tuple(command), env_overrides)),
    )

    hook._refresh_vector([repo_root / "src" / "example.py"])

    assert warnings == []
    assert len(refresh_calls) == 1
    command, env_overrides = refresh_calls[0]
    assert command[:5] == ("uv", "run", "--no-sync", "python", "-m")
    assert env_overrides == {"HF_HUB_OFFLINE": "1"}
