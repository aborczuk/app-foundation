"""Regression tests for CodeGraph index owner lifecycle guards."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy_script_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    db_dir = repo / ".codegraphcontext" / "db"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    for name in ("cgc_safe_index.sh", "cgc_index_repo.sh", "cgc_owner.sh"):
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
        ["bash", f"scripts/{script}", target],
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

    start = time.monotonic()
    result = _run_script(
        repo,
        "cgc_safe_index.sh",
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
        "cgc_safe_index.sh",
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
            "cgc_safe_index.sh",
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
        "cgc_safe_index.sh",
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


def test_index_repo_reuses_safe_index_and_full_repo_opt_in(tmp_path: Path) -> None:
    repo = _copy_script_repo(tmp_path)
    bin_dir, log_file = _install_fake_uv(tmp_path)

    result = _run_script(
        repo,
        "cgc_index_repo.sh",
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
