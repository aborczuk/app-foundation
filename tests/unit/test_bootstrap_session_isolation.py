"""Unit tests for bootstrap_session health gate, failure aggregation, and repo-local CGC isolation."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts import bootstrap_session as bs
from scripts import cgc_safe_index, hook_refresh_indexes, read_code


@dataclass(frozen=True)
class _FakeProbe:
    """Minimal CodeGraph health probe double."""

    status: str
    detail: str


def _make_scope_dirs(tmp_path: Path) -> None:
    """Create standard WARM_SCOPES directories inside tmp_path."""
    for name in ("scripts", "src", "tests", "specs"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)


def test_bootstrap_session_skips_cgc_safe_index_when_already_healthy_and_clean(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When CodeGraph probe is already healthy and no scopes are stale, zero indexing runs."""
    _make_scope_dirs(tmp_path)
    monkeypatch.setattr(bs, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        bs,
        "codegraph_health_probe",
        lambda scope: _FakeProbe(status="healthy", detail="graph snapshot is current"),
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        bs.subprocess,
        "run",
        lambda cmd, **kw: calls.append(list(cmd)) or subprocess.CompletedProcess(args=cmd, returncode=0),
    )

    summary = bs.bootstrap_session(tmp_path)
    assert calls == []
    assert summary["bootstrap_ok"] is True
    assert summary["codegraph_refreshed"] is True
    assert summary["warmed_scopes"] == []


def test_bootstrap_session_aggregates_failures_and_surfaces_subprocess_stderr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A later succeeding scope must never overwrite an earlier failure, and stderr must surface."""
    _make_scope_dirs(tmp_path)
    monkeypatch.setattr(bs, "REPO_ROOT", tmp_path)

    probes = iter(
        [
            _FakeProbe(status="stale", detail="needs refresh"),
            _FakeProbe(status="healthy", detail="graph snapshot is current with tracked source files"),
        ]
    )
    monkeypatch.setattr(bs, "codegraph_health_probe", lambda scope: next(probes))

    def fake_run(cmd, **kwargs):
        """Fail on scripts scope with concrete stderr, succeed on later scopes."""
        target = str(cmd[-1])
        if target.endswith("/scripts"):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="PermissionError: [Errno 1] Operation not permitted: '/Users/x/.codegraphcontext'",
            )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(bs.subprocess, "run", fake_run)

    summary = bs.bootstrap_session(tmp_path)
    assert summary["bootstrap_ok"] is False
    assert summary["codegraph_refreshed"] is False
    assert "PermissionError" in summary["codegraph_detail"]
    assert "failed_scopes" in summary
    assert any(item["scope"] == "scripts" for item in summary["failed_scopes"])


def test_cgc_safe_index_prepare_environment_isolates_home_and_xdg_inside_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """cgc_safe_index._prepare_environment must isolate HOME and XDG_* inside repo .codegraphcontext."""
    monkeypatch.setenv("HOME", "/Users/outside-sandbox-user")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/Users/outside-sandbox-user/.config")
    monkeypatch.setenv("XDG_CACHE_HOME", "/Users/outside-sandbox-user/.cache")

    cgc_safe_index._prepare_environment(tmp_path)
    cgc_root = (tmp_path / ".codegraphcontext").resolve()

    for var in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "CODEGRAPH_CONTEXT_DIR"):
        resolved = Path(os.environ[var]).resolve()
        assert str(resolved).startswith(str(cgc_root)), f"{var}={resolved} escaped {cgc_root}"
        assert "outside-sandbox-user" not in str(resolved)


def test_read_code_and_hook_refresh_envs_isolate_home_inside_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """read_code._cgc_capture_env and hook_refresh_indexes._refresh_env must isolate HOME repo-locally."""
    monkeypatch.setenv("HOME", "/Users/outside-sandbox-user")
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)

    cgc_root = (tmp_path / ".codegraphcontext").resolve()
    cgc_env = read_code._cgc_capture_env()
    refresh_env = hook_refresh_indexes._refresh_env(root=tmp_path)

    for env in (cgc_env, refresh_env):
        home = Path(env["HOME"]).resolve()
        assert str(home).startswith(str(cgc_root)), f"HOME={home} escaped {cgc_root}"
        assert "outside-sandbox-user" not in str(home)
