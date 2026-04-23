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
    """Require explicit model bootstrap before vector refresh runs."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    refresh_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_embedding_model_available_offline", lambda root: (False, "offline-missing"))
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda *args, **kwargs: refresh_calls.append((args, kwargs)),
    )

    errors = hook._refresh_vector([repo_root / "src" / "example.py"])

    assert refresh_calls == []
    assert errors
    assert "embedding model cache for" in errors[0]
    assert str(repo_root / DEFAULT_EMBEDDING_CACHE_DIR) in errors[0]
    assert "offline-missing" in errors[0]
    assert DEFAULT_EMBEDDING_MODEL_NAME in errors[0]


def test_refresh_vector_uses_offline_mode_when_embedding_model_cache_is_present(monkeypatch, tmp_path) -> None:
    """Keep edit-time refresh local once the embedding cache has been primed."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    model_cache_dir = repo_root / DEFAULT_EMBEDDING_CACHE_DIR / f"models--{DEFAULT_EMBEDDING_MODEL_NAME.replace('/', '--')}"
    model_cache_dir.mkdir(parents=True)
    (model_cache_dir / "snapshot.json").write_text("{}", encoding="utf-8")
    refresh_calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_embedding_model_available_offline", lambda root: (True, ""))
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda command, label, env_overrides=None: refresh_calls.append((tuple(command), env_overrides)),
    )

    errors = hook._refresh_vector([repo_root / "src" / "example.py"])

    assert errors == []
    assert len(refresh_calls) == 1
    command, env_overrides = refresh_calls[0]
    assert command[:5] == ("uv", "run", "--no-sync", "python", "-m")
    assert env_overrides == {"HF_HUB_OFFLINE": "1"}


def test_refresh_vector_reuses_cached_embedding_model_availability(monkeypatch, tmp_path) -> None:
    """Reuse the availability probe result while the embedding cache stays unchanged."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    probe_calls: list[Path] = []
    refresh_calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    def fake_probe(root: Path) -> tuple[bool, str]:
        probe_calls.append(root)
        return True, ""

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_embedding_model_available_offline", fake_probe)
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda command, label, env_overrides=None: refresh_calls.append(
            (tuple(command), env_overrides)
        ),
    )

    first_errors = hook._refresh_vector([repo_root / "src" / "example.py"])
    second_errors = hook._refresh_vector([repo_root / "src" / "example.py"])

    assert first_errors == []
    assert second_errors == []
    assert len(probe_calls) == 1
    assert len(refresh_calls) == 2
    for _, env_overrides in refresh_calls:
        assert env_overrides == {"HF_HUB_OFFLINE": "1"}


def test_refresh_vector_reprobes_when_embedding_cache_state_changes(
    monkeypatch, tmp_path
) -> None:
    """Invalidate the cached probe when the embedding cache directory changes."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    probe_calls: list[Path] = []
    refresh_calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    def fake_probe(root: Path) -> tuple[bool, str]:
        probe_calls.append(root)
        return True, ""

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_embedding_model_available_offline", fake_probe)
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda command, label, env_overrides=None: refresh_calls.append(
            (tuple(command), env_overrides)
        ),
    )

    first_errors = hook._refresh_vector([repo_root / "src" / "example.py"])
    model_cache_dir = repo_root / DEFAULT_EMBEDDING_CACHE_DIR
    model_cache_dir.mkdir(parents=True, exist_ok=True)
    (model_cache_dir / "snapshot.json").write_text("{}", encoding="utf-8")
    second_errors = hook._refresh_vector([repo_root / "src" / "example.py"])

    assert first_errors == []
    assert second_errors == []
    assert len(probe_calls) == 2
    assert len(refresh_calls) == 2
    for _, env_overrides in refresh_calls:
        assert env_overrides == {"HF_HUB_OFFLINE": "1"}


def test_refresh_vector_includes_shell_paths(monkeypatch, tmp_path) -> None:
    """Include shell edits in the vector refresh path filter."""
    hook = _load_hook_module()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    script_path = repo_root / "scripts" / "refresh.sh"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("#!/usr/bin/env bash\necho refresh\n", encoding="utf-8")
    ignored_path = repo_root / "notes.txt"
    ignored_path.write_text("not indexed", encoding="utf-8")
    refresh_calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    monkeypatch.setattr(hook, "_repo_root", lambda: repo_root)
    monkeypatch.setattr(hook, "_embedding_model_available_offline", lambda root: (True, ""))
    monkeypatch.setattr(
        hook,
        "_run_refresh",
        lambda command, label, env_overrides=None: refresh_calls.append((tuple(command), env_overrides)),
    )

    errors = hook._refresh_vector([script_path, ignored_path])

    assert errors == []
    assert len(refresh_calls) == 1
    command, env_overrides = refresh_calls[0]
    assert str(script_path) in command
    assert str(ignored_path) not in command
    assert env_overrides == {"HF_HUB_OFFLINE": "1"}


def test_main_returns_nonzero_when_refresh_fails(monkeypatch) -> None:
    """Surface refresh failures as a hard hook failure for deterministic handoff."""
    hook = _load_hook_module()
    monkeypatch.setattr(hook.json, "load", lambda stream: {"tool_input": {"file_path": "scripts/read_code.py"}})
    monkeypatch.setattr(hook, "_collect_changed_paths", lambda payload: [Path("scripts/read_code.py")])
    monkeypatch.setattr(hook, "_refresh_codegraph", lambda paths: ["codegraph failed"])
    monkeypatch.setattr(hook, "_refresh_vector", lambda paths: [])

    exit_code = hook.main()

    assert exit_code == 1
