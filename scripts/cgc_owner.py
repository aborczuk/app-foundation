#!/usr/bin/env python3
"""Shared CodeGraph owner- and lock-file helpers."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_IGNORED_EDIT_PREFIXES = (
    ".codegraphcontext/",
    ".speckit/",
    ".uv-cache/",
    "logs/",
    "shadow-runs/",
)


def codegraph_context_dir() -> Path:
    """Return the repo-local CodeGraph context directory."""
    raw = os.environ.get("CODEGRAPH_CONTEXT_DIR")
    return Path(raw) if raw else REPO_ROOT / ".codegraphcontext"


def codegraph_db_dir() -> Path:
    """Return the repo-local CodeGraph database directory."""
    raw = os.environ.get("CODEGRAPH_DB_DIR")
    return Path(raw) if raw else codegraph_context_dir() / "db"


def owner_pid_file() -> Path:
    """Return the path for the current owner pid marker."""
    db_name = os.environ.get("CGC_OWNER_DB_NAME", "kuzudb")
    return codegraph_db_dir() / f"{db_name}.owner.pid"


def owner_lock_file() -> Path:
    """Return the path for the current owner lock marker."""
    db_name = os.environ.get("CGC_OWNER_DB_NAME", "kuzudb")
    return codegraph_db_dir() / f"{db_name}.lock"


def last_error_file() -> Path:
    """Return the path that stores the last CodeGraph error summary."""
    return codegraph_context_dir() / "last-index-error.txt"


def last_edit_signature_file() -> Path:
    """Return the path that stores the last tracked edit signature."""
    return codegraph_context_dir() / "last-edit-signature.txt"


def wait_seconds() -> int:
    """Return the maximum time to wait for an active owner to release."""
    raw = os.environ.get("CGC_OWNER_WAIT_SECONDS", "15")
    try:
        return max(0, int(raw))
    except ValueError:
        return 15


def poll_seconds() -> float:
    """Return the polling interval used while waiting for release."""
    raw = os.environ.get("CGC_OWNER_POLL_SECONDS", "1")
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 1.0


def lock_stale_seconds() -> int:
    """Return the age threshold for treating a lock without an owner as stale."""
    raw = os.environ.get("CGC_OWNER_LOCK_STALE_SECONDS", "300")
    try:
        return max(0, int(raw))
    except ValueError:
        return 300


def is_valid_pid(value: object) -> bool:
    """Return whether a value looks like a positive integer pid."""
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.isdigit()


def file_mtime_epoch(path: Path) -> int | None:
    """Return the integer modification time for a file if it exists."""
    if not path.exists():
        return None
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return None


def pid_is_alive(pid: object) -> bool:
    """Return whether a pid still points at a non-zombie process."""
    if not is_valid_pid(pid):
        return False
    numeric_pid = int(str(pid))
    try:
        os.kill(numeric_pid, 0)
    except OSError:
        return False

    try:
        result = subprocess.run(
            ["ps", "-p", str(numeric_pid), "-o", "stat="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return True

    return "Z" not in result.stdout


def lock_is_stale_without_owner() -> bool:
    """Return whether the lock marker is stale and no owner marker exists."""
    owner_file = owner_pid_file()
    lock_path = owner_lock_file()
    stale_after = lock_stale_seconds()
    if owner_file.exists() or not lock_path.exists():
        return False

    mtime = file_mtime_epoch(lock_path)
    now = int(time.time())
    if mtime is None:
        return False

    age = max(0, now - mtime)
    return age >= stale_after


def clear_artifacts() -> None:
    """Remove the owner pid and lock markers."""
    for path in (owner_pid_file(), owner_lock_file()):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def clear_last_error() -> None:
    """Remove the last-error marker if it exists."""
    try:
        last_error_file().unlink()
    except FileNotFoundError:
        pass


def clear_last_edit_signature() -> None:
    """Remove the last edit-signature marker if it exists."""
    try:
        last_edit_signature_file().unlink()
    except FileNotFoundError:
        pass


def release(current_pid: int | None = None) -> None:
    """Release the ownership markers if this process still owns them."""
    pid_file = owner_pid_file()
    try:
        owner_pid = pid_file.read_text(encoding="utf-8").splitlines()[0].strip()
    except (FileNotFoundError, IndexError):
        owner_pid = ""

    current = str(current_pid or os.getpid())
    if owner_pid == current:
        clear_artifacts()


def _register_release() -> None:
    """Register the exit handler that clears ownership markers."""
    atexit.register(release)


def wait_for_release() -> int:
    """Wait for an active owner to clear its markers."""
    owner_file = owner_pid_file()
    lock_path = owner_lock_file()
    waited = 0.0
    max_wait = float(wait_seconds())
    poll = poll_seconds()

    while owner_file.exists() or lock_path.exists():
        if owner_file.exists():
            try:
                owner_pid = owner_file.read_text(encoding="utf-8").splitlines()[0].strip()
            except (FileNotFoundError, IndexError):
                owner_pid = ""

            if not is_valid_pid(owner_pid):
                print(f"Removing invalid CodeGraph owner marker: {owner_file}")
                clear_artifacts()
                return 0

            if not pid_is_alive(owner_pid):
                print(f"Removing stale CodeGraph owner marker (pid {owner_pid}): {owner_file}")
                clear_artifacts()
                return 0
        elif lock_is_stale_without_owner():
            print(f"Removing stale CodeGraph lock marker without owner: {lock_path}")
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            return 0

        if waited >= max_wait:
            if owner_file.exists():
                try:
                    owner_pid = owner_file.read_text(encoding="utf-8").splitlines()[0].strip()
                except (FileNotFoundError, IndexError):
                    owner_pid = ""
                print(
                    f"Existing CodeGraph owner (pid {owner_pid}) is still active after {int(max_wait)}s; "
                    "refusing recovery yet.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"CodeGraph lock marker persists without owner after {int(max_wait)}s; refusing recovery yet.",
                    file=sys.stderr,
                )
            return 75

        time.sleep(poll)
        waited += poll

    return 0


def claim(command: str | None = None) -> None:
    """Record ownership for the current process and register release hooks."""
    db_dir = codegraph_db_dir()
    db_dir.mkdir(parents=True, exist_ok=True)
    pid_file = owner_pid_file()
    lock_path = owner_lock_file()
    pid = str(os.getpid())
    pid_file.write_text(f"{pid}\n", encoding="utf-8")
    lock_path.write_text(f"pid={pid} command={command or sys.argv[0]}\n", encoding="utf-8")
    _register_release()


def error_is_memory_pressure(detail: str) -> bool:
    """Return whether an error message looks like a memory-pressure failure."""
    normalized = detail.lower()
    markers = (
        "buffer pool",
        "exhaust",
        "out of memory",
        "memory pressure",
        "memory exhausted",
        "cannot allocate",
        "allocation failed",
    )
    return any(marker in normalized for marker in markers)


def record_last_error(error_type: str, exit_code: int, error_detail: str) -> None:
    """Persist the last CodeGraph error summary for later diagnosis."""
    detail = " ".join(error_detail.split())
    last_error_file().write_text(
        f"type={error_type}\nexit_code={exit_code}\ndetail={detail}\n",
        encoding="utf-8",
    )


def current_edit_signature(repo_root: Path | None = None) -> str:
    """Return a stable signature for the current git edit state."""
    root = repo_root or REPO_ROOT
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""

    lines: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else ""
        candidates = [part.strip() for part in path.split(" -> ")] if " -> " in path else [path.strip()]
        if any(candidate.startswith(_IGNORED_EDIT_PREFIXES) for candidate in candidates if candidate):
            continue
        lines.append(line)

    unique_sorted = sorted(dict.fromkeys(lines))
    return "\n".join(unique_sorted)


def record_edit_signature(repo_root: Path | None = None) -> None:
    """Persist the current edit signature for freshness comparisons."""
    signature = current_edit_signature(repo_root)
    last_edit_signature_file().write_text(signature, encoding="utf-8")
