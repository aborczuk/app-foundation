from __future__ import annotations

import os
from pathlib import Path

import scripts.bootstrap_session as bootstrap_session


class _Probe:
    """Minimal stand-in for the codegraph probe result."""

    def __init__(self, status: str, detail: str = "") -> None:
        self.status = status
        self.detail = detail


def test_bootstrap_session_sets_uv_cache_and_refreshes(monkeypatch, tmp_path: Path) -> None:
    """Bootstrap should pin UV cache and warm codegraph when stale."""
    calls: list[str] = []

    monkeypatch.setattr(bootstrap_session, "repo_uv_env", lambda: {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")})
    monkeypatch.setattr(bootstrap_session, "codegraph_health_probe", lambda scope: _Probe("stale", "stale index"))
    monkeypatch.setattr(
        bootstrap_session.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args[0][-1]) or type("Proc", (), {"returncode": 0})(),
    )

    summary = bootstrap_session.bootstrap_session(tmp_path)

    assert os.environ["UV_CACHE_DIR"] == str(tmp_path / ".uv-cache")
    assert summary["uv_cache_dir"] == str(tmp_path / ".uv-cache")
    assert summary["codegraph_before"] == "stale"
    assert summary["codegraph_after"] == "stale"
    assert summary["bootstrap_ok"] is True
    assert summary["warmed_scopes"] == ["scripts", "src", "tests", "specs"]
    assert calls == [
        str(bootstrap_session.REPO_ROOT / "scripts"),
        str(bootstrap_session.REPO_ROOT / "src"),
        str(bootstrap_session.REPO_ROOT / "tests"),
        str(bootstrap_session.REPO_ROOT / "specs"),
    ]
