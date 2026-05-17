"""Probe whether fresh read_code invocations reuse the same stdio worker process."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType


def _repo_root() -> Path:
    """Return the repository root that contains this probe script."""
    return Path(__file__).resolve().parents[1]


def _default_state_file() -> Path:
    """Return the default persisted comparison file for cross-invocation probes."""
    return _repo_root() / ".codegraphcontext" / "read-code-worker-persistence-probe.json"


def _load_read_code_module() -> ModuleType:
    """Load scripts/read_code.py as a module for direct backend probing."""
    scripts_dir = _repo_root() / "scripts"
    script_path = scripts_dir / "read_code.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("read_code_worker_persistence_probe", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load read_code module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, object] | None:
    """Return the persisted JSON object when the probe state file already exists."""
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"probe state file must contain a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    """Persist one bounded JSON object for the next probe invocation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _capture_worker_snapshot(read_code: ModuleType) -> dict[str, object]:
    """Start the current stdio worker path and return its live identity payload."""
    backend = read_code._load_read_code_reranker()
    if backend is None:
        return {
            "ok": False,
            "error": "read_code reranker backend unavailable",
            "captured_at": time.time(),
        }
    ready = backend._ensure_worker_ready()
    if ready is None or backend._worker_process is None:
        return {
            "ok": False,
            "error": "stdio worker unavailable",
            "captured_at": time.time(),
        }
    health = backend._worker_request({"op": "health"}, timeout=10.0)
    return {
        "ok": True,
        "captured_at": time.time(),
        "pid": backend._worker_process.pid,
        "started_at": health.get("started_at"),
        "model_name": health.get("model_name"),
        "build_fingerprint": health.get("build_fingerprint"),
        "parent_pid": backend._worker_process.pid,
    }


def _compare_snapshots(
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> dict[str, object]:
    """Return a compact comparison between the previous and current worker identities."""
    previous_pid = previous.get("pid") if isinstance(previous, dict) else None
    current_pid = current.get("pid")
    previous_started_at = previous.get("started_at") if isinstance(previous, dict) else None
    current_started_at = current.get("started_at")
    return {
        "previous_pid": previous_pid,
        "current_pid": current_pid,
        "same_pid": previous_pid == current_pid if previous_pid is not None and current_pid is not None else None,
        "previous_started_at": previous_started_at,
        "current_started_at": current_started_at,
        "same_started_at": (
            previous_started_at == current_started_at
            if previous_started_at is not None and current_started_at is not None
            else None
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the cross-invocation worker persistence probe."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=_default_state_file(),
        help="Persisted comparison file used across fresh probe invocations.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove any prior comparison state before probing the current invocation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Capture the current worker identity, compare it to the last invocation, and persist it."""
    args = build_parser().parse_args(argv)
    state_file = args.state_file.expanduser().resolve()
    if args.reset and state_file.exists():
        state_file.unlink()

    previous = _load_json(state_file)
    read_code = _load_read_code_module()
    current = _capture_worker_snapshot(read_code)
    comparison = _compare_snapshots(previous, current)
    payload = {
        "state_file": str(state_file),
        "previous": previous,
        "current": current,
        "comparison": comparison,
    }
    _write_json(state_file, current)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if current.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
