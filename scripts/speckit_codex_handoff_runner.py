#!/usr/bin/env python3
"""Run a single implement-task handoff through local Codex and commit the result."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
DEFAULT_GIT_AUTHOR_NAME = "Codex"
DEFAULT_GIT_AUTHOR_EMAIL = "codex@example.com"


def _tail_lines(text: str, count: int = 20) -> list[str]:
    """Return the last `count` lines from text for compact diagnostics."""
    if not text:
        return []
    lines = text.splitlines()
    return lines[-count:]


def _string(value: object) -> str:
    """Return a stripped string representation for payload fields."""
    return str(value or "").strip()


def _normalize_handoff(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a nested handoff mapping from either supported payload shape."""
    handoff = payload.get("handoff")
    if isinstance(handoff, Mapping):
        return dict(handoff)

    return {
        "feature_dir": _string(payload.get("feature_dir")),
        "task_id": _string(payload.get("task_id")),
        "task_attempt": payload.get("task_attempt"),
        "task_action": _string(payload.get("task_action")),
        "task_registered": payload.get("task_registered"),
        "task_parallel": payload.get("task_parallel"),
        "repo_root": _string(payload.get("repo_root")),
        "step_name": _string(payload.get("step_name")),
        "output_template_path": _string(payload.get("output_template_path")),
        "completion_marker": _string(payload.get("completion_marker")),
    }


def _load_payload(stdin_text: str) -> dict[str, Any]:
    """Parse the JSON handoff payload supplied on stdin."""
    payload = json.loads(stdin_text)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def _build_prompt(payload: Mapping[str, Any], repo_root: Path) -> str:
    """Build the Codex prompt for a single implement task."""
    handoff = _normalize_handoff(payload)

    feature_id = _string(payload.get("feature_id"))
    phase = _string(payload.get("phase"))
    correlation_id = _string(payload.get("correlation_id"))
    task_id = _string(handoff.get("task_id"))
    task_attempt = _string(handoff.get("task_attempt"))
    task_action = _string(handoff.get("task_action"))
    feature_dir = _string(handoff.get("feature_dir"))
    handoff_json = json.dumps(dict(handoff), indent=2, sort_keys=True)

    return (
        "You are the local Codex implementation runner for speckit.\n"
        f"Repository root: {repo_root}\n"
        f"Feature id: {feature_id}\n"
        f"Phase: {phase}\n"
        f"Correlation id: {correlation_id}\n"
        f"Task id: {task_id}\n"
        f"Task attempt: {task_attempt}\n"
        f"Task action: {task_action}\n"
        f"Feature dir: {feature_dir}\n\n"
        "Implement the next registered task for this feature.\n"
        "The task has already been selected and started by the deterministic runner.\n"
        "Use the task id and feature directory to inspect the relevant tasks.md and HUD context.\n"
        "Make only the code, test, and documentation changes needed for this task.\n"
        "Run targeted verification when it is useful to confirm the change.\n"
        "Do not create a git commit. The wrapper will commit after you finish.\n"
        "Return a short final summary of the changes.\n\n"
        "Handoff payload:\n"
        f"{handoff_json}\n"
    )


def _run_codex_exec(prompt: str, repo_root: Path) -> tuple[int, str, str, str]:
    """Execute Codex and return its exit code, streams, and last message."""
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise ValueError("codex_not_found")

    with tempfile.NamedTemporaryFile(prefix="speckit-codex-", suffix=".txt", delete=False) as handle:
        last_message_path = Path(handle.name)

    try:
        command = [
            codex_bin,
            "exec",
            "--ephemeral",
            "--full-auto",
            "--cd",
            str(repo_root),
            "--output-last-message",
            str(last_message_path),
            "-",
        ]
        execution = subprocess.run(
            command,
            cwd=repo_root,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        last_message = ""
        if last_message_path.exists():
            last_message = last_message_path.read_text(encoding="utf-8").strip()
        return execution.returncode, execution.stdout, execution.stderr, last_message
    finally:
        if last_message_path.exists():
            last_message_path.unlink()


def _git_identity_env() -> dict[str, str]:
    """Return a deterministic Git identity for the commit step."""
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", DEFAULT_GIT_AUTHOR_NAME)
    env.setdefault("GIT_AUTHOR_EMAIL", DEFAULT_GIT_AUTHOR_EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    return env


def _stage_and_commit(repo_root: Path, commit_message: str) -> tuple[str, list[str]]:
    """Stage the working tree, create a commit, and return its SHA and files."""
    add_run = subprocess.run(
        ["git", "add", "-A"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=_git_identity_env(),
    )
    if add_run.returncode != 0:
        raise ValueError("git_add_failed")

    diff_run = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=_git_identity_env(),
    )
    if diff_run.returncode != 0:
        raise ValueError("git_diff_failed")

    changed_files = [line.strip() for line in diff_run.stdout.splitlines() if line.strip()]
    if not changed_files:
        raise ValueError("no_changes_to_commit")

    commit_run = subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=_git_identity_env(),
    )
    if commit_run.returncode != 0:
        raise ValueError("git_commit_failed")

    sha_run = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
        env=_git_identity_env(),
    )
    if sha_run.returncode != 0:
        raise ValueError("commit_sha_unavailable")

    return sha_run.stdout.strip(), changed_files


def run_codex_handoff(
    payload: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run the local Codex handoff and commit the resulting task changes."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")

    repo_root = (repo_root or Path.cwd()).resolve()
    handoff = _normalize_handoff(payload)

    feature_id = _string(payload.get("feature_id"))
    phase = _string(payload.get("phase"))
    correlation_id = _string(payload.get("correlation_id"))
    task_id = _string(handoff.get("task_id"))
    task_attempt_raw = handoff.get("task_attempt")
    task_attempt = int(task_attempt_raw) if str(task_attempt_raw).strip() else 0
    task_action = _string(handoff.get("task_action"))
    artifact_path = _string(handoff.get("output_template_path"))
    completion_marker = _string(handoff.get("completion_marker"))

    prompt = _build_prompt(payload, repo_root)
    try:
        codex_exit_code, codex_stdout, codex_stderr, last_message = _run_codex_exec(prompt, repo_root)
    except ValueError as exc:
        reason = str(exc) or "codex_exec_failed"
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "feature_id": feature_id,
            "phase": phase,
            "task_id": task_id,
            "task_attempt": task_attempt,
            "task_action": task_action,
            "artifact_path": artifact_path,
            "completion_marker": completion_marker,
            "runner": "codex-local",
            "handoff_execution": "codex_exec",
            "reasons": [reason],
            "error_code": reason,
            "debug_path": None,
            "commit_sha": None,
            "summary": "",
            "changed_files": [],
            "stdout_tail": [],
            "stderr_tail": [],
            "handoff": dict(handoff),
        }

    if codex_exit_code != 0:
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": codex_exit_code,
            "correlation_id": correlation_id,
            "feature_id": feature_id,
            "phase": phase,
            "task_id": task_id,
            "task_attempt": task_attempt,
            "task_action": task_action,
            "artifact_path": artifact_path,
            "completion_marker": completion_marker,
            "runner": "codex-local",
            "handoff_execution": "codex_exec",
            "reasons": ["codex_exec_failed"],
            "error_code": "codex_exec_failed",
            "debug_path": None,
            "commit_sha": None,
            "summary": last_message or "",
            "changed_files": [],
            "stdout_tail": _tail_lines(codex_stdout),
            "stderr_tail": _tail_lines(codex_stderr),
            "handoff": dict(handoff),
        }

    commit_message = f"speckit implement {feature_id} {task_id} attempt {task_attempt}"
    try:
        commit_sha, changed_files = _stage_and_commit(repo_root, commit_message)
    except ValueError as exc:
        reason = str(exc) or "git_commit_failed"
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "feature_id": feature_id,
            "phase": phase,
            "task_id": task_id,
            "task_attempt": task_attempt,
            "task_action": task_action,
            "artifact_path": artifact_path,
            "completion_marker": completion_marker,
            "runner": "codex-local",
            "handoff_execution": "codex_exec",
            "reasons": [reason],
            "error_code": reason,
            "debug_path": None,
            "commit_sha": None,
            "summary": last_message or "",
            "changed_files": [],
            "stdout_tail": _tail_lines(codex_stdout),
            "stderr_tail": _tail_lines(codex_stderr),
            "handoff": dict(handoff),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "feature_id": feature_id,
        "phase": phase,
        "task_id": task_id,
        "task_attempt": task_attempt,
        "task_action": task_action,
        "artifact_path": artifact_path,
        "completion_marker": completion_marker,
        "runner": "codex-local",
        "handoff_execution": "codex_exec",
        "reasons": [],
        "error_code": None,
        "debug_path": None,
        "commit_sha": commit_sha,
        "summary": last_message or "",
        "changed_files": changed_files,
        "stdout_tail": _tail_lines(codex_stdout),
        "stderr_tail": _tail_lines(codex_stderr),
        "handoff": dict(handoff),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Read the handoff payload from stdin, run Codex, and print JSON."""
    _ = argv
    raw_input = sys.stdin.read()
    try:
        payload = _load_payload(raw_input)
        result = run_codex_handoff(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "exit_code": 1,
            "error_code": str(exc) or "invalid_payload",
            "reasons": [str(exc) or "invalid_payload"],
            "debug_path": None,
            "commit_sha": None,
            "summary": "",
            "changed_files": [],
        }

    print(json.dumps(result, sort_keys=True))
    if result.get("ok"):
        return 0
    exit_code = result.get("exit_code")
    return int(exit_code) if isinstance(exit_code, int) and exit_code != 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
