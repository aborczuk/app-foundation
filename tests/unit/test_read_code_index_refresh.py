"""Unit tests for read-code index freshness checks and targeted refresh behavior."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_module("read_code_index_refresh", "read_code.py")


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_vector_index_status_reports_missing_for_null_payload(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout="null\n"))

    status = read_code.vector_index_status()

    assert status == "missing"


def test_vector_index_status_reports_stale_when_status_payload_is_stale(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout='{"is_stale": true}\n'))

    status = read_code.vector_index_status()

    assert status == "stale"


def test_vector_index_status_reports_healthy_when_status_payload_is_fresh(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout='{"is_stale": false}\n'))

    status = read_code.vector_index_status()

    assert status == "healthy"


def test_vector_refresh_if_needed_runs_targeted_refresh_for_missing_index(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    monkeypatch.setattr(read_code, "vector_index_status", lambda project_root=None: "missing")
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env", {})))
        return _completed(0, stdout='{"entry_count": 1}')

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    target = tmp_path / "sample.py"
    read_code.vector_refresh_if_needed(target)

    assert len(calls) == 1
    cmd, env = calls[0]
    assert cmd[:8] == [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(read_code.REPO_ROOT),
    ]
    assert cmd[8:] == ["refresh", str(target)]
    assert env.get("HF_HUB_OFFLINE") == "1"


def test_vector_refresh_if_needed_skips_when_index_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "vector_index_status", lambda project_root=None: "healthy")
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    read_code.vector_refresh_if_needed(tmp_path / "sample.py")

    assert called["value"] is False


def test_codegraph_health_status_reports_unavailable_without_uv(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: False)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0, stdout='{"status":"healthy"}')

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    status = read_code.codegraph_health_status()

    assert status == "unavailable"
    assert called["value"] is False


def test_codegraph_refresh_if_needed_runs_scoped_refresh_for_stale_status(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "codegraph_health_status", lambda project_root=None: "stale")
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)

    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    scope_path = tmp_path / "src"
    read_code.codegraph_refresh_if_needed(scope_path)

    assert calls == [[str(fake_script), str(scope_path)]]


def test_codegraph_refresh_if_needed_skips_when_status_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "codegraph_health_status", lambda project_root=None: "healthy")
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert called["value"] is False


def test_read_code_context_runs_index_preflight_before_anchor_resolution(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    calls: list[Path] = []
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: calls.append(file_path))
    monkeypatch.setattr(
        read_code,
        "_vector_find_line_num",
        lambda *args, **kwargs: read_code._VectorMatch(
            line_num=1,
            raw_score=0.9,
            metadata_score=5.0,
            exact_symbol_match=True,
            symbol_type="function",
            has_body=True,
            has_docstring=False,
            line_span=1,
        ),
    )
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (0, 1))

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])

    assert exit_code == 0
    assert calls == [code_file]
