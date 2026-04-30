#!/usr/bin/env python3
"""Run resumable implement-task handoffs through local Codex and commit the result."""

from __future__ import annotations

import json
import os
import re
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


def _sanitize_for_filename(value: str) -> str:
    """Normalize arbitrary text into a filesystem-safe token."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def _write_runner_log(
    *,
    repo_root: Path,
    correlation_id: str,
    task_id: str,
    task_attempt: int,
    retry_index: int,
    payload: Mapping[str, Any],
) -> str:
    """Persist the full runner trace and return the artifact path."""
    log_dir = repo_root / ".speckit" / "runtime" / "implement" / "runner"
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = "__".join(
        [
            _sanitize_for_filename(correlation_id),
            _sanitize_for_filename(task_id),
            f"attempt-{task_attempt}",
            f"retry-{retry_index}",
        ]
    ) + ".json"
    log_path = (log_dir / filename).resolve()
    log_path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")
    return str(log_path)


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
        "resume_session": payload.get("resume_session"),
        "qa_feedback": payload.get("qa_feedback"),
        "retry_index": payload.get("retry_index"),
    }


def _coerce_bool(value: object) -> bool:
    """Interpret common payload values as a boolean flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_int(value: object, default: int = 0) -> int:
    """Interpret a payload field as an integer with a safe fallback."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        return int(stripped)
    return int(value)


def _load_payload(stdin_text: str) -> dict[str, Any]:
    """Parse the JSON handoff payload supplied on stdin."""
    payload = json.loads(stdin_text)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def _build_prompt(
    payload: Mapping[str, Any],
    repo_root: Path,
    *,
    resume_session: bool,
    qa_feedback: Mapping[str, Any] | None,
    retry_index: int,
) -> str:
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
    prompt = (
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
    if resume_session:
        prompt += (
            "\nThis is a resumed Codex session.\n"
            f"Resume index: {retry_index}\n"
            "Continue from the existing workspace state.\n"
            "Incorporate the QA feedback below before making any further changes.\n"
        )
        if qa_feedback:
            prompt += f"QA feedback:\n{json.dumps(dict(qa_feedback), indent=2, sort_keys=True)}\n"
    return prompt


def _run_codex_exec(prompt: str, repo_root: Path, *, resume_session: bool = False) -> tuple[int, str, str, str]:
    """Execute Codex and return its exit code, streams, and last message."""
    codex_bin = shutil.which("codex")
    if not codex_bin:
        raise ValueError("codex_not_found")

    with tempfile.NamedTemporaryFile(prefix="speckit-codex-", suffix=".txt", delete=False) as handle:
        last_message_path = Path(handle.name)

    try:
        command = [codex_bin, "exec"]
        if resume_session:
            command.extend(["resume", "--last"])
        command.extend(
            [
                "--full-auto",
                "--cd",
                str(repo_root),
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
    task_attempt = _coerce_int(handoff.get("task_attempt"))
    task_action = _string(handoff.get("task_action"))
    artifact_path = _string(handoff.get("output_template_path"))
    completion_marker = _string(handoff.get("completion_marker"))
    resume_session = _coerce_bool(handoff.get("resume_session") if "resume_session" in handoff else payload.get("resume_session"))
    qa_feedback = handoff.get("qa_feedback") if "qa_feedback" in handoff else payload.get("qa_feedback")
    retry_index_raw = handoff.get("retry_index") if "retry_index" in handoff else payload.get("retry_index")
    retry_index = _coerce_int(retry_index_raw)

    prompt = _build_prompt(
        payload,
        repo_root,
        resume_session=resume_session,
        qa_feedback=qa_feedback if isinstance(qa_feedback, Mapping) else None,
        retry_index=retry_index,
    )

    def _attach_runner_log(
        result: dict[str, Any],
        *,
        codex_exit_code: int | None = None,
        codex_stdout: str = "",
        codex_stderr: str = "",
        last_message: str = "",
        commit_sha: str | None = None,
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist the full runner trace and attach the artifact path."""
        runner_log_payload = {
            "schema_version": SCHEMA_VERSION,
            "correlation_id": correlation_id,
            "feature_id": feature_id,
            "phase": phase,
            "task_id": task_id,
            "task_attempt": task_attempt,
            "task_action": task_action,
            "artifact_path": artifact_path,
            "completion_marker": completion_marker,
            "resume_session": resume_session,
            "retry_index": retry_index,
            "prompt": prompt,
            "handoff": dict(handoff),
            "qa_feedback": dict(qa_feedback) if isinstance(qa_feedback, Mapping) else None,
            "codex_exit_code": codex_exit_code,
            "codex_stdout": codex_stdout,
            "codex_stderr": codex_stderr,
            "last_message": last_message,
            "commit_sha": commit_sha,
            "changed_files": list(changed_files or []),
            "result": dict(result),
        }
        result["runner_log_path"] = _write_runner_log(
            repo_root=repo_root,
            correlation_id=correlation_id,
            task_id=task_id,
            task_attempt=task_attempt,
            retry_index=retry_index,
            payload=runner_log_payload,
        )
        return result

    try:
        codex_exit_code, codex_stdout, codex_stderr, last_message = _run_codex_exec(
            prompt,
            repo_root,
            resume_session=resume_session,
        )
    except ValueError as exc:
        reason = str(exc) or "codex_exec_failed"
        return _attach_runner_log(
            {
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
                "session_mode": "resume" if resume_session else "fresh",
                "reasons": [reason],
                "error_code": reason,
                "debug_path": None,
                "commit_sha": None,
                "summary": "",
                "changed_files": [],
                "stdout_tail": [],
                "stderr_tail": [],
                "handoff": dict(handoff),
            },
            codex_exit_code=None,
        )

    if codex_exit_code != 0:
        return _attach_runner_log(
            {
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
                "session_mode": "resume" if resume_session else "fresh",
                "reasons": ["codex_exec_failed"],
                "error_code": "codex_exec_failed",
                "debug_path": None,
                "commit_sha": None,
                "summary": last_message or "",
                "changed_files": [],
                "stdout_tail": _tail_lines(codex_stdout),
                "stderr_tail": _tail_lines(codex_stderr),
                "handoff": dict(handoff),
            },
            codex_exit_code=codex_exit_code,
            codex_stdout=codex_stdout,
            codex_stderr=codex_stderr,
            last_message=last_message,
        )

    commit_message = f"speckit implement {feature_id} {task_id} attempt {task_attempt}"
    try:
        commit_sha, changed_files = _stage_and_commit(repo_root, commit_message)
    except ValueError as exc:
        reason = str(exc) or "git_commit_failed"
        return _attach_runner_log(
            {
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
                "session_mode": "resume" if resume_session else "fresh",
                "reasons": [reason],
                "error_code": reason,
                "debug_path": None,
                "commit_sha": None,
                "summary": last_message or "",
                "changed_files": [],
                "stdout_tail": _tail_lines(codex_stdout),
                "stderr_tail": _tail_lines(codex_stderr),
                "handoff": dict(handoff),
            },
            codex_exit_code=codex_exit_code,
            codex_stdout=codex_stdout,
            codex_stderr=codex_stderr,
            last_message=last_message,
        )

    return _attach_runner_log(
        {
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
            "session_mode": "resume" if resume_session else "fresh",
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "commit_sha": commit_sha,
            "summary": last_message or "",
            "changed_files": changed_files,
            "stdout_tail": _tail_lines(codex_stdout),
            "stderr_tail": _tail_lines(codex_stderr),
            "handoff": dict(handoff),
        },
        codex_exit_code=codex_exit_code,
        codex_stdout=codex_stdout,
        codex_stderr=codex_stderr,
        last_message=last_message,
        commit_sha=commit_sha,
        changed_files=changed_files,
    )


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
