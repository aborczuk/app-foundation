"""Regression tests for CodeGraph index owner lifecycle guards."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
READ_CODE_SCRIPT = REPO_ROOT / "scripts" / "read_code.py"
READ_CODE_HEALTH_SCRIPT = REPO_ROOT / "scripts" / "read_code_health.py"


def _load_read_code_module():
    scripts_dir = READ_CODE_SCRIPT.parent
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("read_code", READ_CODE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
def _load_read_code_health_module():
    scripts_dir = READ_CODE_HEALTH_SCRIPT.parent
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("read_code_health", READ_CODE_HEALTH_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_code_health = _load_read_code_health_module()
read_code = _load_read_code_module()


def _copy_script_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    db_dir = repo / ".codegraphcontext" / "db"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    for name in ("cgc_safe_index.py", "cgc_index_repo.py", "cgc_owner.py"):
        shutil.copy2(REPO_ROOT / "scripts" / name, scripts_dir / name)
        (scripts_dir / name).chmod(0o755)

    return repo


def _install_fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "uv.log"
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$FAKE_UV_LOG"
if [ "${1:-}" = "run" ] && [ "${3:-}" = "cgc" ] && [ "${4:-}" = "index" ]; then
  printf '%s\\n' "$*" >> "$FAKE_CGC_LOG"
  printf 'KUZUDB_PATH=%s\\n' "${KUZUDB_PATH:-}" >> "$FAKE_CGC_LOG"
  printf 'FALKORDB_PATH=%s\\n' "${FALKORDB_PATH:-}" >> "$FAKE_CGC_LOG"
  printf 'FALKORDB_SOCKET_PATH=%s\\n' "${FALKORDB_SOCKET_PATH:-}" >> "$FAKE_CGC_LOG"
  printf 'CODEGRAPH_CONTEXT_DIR=%s\\n' "${CODEGRAPH_CONTEXT_DIR:-}" >> "$FAKE_CGC_LOG"
  printf 'CODEGRAPH_DB_DIR=%s\\n' "${CODEGRAPH_DB_DIR:-}" >> "$FAKE_CGC_LOG"
  printf 'UV_CACHE_DIR=%s\\n' "${UV_CACHE_DIR:-}" >> "$FAKE_CGC_LOG"
  case "${FAKE_UV_MODE:-success}" in
    success)
      exit 0
      ;;
    memory-pressure)
      echo "Kuzu buffer pool exhausted while indexing" >&2
      exit 137
      ;;
    *)
      echo "generic cgc index failure" >&2
      exit 1
      ;;
  esac
fi
if [ "${1:-}" = "run" ] && [ "${3:-}" = "python" ] && [ "${4:-}" = "-m" ] && [ "${5:-}" = "src.mcp_codebase.doctor" ]; then
  case "${FAKE_UV_DOCTOR_STATUS:-healthy}" in
    healthy)
      cat <<'JSON'
{"access_mode":"READ_ONLY","checked_at":"2026-04-19T00:00:00Z","detail":"healthy","latency_ms":1.0,"recovery_hint":{"action":"continue","command":"","id":"continue","preserves_last_good":true,"summary":"ok"},"source":"filesystem-freshness","status":"healthy"}
JSON
      exit 0
      ;;
    stale)
      cat <<'JSON'
{"access_mode":"READ_ONLY","checked_at":"2026-04-19T00:00:00Z","detail":"stale","latency_ms":1.0,"recovery_hint":{"action":"refresh","command":"scripts/cgc_safe_index.py .","id":"refresh-scoped-index","preserves_last_good":true,"summary":"stale"},"source":"filesystem-freshness","status":"stale"}
JSON
      exit 0
      ;;
    *)
      cat <<'JSON'
{
  "access_mode":"READ_ONLY",
  "checked_at":"2026-04-19T00:00:00Z",
  "detail":"unavailable",
  "latency_ms":1.0,
  "recovery_hint":{
    "action":"fallback",
    "command":"scripts/read_code.py <file> <symbol> --allow-fallback",
    "id":"fallback-to-files",
    "preserves_last_good":false,
    "summary":"fallback"
  },
  "source":"filesystem-freshness",
  "status":"unavailable"
}
JSON
      exit 0
      ;;
  esac
fi
echo "unexpected uv invocation: $*" >&2
exit 1
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    return bin_dir, log_file


def _run_script(
    repo: Path,
    script: str,
    target: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        [sys.executable, f"scripts/{script}", target],
        cwd=repo,
        text=True,
        capture_output=True,
        env=proc_env,
        check=False,
    )


def _read_text_or_empty(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_safe_index_waits_for_live_owner_then_runs(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    owner_pid_file = repo / ".codegraphcontext" / "db" / "kuzudb.owner.pid"
    lock_file = repo / ".codegraphcontext" / "db" / "kuzudb.lock"

    owner = subprocess.Popen(["sleep", "1"], text=True)
    owner_pid_file.write_text(f"{owner.pid}\n", encoding="utf-8")
    lock_file.write_text("locked\n", encoding="utf-8")
    reaper = threading.Timer(1.0, owner.wait)
    reaper.daemon = True
    reaper.start()

    start = time.monotonic()
    result = _run_script(
        repo,
        "cgc_safe_index.py",
        "src/mcp_codebase",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "CGC_OWNER_WAIT_SECONDS": "5",
            "CGC_OWNER_POLL_SECONDS": "1",
        },
    )
    elapsed = time.monotonic() - start
    owner.wait(timeout=5)

    assert result.returncode == 0, result.stderr
    assert elapsed >= 1.0
    assert "Running incremental index for: src/mcp_codebase" in result.stdout
    assert "cgc index src/mcp_codebase" in log_file.read_text(encoding="utf-8")
    assert not owner_pid_file.exists()
    assert not lock_file.exists()


def test_safe_index_cleans_stale_owner_without_blocking(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    owner_pid_file = repo / ".codegraphcontext" / "db" / "kuzudb.owner.pid"
    lock_file = repo / ".codegraphcontext" / "db" / "kuzudb.lock"

    owner_pid_file.write_text("999999\n", encoding="utf-8")
    lock_file.write_text("locked\n", encoding="utf-8")

    start = time.monotonic()
    result = _run_script(
        repo,
        "cgc_safe_index.py",
        "src/mcp_codebase",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "CGC_OWNER_WAIT_SECONDS": "2",
            "CGC_OWNER_POLL_SECONDS": "1",
        },
    )
    elapsed = time.monotonic() - start

    assert result.returncode == 0, result.stderr
    assert elapsed < 2.0
    assert "Removing stale CodeGraph owner marker" in result.stdout
    assert "cgc index src/mcp_codebase" in log_file.read_text(encoding="utf-8")
    assert not owner_pid_file.exists()
    assert not lock_file.exists()


def test_safe_index_cleans_stale_lock_without_owner_after_age_threshold(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    lock_file = repo / ".codegraphcontext" / "db" / "kuzudb.lock"
    lock_file.write_text("locked\n", encoding="utf-8")
    old = time.time() - 120
    os.utime(lock_file, (old, old))

    result = _run_script(
        repo,
        "cgc_safe_index.py",
        "src/mcp_codebase",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "CGC_OWNER_WAIT_SECONDS": "1",
            "CGC_OWNER_POLL_SECONDS": "1",
            "CGC_OWNER_LOCK_STALE_SECONDS": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Removing stale CodeGraph lock marker without owner" in result.stdout
    assert "cgc index src/mcp_codebase" in log_file.read_text(encoding="utf-8")
    assert not lock_file.exists()


def test_safe_index_refuses_when_owner_stays_live_past_timeout(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    owner_pid_file = repo / ".codegraphcontext" / "db" / "kuzudb.owner.pid"
    lock_file = repo / ".codegraphcontext" / "db" / "kuzudb.lock"

    owner = subprocess.Popen(["sleep", "5"], text=True)
    owner_pid_file.write_text(f"{owner.pid}\n", encoding="utf-8")
    lock_file.write_text("locked\n", encoding="utf-8")

    try:
        result = _run_script(
            repo,
            "cgc_safe_index.py",
            "src/mcp_codebase",
            env={
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
                "FAKE_UV_LOG": str(log_file),
                "FAKE_CGC_LOG": str(log_file),
                "CGC_OWNER_WAIT_SECONDS": "1",
                "CGC_OWNER_POLL_SECONDS": "1",
            },
        )
    finally:
        owner.terminate()
        owner.wait(timeout=5)

    assert result.returncode == 75, result.stderr
    assert "refusing recovery yet" in result.stderr
    assert _read_text_or_empty(log_file) == ""
    assert owner_pid_file.exists()
    assert lock_file.exists()


def test_safe_index_records_memory_pressure_and_health_reports_it(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    owner_pid_file = repo / ".codegraphcontext" / "db" / "kuzudb.owner.pid"
    lock_file = repo / ".codegraphcontext" / "db" / "kuzudb.lock"
    last_error_file = repo / ".codegraphcontext" / "last-index-error.txt"

    result = _run_script(
        repo,
        "cgc_safe_index.py",
        "src/mcp_codebase",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "FAKE_UV_MODE": "memory-pressure",
            "CGC_OWNER_WAIT_SECONDS": "2",
            "CGC_OWNER_POLL_SECONDS": "1",
        },
    )

    assert result.returncode == 137, result.stderr
    assert "memory pressure" in result.stderr.lower()
    assert last_error_file.exists()
    assert "memory-pressure" in last_error_file.read_text(encoding="utf-8")
    assert not owner_pid_file.exists()
    assert not lock_file.exists()

    from src.mcp_codebase.health import GraphHealthStatus, classify_graph_health

    health = classify_graph_health(repo)

    assert health.status is GraphHealthStatus.UNAVAILABLE
    assert health.recovery_hint.id == "fail-fast-memory-pressure"
    assert "memory pressure" in health.detail.lower()


def test_read_code_health_status_marks_dirty_tree_stale(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "src").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / ".codegraphcontext").mkdir(parents=True, exist_ok=True)
    (repo / ".codegraphcontext" / "last-edit-signature.txt").write_text("", encoding="utf-8")

    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_UV_LOG", str(log_file))
    monkeypatch.setenv("FAKE_CGC_LOG", str(log_file))
    monkeypatch.setenv("FAKE_UV_DOCTOR_STATUS", "healthy")

    status = read_code_health.codegraph_health_status(repo)
    captured = capsys.readouterr()

    assert status == "stale"
    assert "marking codegraph stale" in captured.err


def test_index_repo_reuses_safe_index_and_full_repo_opt_in(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)

    result = _run_script(
        repo,
        "cgc_index_repo.py",
        ".",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "CGC_ALLOW_REPO_INDEX": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Running incremental index for:" in result.stdout
    assert "cgc index" in log_file.read_text(encoding="utf-8")


def test_safe_index_overrides_inherited_codegraph_paths(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)
    inherited_root = tmp_path / "inherited-main-repo"
    inherited_db = inherited_root / ".codegraphcontext" / "db"

    result = _run_script(
        repo,
        "cgc_safe_index.py",
        "scripts",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log_file),
            "FAKE_CGC_LOG": str(log_file),
            "KUZUDB_PATH": str(inherited_db / "kuzudb"),
            "FALKORDB_PATH": str(inherited_db / "falkordb"),
            "FALKORDB_SOCKET_PATH": str(inherited_db / "falkordb.sock"),
            "CODEGRAPH_CONTEXT_DIR": str(inherited_root / ".codegraphcontext"),
            "CODEGRAPH_DB_DIR": str(inherited_db),
            "UV_CACHE_DIR": str(inherited_root / ".codegraphcontext" / ".uv-cache"),
        },
    )

    assert result.returncode == 0, result.stderr
    log_text = log_file.read_text(encoding="utf-8")
    expected_context = repo / ".codegraphcontext"
    expected_db = expected_context / "db"
    assert f"KUZUDB_PATH={expected_db / 'kuzudb'}" in log_text
    assert f"FALKORDB_PATH={expected_db / 'falkordb'}" in log_text
    assert f"FALKORDB_SOCKET_PATH={expected_db / 'falkordb.sock'}" in log_text
    assert f"CODEGRAPH_CONTEXT_DIR={expected_context}" in log_text
    assert f"CODEGRAPH_DB_DIR={expected_db}" in log_text
    assert f"UV_CACHE_DIR={expected_context / '.uv-cache'}" in log_text
    assert str(inherited_root) not in log_text
