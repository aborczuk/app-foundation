"""Test module."""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import pytest

from csp_trader.runtime.runner_lock import (
    IBKR_SESSION_LOCK_CLIENT_ID,
    IBKR_SESSION_LOCK_MODE,
    RunnerInstanceLock,
    RunnerLockBusyError,
    build_ibkr_session_lock,
)


def _hold_lock(lock_dir: str, ready_conn, release_conn) -> None:
    lock = RunnerInstanceLock(
        mode="trading",
        host="127.0.0.1",
        port=4001,
        client_id=7,
        lock_dir=Path(lock_dir),
    )
    lock.acquire()
    ready_conn.send("ready")
    release_conn.recv()
    lock.release()


def _hold_ibkr_session_lock(lock_dir: str, ready_conn, release_conn) -> None:
    lock = build_ibkr_session_lock(
        host="127.0.0.1",
        port=4001,
        lock_dir=Path(lock_dir),
    )
    lock.acquire()
    ready_conn.send("ready")
    release_conn.recv()
    lock.release()


def test_build_ibkr_session_lock_uses_canonical_scope(tmp_path: Path) -> None:
    """Test the expected behavior."""
    lock = build_ibkr_session_lock(host="127.0.0.1", port=4001, lock_dir=tmp_path)
    assert lock.lock_key == (
        f"{IBKR_SESSION_LOCK_MODE}|127.0.0.1|4001|{IBKR_SESSION_LOCK_CLIENT_ID}"
    )


def test_runner_lock_reacquire_after_release(tmp_path: Path) -> None:
    """Test the expected behavior."""
    first = RunnerInstanceLock(
        mode="trading",
        host="127.0.0.1",
        port=4001,
        client_id=7,
        lock_dir=tmp_path,
    )
    second = RunnerInstanceLock(
        mode="trading",
        host="127.0.0.1",
        port=4001,
        client_id=7,
        lock_dir=tmp_path,
    )

    first.acquire()
    first.release()
    second.acquire()
    second.release()


@pytest.mark.skipif(
    mp.get_start_method(allow_none=True) == "forkserver",
    reason="forkserver environments can block pipe handshakes in this test",
)
def test_runner_lock_blocks_parallel_process(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ready_parent, ready_child = mp.Pipe(duplex=True)
    release_parent, release_child = mp.Pipe(duplex=True)
    proc = mp.Process(
        target=_hold_lock,
        args=(str(tmp_path), ready_child, release_child),
        daemon=True,
    )
    proc.start()
    try:
        assert ready_parent.recv() == "ready"

        contender = RunnerInstanceLock(
            mode="trading",
            host="127.0.0.1",
            port=4001,
            client_id=7,
            lock_dir=tmp_path,
        )
        busy, owner = contender.probe_busy()
        assert busy is True
        assert isinstance(owner, dict)
        assert owner.get("pid") == proc.pid

        with pytest.raises(RunnerLockBusyError):
            contender.acquire()
    finally:
        release_parent.send("release")
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        assert proc.exitcode == 0


@pytest.mark.skipif(
    mp.get_start_method(allow_none=True) == "forkserver",
    reason="forkserver environments can block pipe handshakes in this test",
)
def test_ibkr_session_lock_blocks_parallel_process(tmp_path: Path) -> None:
    """Test the expected behavior."""
    ready_parent, ready_child = mp.Pipe(duplex=True)
    release_parent, release_child = mp.Pipe(duplex=True)
    proc = mp.Process(
        target=_hold_ibkr_session_lock,
        args=(str(tmp_path), ready_child, release_child),
        daemon=True,
    )
    proc.start()
    try:
        assert ready_parent.recv() == "ready"

        contender = build_ibkr_session_lock(
            host="127.0.0.1",
            port=4001,
            lock_dir=tmp_path,
        )
        busy, owner = contender.probe_busy()
        assert busy is True
        assert isinstance(owner, dict)
        assert owner.get("pid") == proc.pid

        with pytest.raises(RunnerLockBusyError):
            contender.acquire()
    finally:
        release_parent.send("release")
        proc.join(timeout=5)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
        assert proc.exitcode == 0
