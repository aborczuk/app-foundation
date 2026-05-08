#!/usr/bin/env python3
"""Run Codex-backed estimate or breakdown work for task stabilization."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "1.0"
DEFAULT_GIT_AUTHOR_NAME = "speckit-tasking"
DEFAULT_GIT_AUTHOR_EMAIL = "speckit-tasking@localhost"
RUNNER_SUBDIR = Path(".speckit/runtime/tasking/runner")
SESSION_STATE_DIR = Path(".speckit/runtime/tasking/sessions")
SESSION_INDEX_FILENAME = "session_index.jsonl"
TAIL_LINES = 40


@dataclass(frozen=True)
class CommandResult:
    """Capture one Codex command execution."""

    exit_code: int
    stdout: str
    stderr: str
    last_message: str


def _build_parser() -> argparse.ArgumentParser:
    """Build CLI arguments for the tasking Codex runner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("estimate", "breakdown"), required=True)
    parser.add_argument("--feature-dir", required=True)
    parser.add_argument("--tasks-file", default=None)
    parser.add_argument("--estimates-file", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def _resolve_paths(args: argparse.Namespace, repo_root: Path) -> tuple[Path, Path, Path]:
    """Resolve the feature, task, and estimate paths for the selected mode."""
    feature_dir = Path(args.feature_dir).resolve()
    tasks_file = Path(args.tasks_file).resolve() if args.tasks_file else feature_dir / "tasks.md"
    estimates_file = (
        Path(args.estimates_file).resolve() if args.estimates_file else feature_dir / "estimates.md"
    )
    if not feature_dir.is_relative_to(repo_root):
        raise ValueError("feature_dir_outside_repo")
    return feature_dir, tasks_file, estimates_file


def _tail_lines(text: str, *, limit: int = TAIL_LINES) -> list[str]:
    """Return the trailing non-empty lines from a captured stream."""
    lines = [line.rstrip("\n") for line in text.splitlines()]
    tail = [line for line in lines if line.strip()]
    return tail[-limit:]


def _feature_scope_key(repo_root: Path, feature_dir: Path) -> str:
    """Return a stable key for the feature directory within this repo."""
    return feature_dir.relative_to(repo_root).as_posix().replace("/", "__")


def _session_state_path(repo_root: Path, feature_dir: Path, mode: str) -> Path:
    """Return the repo-local session-state path for the mode-specific agent."""
    return repo_root / SESSION_STATE_DIR / mode / f"{_feature_scope_key(repo_root, feature_dir)}.json"


def _load_session_state(session_state_path: Path) -> dict[str, Any] | None:
    """Load a previously persisted Codex session state if available."""
    if not session_state_path.exists():
        return None
    payload = json.loads(session_state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return payload


def _write_session_state(session_state_path: Path, payload: Mapping[str, Any]) -> None:
    """Persist Codex session metadata for the next stabilization round."""
    session_state_path.parent.mkdir(parents=True, exist_ok=True)
    session_state_path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _codex_home(repo_root: Path) -> Path:
    """Return the writable Codex home directory for this repo."""
    if "CODEX_HOME" in os.environ:
        return Path(os.environ["CODEX_HOME"]).expanduser().resolve()
    return (repo_root / ".speckit" / "runtime" / "tasking" / "codex-home").resolve()


def _discover_latest_session_record(codex_home: Path) -> dict[str, Any] | None:
    """Return the newest Codex session index record from the active Codex home."""
    session_index_path = codex_home / SESSION_INDEX_FILENAME
    if not session_index_path.exists():
        return None

    latest_record: dict[str, Any] | None = None
    for raw_line in session_index_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            latest_record = record
    if latest_record is None:
        return None
    return {
        "session_id": str(latest_record["id"]),
        "thread_name": latest_record.get("thread_name"),
        "updated_at": latest_record.get("updated_at"),
    }


def _build_prompt(
    *,
    mode: str,
    repo_root: Path,
    feature_dir: Path,
    tasks_file: Path,
    estimates_file: Path,
    session_mode: str,
    session_id: str | None,
) -> str:
    """Build the Codex prompt for the selected tasking mode."""
    base = [
        "You are the local Codex tasking runner for speckit.",
        f"Repository root: {repo_root}",
        f"Mode: {mode}",
        f"Feature dir: {feature_dir}",
        f"Tasks file: {tasks_file}",
        f"Estimates file: {estimates_file}",
        "",
    ]
    if mode == "estimate":
        base.extend(
            [
                "Read the task graph and update estimates.md with stable fibonacci estimates.",
                "Keep the estimates grounded in concrete task scope and preserve task ordering.",
                "Do not edit tasks.md in estimate mode.",
            ]
        )
    else:
        base.extend(
            [
                "Read the current task graph and split any 8/13-point tasks into smaller tasks.",
                "Update tasks.md only; do not edit estimates.md in breakdown mode.",
                "Preserve ordering, dependencies, and task identifiers where possible.",
            ]
        )
    base.extend(
        [
            "Do not create a git commit.",
            "Return a short summary of the changes.",
        ]
    )
    if session_mode == "resume":
        base.extend(
            [
                "",
                "This is a resumed Codex session.",
                f"Session id: {session_id or 'unknown'}",
                "Continue from the existing workspace state and keep this mode-specific agent warm until the task graph stabilizes.",
            ]
        )
    return "\n".join(base)


def _run_codex_exec(
    prompt: str,
    repo_root: Path,
    *,
    codex_home: Path,
    session_id: str | None = None,
) -> CommandResult:
    """Run Codex in the selected repository root and capture its output."""
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise ValueError("codex_not_found")

    with tempfile.NamedTemporaryFile(prefix="speckit-tasking-", suffix=".txt", delete=False) as handle:
        last_message_path = Path(handle.name)

    try:
        command = [
            codex_bin,
            "exec",
        ]
        if session_id:
            command.extend(["resume", session_id])
        command.append("--full-auto")
        command.extend(
            [
                "--output-last-message",
                str(last_message_path),
                "-",
            ]
        )
        execution = subprocess.run(
            command,
            cwd=repo_root,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "CODEX_HOME": str(codex_home)},
        )
        last_message = ""
        if last_message_path.exists():
            last_message = last_message_path.read_text(encoding="utf-8").strip()
        return CommandResult(
            exit_code=int(execution.returncode),
            stdout=execution.stdout,
            stderr=execution.stderr,
            last_message=last_message,
        )
    finally:
        if last_message_path.exists():
            last_message_path.unlink()


def _status_paths(repo_root: Path, feature_dir: Path) -> list[str]:
    """Return changed paths scoped to the active feature directory."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", str(feature_dir)],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        raise ValueError("git_status_failed")

    changed: list[str] = []
    for raw_line in status.stdout.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        path = line[3:].strip() if len(line) > 3 else line.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            changed.append(path)
    return changed


def _runner_log_path(repo_root: Path, mode: str, feature_dir: Path) -> Path:
    """Build a unique log path for the current Codex tasking run."""
    run_id = uuid.uuid4().hex[:12]
    return repo_root / RUNNER_SUBDIR / mode / f"{feature_dir.name}__{run_id}.json"


def _write_runner_log(
    *,
    repo_root: Path,
    mode: str,
    feature_dir: Path,
    tasks_file: Path,
    estimates_file: Path,
    prompt: str,
    codex_result: CommandResult | None,
    changed_files: list[str],
    result: Mapping[str, Any],
) -> str:
    """Persist a full runner trace and return the saved path."""
    runner_log_path = _runner_log_path(repo_root, mode, feature_dir)
    runner_log_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "feature_dir": str(feature_dir),
        "tasks_file": str(tasks_file),
        "estimates_file": str(estimates_file),
        "prompt": prompt,
        "codex_exit_code": codex_result.exit_code if codex_result else None,
        "codex_stdout": codex_result.stdout if codex_result else "",
        "codex_stderr": codex_result.stderr if codex_result else "",
        "last_message": codex_result.last_message if codex_result else "",
        "changed_files": list(changed_files),
        "result": dict(result),
    }
    runner_log_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(runner_log_path)


def _session_state_payload(
    *,
    mode: str,
    feature_dir: Path,
    session_id: str,
    session_record: Mapping[str, Any] | None,
    codex_home: Path,
) -> dict[str, Any]:
    """Build the persisted session state payload for a mode-specific agent."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "feature_dir": str(feature_dir),
        "session_id": session_id,
        "codex_home": str(codex_home),
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if session_record is not None:
        payload["thread_name"] = session_record.get("thread_name")
        payload["record_updated_at"] = session_record.get("updated_at")
    return payload


def _persist_session_state(
    *,
    repo_root: Path,
    feature_dir: Path,
    mode: str,
    session_id: str | None,
    session_record: Mapping[str, Any] | None,
    codex_home: Path,
) -> str | None:
    """Persist the latest session id for the mode-specific Codex agent."""
    if not session_id:
        return None
    session_state_path = _session_state_path(repo_root, feature_dir, mode)
    _write_session_state(
        session_state_path,
        _session_state_payload(
            mode=mode,
            feature_dir=feature_dir,
            session_id=session_id,
            session_record=session_record,
            codex_home=codex_home,
        ),
    )
    return str(session_state_path)


def _session_result_fields(
    *,
    repo_root: Path,
    feature_dir: Path,
    mode: str,
    session_id: str | None,
    session_mode: str,
    codex_home: Path,
) -> dict[str, Any]:
    """Return the session metadata that should appear in runner payloads."""
    session_state_path = _session_state_path(repo_root, feature_dir, mode)
    return {
        "session_id": session_id,
        "session_mode": session_mode,
        "session_state_path": str(session_state_path),
        "codex_home": str(codex_home),
    }


def clear_tasking_session_state(repo_root: Path, feature_dir: Path) -> list[str]:
    """Delete persisted warm-session state for both tasking modes."""
    removed_paths: list[str] = []
    for mode in ("estimate", "breakdown"):
        session_state_path = _session_state_path(repo_root, feature_dir, mode)
        if session_state_path.exists():
            session_state_path.unlink()
            removed_paths.append(str(session_state_path))
    return removed_paths


def _failure_result(
    *,
    mode: str,
    feature_dir: Path,
    tasks_file: Path,
    estimates_file: Path,
    session_id: str | None,
    session_mode: str,
    codex_home: Path,
    reason: str,
    prompt: str,
    codex_result: CommandResult | None,
    repo_root: Path,
) -> dict[str, Any]:
    """Build and persist a deterministic failure payload."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "exit_code": 1,
        "mode": mode,
        "feature_dir": str(feature_dir),
        "tasks_file": str(tasks_file),
        "estimates_file": str(estimates_file),
        "runner": "codex-local",
        "handoff_execution": "codex_exec",
        "completion_marker": f"{mode}_complete",
        "artifact_path": str(estimates_file if mode == "estimate" else tasks_file),
        "reasons": [reason],
        "error_code": reason,
        "summary": codex_result.last_message if codex_result else "",
        "changed_files": [],
        "stdout_tail": _tail_lines(codex_result.stdout) if codex_result else [],
        "stderr_tail": _tail_lines(codex_result.stderr) if codex_result else [],
    }
    result.update(
        _session_result_fields(
            repo_root=repo_root,
            feature_dir=feature_dir,
            mode=mode,
            session_id=session_id,
            session_mode=session_mode,
            codex_home=codex_home,
        )
    )
    result["runner_log_path"] = _write_runner_log(
        repo_root=repo_root,
        mode=mode,
        feature_dir=feature_dir,
        tasks_file=tasks_file,
        estimates_file=estimates_file,
        prompt=prompt,
        codex_result=codex_result,
        changed_files=[],
        result=result,
    )
    return result


def run_tasking_codex(args: argparse.Namespace, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Run the tasking Codex agent for estimate or breakdown stabilization."""
    repo_root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    feature_dir, tasks_file, estimates_file = _resolve_paths(args, repo_root)
    mode = str(args.mode)
    codex_home = _codex_home(repo_root)
    codex_home.mkdir(parents=True, exist_ok=True)
    session_state_path = _session_state_path(repo_root, feature_dir, mode)
    existing_session_state = _load_session_state(session_state_path)
    session_id: str | None = None
    if existing_session_state is not None and existing_session_state.get("codex_home") == str(codex_home):
        stored_session_id = existing_session_state.get("session_id")
        if isinstance(stored_session_id, str) and stored_session_id.strip():
            session_id = stored_session_id
    session_mode = "resume" if session_id else "fresh"
    prompt = _build_prompt(
        mode=mode,
        repo_root=repo_root,
        feature_dir=feature_dir,
        tasks_file=tasks_file,
        estimates_file=estimates_file,
        session_mode=session_mode,
        session_id=session_id,
    )

    if not feature_dir.exists():
        return _failure_result(
            mode=mode,
            feature_dir=feature_dir,
            tasks_file=tasks_file,
            estimates_file=estimates_file,
            session_id=session_id,
            session_mode=session_mode,
            codex_home=codex_home,
            reason="missing_feature_dir",
            prompt=prompt,
            codex_result=None,
            repo_root=repo_root,
        )
    if not tasks_file.exists():
        return _failure_result(
            mode=mode,
            feature_dir=feature_dir,
            tasks_file=tasks_file,
            estimates_file=estimates_file,
            session_id=session_id,
            session_mode=session_mode,
            codex_home=codex_home,
            reason="missing_tasks_file",
            prompt=prompt,
            codex_result=None,
            repo_root=repo_root,
        )
    if mode == "estimate" and not estimates_file.exists():
        estimates_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        codex_result = _run_codex_exec(prompt, repo_root, codex_home=codex_home, session_id=session_id)
    except ValueError as exc:
        reason = str(exc) or "codex_exec_failed"
        return _failure_result(
            mode=mode,
            feature_dir=feature_dir,
            tasks_file=tasks_file,
            estimates_file=estimates_file,
            session_id=session_id,
            session_mode=session_mode,
            codex_home=codex_home,
            reason=reason,
            prompt=prompt,
            codex_result=None,
            repo_root=repo_root,
        )

    session_record: Mapping[str, Any] | None = existing_session_state
    discovered_session_record = _discover_latest_session_record(codex_home)
    if discovered_session_record is not None:
        session_record = discovered_session_record
        discovered_session_id = discovered_session_record.get("session_id")
        if session_id is None and isinstance(discovered_session_id, str) and discovered_session_id.strip():
            session_id = discovered_session_id

    if codex_result.exit_code != 0:
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": codex_result.exit_code,
            "mode": mode,
            "feature_dir": str(feature_dir),
            "tasks_file": str(tasks_file),
            "estimates_file": str(estimates_file),
            "runner": "codex-local",
            "handoff_execution": "codex_exec",
            "completion_marker": f"{mode}_complete",
            "artifact_path": str(estimates_file if mode == "estimate" else tasks_file),
            "reasons": ["codex_exec_failed"],
            "error_code": "codex_exec_failed",
            "summary": codex_result.last_message,
            "changed_files": [],
            "stdout_tail": _tail_lines(codex_result.stdout),
            "stderr_tail": _tail_lines(codex_result.stderr),
        }
        result.update(
            _session_result_fields(
                repo_root=repo_root,
                feature_dir=feature_dir,
                mode=mode,
                session_id=session_id,
                session_mode=session_mode,
                codex_home=codex_home,
            )
        )
        persisted_session_state = _persist_session_state(
            repo_root=repo_root,
            feature_dir=feature_dir,
            mode=mode,
            session_id=session_id,
            session_record=session_record,
            codex_home=codex_home,
        )
        if persisted_session_state is not None:
            result["session_state_path"] = persisted_session_state
        result["runner_log_path"] = _write_runner_log(
            repo_root=repo_root,
            mode=mode,
            feature_dir=feature_dir,
            tasks_file=tasks_file,
            estimates_file=estimates_file,
            prompt=prompt,
            codex_result=codex_result,
            changed_files=[],
            result=result,
        )
        return result

    changed_files = _status_paths(repo_root, feature_dir)
    artifact_path = estimates_file if mode == "estimate" else tasks_file
    result = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "exit_code": 0,
        "mode": mode,
        "feature_dir": str(feature_dir),
        "tasks_file": str(tasks_file),
        "estimates_file": str(estimates_file),
        "runner": "codex-local",
        "handoff_execution": "codex_exec",
        "completion_marker": f"{mode}_complete",
        "artifact_path": str(artifact_path),
        "reasons": [],
        "error_code": None,
        "summary": codex_result.last_message,
        "changed_files": changed_files,
        "stdout_tail": _tail_lines(codex_result.stdout),
        "stderr_tail": _tail_lines(codex_result.stderr),
    }
    result.update(
        _session_result_fields(
            repo_root=repo_root,
            feature_dir=feature_dir,
            mode=mode,
            session_id=session_id,
            session_mode=session_mode,
            codex_home=codex_home,
        )
    )
    persisted_session_state = _persist_session_state(
        repo_root=repo_root,
        feature_dir=feature_dir,
        mode=mode,
        session_id=session_id,
        session_record=session_record,
        codex_home=codex_home,
    )
    if persisted_session_state is not None:
        result["session_state_path"] = persisted_session_state
    result["runner_log_path"] = _write_runner_log(
        repo_root=repo_root,
        mode=mode,
        feature_dir=feature_dir,
        tasks_file=tasks_file,
        estimates_file=estimates_file,
        prompt=prompt,
        codex_result=codex_result,
        changed_files=changed_files,
        result=result,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    """Run the requested Codex-backed tasking step and emit a JSON payload."""
    args = _build_parser().parse_args(argv)
    payload = run_tasking_codex(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if payload.get("ok"):
            print(
                " ".join(
                    [
                        "status=PASS",
                        f"mode={payload.get('mode')}",
                        f"changed_files={len(payload.get('changed_files', []))}",
                    ]
                )
            )
        else:
            print(f"status=FAIL reasons={','.join(payload.get('reasons', []))}")
    return 0 if bool(payload.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
