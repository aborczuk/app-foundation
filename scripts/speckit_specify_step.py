#!/usr/bin/env python3
"""Deterministic specify runner and bootstrap helper for speckit.specify."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
SPEC_COMPLETION_MARKER = "## Definition of Done"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from pipeline_driver import build_correlation_id  # noqa: E402
from pipeline_driver_state import determine_next_phase  # noqa: E402


def _trace(message: str) -> None:
    """Emit a temporary stderr trace when SPECKIT_TRACE is enabled."""
    if not os.environ.get("SPECKIT_TRACE"):
        return
    print(
        f"[specify-trace pid={os.getpid()} ppid={os.getppid()}] {message}",
        file=sys.stderr,
        flush=True,
    )


def _build_uv_env() -> dict[str, str]:
    """Return the repo-local environment for specify workflows."""
    from uv_env import repo_uv_env

    os.environ.update(repo_uv_env())
    return os.environ.copy()


def _run_uv_command(
    args: list[str],
    *,
    env: dict[str, str],
    input_payload: str | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a repo command through uv with the repo-local cache enabled."""
    return subprocess.run(
        ["uv", "run", "--no-sync", *args],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        input=input_payload,
        timeout=timeout_seconds,
    )


def _sanitize_for_filename(value: str) -> str:
    """Normalize arbitrary text into a filesystem-safe token."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def _write_debug_payload(*, correlation_id: str, payload: dict[str, Any]) -> str:
    """Persist a debug payload for failed specify-step runs."""
    debug_dir = REPO_ROOT / ".speckit" / "runtime" / "specify"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = (debug_dir / f"{_sanitize_for_filename(correlation_id)}.json").resolve()
    debug_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(debug_path)


def _persist_bootstrap_description(spec_file: Path, description: str) -> None:
    """Store the original user request in the generated spec scaffold."""
    description = description.strip()
    if not description:
        return

    try:
        content = spec_file.read_text(encoding="utf-8")
    except OSError:
        return

    description_literal = json.dumps(description)
    updated = content
    if '"$ARGUMENTS"' in updated:
        updated = updated.replace('"$ARGUMENTS"', description_literal, 1)
    elif "$ARGUMENTS" in updated:
        updated = updated.replace("$ARGUMENTS", description_literal, 1)

    if updated != content:
        spec_file.write_text(updated, encoding="utf-8")


def _load_spec_description(spec_file: Path) -> str:
    """Read the persisted user-description line from a scaffolded spec."""
    try:
        content = spec_file.read_text(encoding="utf-8")
    except OSError:
        return ""

    for line in content.splitlines():
        marker = "Input: User description:"
        if marker not in line:
            continue
        raw_value = line.split(marker, 1)[1].strip()
        if not raw_value:
            return ""
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value.strip('"').strip("'")
    return ""


def _create_feature(description: str, short_name: str, env: dict[str, str]) -> dict[str, Any]:
    """Create the feature scaffold and return the parsed JSON payload."""
    _trace(f"_create_feature start short_name={short_name!r} description={description!r}")
    cmd = [
        "python3",
        ".specify/scripts/python/create_new_feature.py",
        "--json",
    ]
    if short_name:
        cmd.extend(["--short-name", short_name])
    cmd.append(description)

    proc = _run_uv_command(cmd, env=env)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "feature scaffold failed").strip())

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("feature scaffold returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("feature scaffold returned invalid payload")
    _trace(
        "_create_feature done "
        f"branch_name={payload.get('BRANCH_NAME')!r} feature_num={payload.get('FEATURE_NUM')!r} "
        f"spec_file={payload.get('SPEC_FILE')!r}"
    )
    return payload




def _default_handoff_runner(repo_root: Path) -> str:
    """Return the canonical local Codex runner command."""
    runner_path = (repo_root / "scripts" / "speckit_codex_handoff_runner.py").resolve()
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(runner_path))}"


def _load_feature_paths(env: dict[str, str]) -> dict[str, str]:
    """Resolve the current feature paths from the repo-local prerequisite helper."""
    feature_dir = str(env.get("FEATURE_DIR") or "").strip()
    feature_spec = str(env.get("FEATURE_SPEC") or "").strip()
    if feature_dir and feature_spec:
        return {"FEATURE_DIR": feature_dir, "FEATURE_SPEC": feature_spec}

    proc = _run_uv_command(
        ["python3", ".specify/scripts/python/check_prerequisites.py", "--json", "--paths-only"],
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "failed to resolve feature paths").strip())

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("check_prerequisites returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("check_prerequisites returned invalid payload")
    return {str(key): str(value) for key, value in payload.items()}


def _build_specify_instructions(
    *,
    feature_description: str,
    feature_id: str,
    feature_dir: Path,
    spec_file: Path,
) -> str:
    """Build the Codex instructions used to fill the specify scaffold."""
    template_path = (REPO_ROOT / ".specify" / "templates" / "spec-template.md").resolve()
    lines = [
        "You are filling the scaffolded specification for speckit.specify.",
        f"Repository root: {REPO_ROOT}",
        f"Feature id: {feature_id}",
        f"Feature dir: {feature_dir}",
        f"Spec file: {spec_file}",
        f"Template file: {template_path}",
        "",
        "Use the scaffolded spec and the user description to write the requirements in place.",
        "Replace all placeholders with concrete, user-value-focused content.",
        "Keep the spec limited to feature name, user context, requirements, success criteria, and open questions.",
        "Preserve the section order from the template.",
        "Do not create a git commit.",
        "",
        f"Original user description: {feature_description or feature_id}",
    ]
    return "\n".join(lines).strip() + "\n"


def _build_specify_handoff_input(
    *,
    feature_id: str,
    phase: str,
    correlation_id: str,
    feature_dir: Path,
    spec_file: Path,
    feature_description: str,
    resume_session: bool = False,
    retry_index: int = 0,
    qa_feedback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the generic Codex handoff payload for specify fill rounds."""
    handoff: dict[str, Any] = {
        "feature_dir": str(feature_dir),
        "repo_root": str(REPO_ROOT),
        "step_name": "speckit.specify",
        "task_action": "fill_spec_scaffold",
        "output_template_path": str(spec_file),
        "completion_marker": SPEC_COMPLETION_MARKER,
        "instructions": _build_specify_instructions(
            feature_description=feature_description,
            feature_id=feature_id,
            feature_dir=feature_dir,
            spec_file=spec_file,
        ),
        "resume_session": resume_session,
        "retry_index": retry_index,
    }
    if qa_feedback is not None:
        handoff["qa_feedback"] = dict(qa_feedback)
    return {
        "feature_id": feature_id,
        "phase": phase,
        "correlation_id": correlation_id,
        "handoff": handoff,
    }


def _run_specify_handoff_round(
    *,
    env: dict[str, str],
    handoff_input: Mapping[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run one Codex handoff round for the specify fill step."""
    correlation_id = str(handoff_input.get("correlation_id") or "").strip()
    command = ["python3", "scripts/speckit_codex_handoff_runner.py"]

    try:
        proc = _run_uv_command(
            command,
            env=env,
            input_payload=json.dumps(dict(handoff_input), sort_keys=True),
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        debug_path = _write_debug_payload(
            correlation_id=correlation_id or "unknown",
            payload={
                "stage": "handoff",
                "error_code": "handoff_timeout",
                "command": command,
                "input_payload": dict(handoff_input),
                "stdout": str(exc.stdout or ""),
                "stderr": str(exc.stderr or ""),
            },
        )
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 2,
            "correlation_id": correlation_id or "unknown",
            "error_code": "handoff_timeout",
            "reasons": ["handoff_timeout"],
            "gate": None,
            "next_phase": None,
            "debug_path": debug_path,
        }

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        debug_path = _write_debug_payload(
            correlation_id=correlation_id or "unknown",
            payload={
                "stage": "handoff",
                "error_code": "invalid_handoff_json_result",
                "command": command,
                "process_exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "input_payload": dict(handoff_input),
            },
        )
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 2,
            "correlation_id": correlation_id or "unknown",
            "error_code": "invalid_handoff_json_result",
            "reasons": ["invalid_handoff_json_result"],
            "gate": None,
            "next_phase": None,
            "debug_path": debug_path,
        }

    if not isinstance(payload, dict):
        debug_path = _write_debug_payload(
            correlation_id=correlation_id or "unknown",
            payload={
                "stage": "handoff",
                "error_code": "invalid_handoff_payload",
                "command": command,
                "process_exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "input_payload": dict(handoff_input),
            },
        )
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 2,
            "correlation_id": correlation_id or "unknown",
            "error_code": "invalid_handoff_payload",
            "reasons": ["invalid_handoff_payload"],
            "gate": None,
            "next_phase": None,
            "debug_path": debug_path,
        }

    payload.setdefault("stdout", stdout)
    payload.setdefault("stderr", stderr)
    payload.setdefault("process_exit_code", proc.returncode)
    payload.setdefault("timed_out", False)
    if int(payload.get("exit_code") or 0) == 1 and str(payload.get("error_code") or "") == "codex_exec_failed":
        payload["exit_code"] = 2
    if not str(payload.get("debug_path") or "").strip():
        payload["debug_path"] = str(payload.get("runner_log_path") or "")
    return payload


def _run_bootstrap_mode(description: str, short_name: str, env: dict[str, str]) -> dict[str, Any]:
    """Bootstrap a new feature scaffold."""
    _trace(f"_run_bootstrap_mode start short_name={short_name!r} description={description!r}")
    feature = _create_feature(description, short_name, env)

    feature_dir = Path(feature["SPEC_FILE"]).resolve().parent
    spec_file = Path(feature["SPEC_FILE"]).resolve()
    _persist_bootstrap_description(spec_file, description)
    _trace(
        "_run_bootstrap_mode done "
        f"branch_name={feature.get('BRANCH_NAME')!r} feature_num={feature.get('FEATURE_NUM')!r} "
        f"feature_dir={feature_dir} spec_file={spec_file}"
    )

    return {
        "BRANCH_NAME": feature["BRANCH_NAME"],
        "FEATURE_NUM": feature["FEATURE_NUM"],
        "FEATURE_DIR": str(feature_dir),
        "SPEC_FILE": str(spec_file),
        "FEATURE_DESCRIPTION": description,
    }


def _build_specify_step_identity(
    *,
    feature: Mapping[str, Any],
    phase: str,
    feature_description: str,
) -> tuple[str, str]:
    """Derive the step feature id and correlation id from bootstrap output."""
    feature_id = str(feature.get("BRANCH_NAME") or feature.get("FEATURE_NUM") or "").strip()
    if not feature_id:
        raise RuntimeError("bootstrap feature id missing")
    return feature_id, build_correlation_id(feature_id, phase)


def _run_bootstrap_only_mode(
    *,
    description: str,
    short_name: str,
    env: dict[str, str],
) -> dict[str, Any]:
    """Bootstrap the scaffold and return the metadata needed for manual spec writing."""
    _trace(f"_run_bootstrap_only_mode start description={description!r} short_name={short_name!r}")
    bootstrap = _run_bootstrap_mode(description, short_name, env)
    feature_id = str(bootstrap.get("BRANCH_NAME") or bootstrap.get("FEATURE_NUM") or "").strip()
    result = {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "phase": "specify",
        "feature_id": feature_id,
        "branch_name": str(bootstrap.get("BRANCH_NAME") or ""),
        "feature_num": str(bootstrap.get("FEATURE_NUM") or ""),
        "feature_dir": str(bootstrap.get("FEATURE_DIR") or ""),
        "spec_file": str(bootstrap.get("SPEC_FILE") or ""),
        "generated_artifact": {
            "path": str(bootstrap.get("SPEC_FILE") or ""),
            "completion_marker": SPEC_COMPLETION_MARKER,
        },
        "next_step": "fill_spec_scaffold",
    }
    _trace(
        "_run_bootstrap_only_mode done "
        f"feature_id={feature_id!r} branch_name={result['branch_name']!r} "
        f"spec_file={result['spec_file']!r}"
    )
    return result


def _build_step_failure(
    *,
    correlation_id: str,
    error_code: str,
    reason: str,
    debug_stage: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    """Build a canonical error envelope for specify step failures."""
    debug_path = _write_debug_payload(
        correlation_id=correlation_id,
        payload={
            "stage": debug_stage,
            "error_code": error_code,
            **details,
        },
    )
    return {
        "schema_version": "1.0.0",
        "ok": False,
        "exit_code": 2,
        "correlation_id": correlation_id,
        "gate": None,
        "reasons": [reason],
        "error_code": error_code,
        "next_phase": None,
        "debug_path": debug_path,
    }


def _run_step_mode(
    *,
    feature_id: str,
    phase: str,
    correlation_id: str,
    env: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run the deterministic specify fill/validation loop."""
    _trace(f"_run_step_mode start feature_id={feature_id!r} phase={phase!r} correlation_id={correlation_id!r}")
    try:
        paths = _load_feature_paths(env)
    except RuntimeError as exc:
        return _build_step_failure(
            correlation_id=correlation_id,
            error_code="feature_paths_unavailable",
            reason="feature_paths_unavailable",
            debug_stage="resolve_feature_paths",
            details={"exception": str(exc)},
        )

    feature_dir = Path(paths.get("FEATURE_DIR", "")).resolve()
    spec_file = Path(paths.get("FEATURE_SPEC", "")).resolve()
    if not feature_dir.exists() or not spec_file.is_file():
        return _build_step_failure(
            correlation_id=correlation_id,
            error_code="spec_scaffold_missing",
            reason="spec_scaffold_missing",
            debug_stage="resolve_spec_scaffold",
            details={
                "feature_dir": str(feature_dir),
                "spec_file": str(spec_file),
            },
        )

    feature_description = _load_spec_description(spec_file) or feature_dir.name
    handoff_input = _build_specify_handoff_input(
        feature_id=feature_id,
        phase=phase,
        correlation_id=correlation_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        feature_description=feature_description,
    )

    handoff_result = _run_specify_handoff_round(
        env=env,
        handoff_input=handoff_input,
        timeout_seconds=timeout_seconds,
    )
    _trace(
        "_run_step_mode handoff complete "
        f"feature_id={feature_id!r} ok={handoff_result.get('ok')!r} "
        f"spec_file={str(spec_file)!r}"
    )
    if not handoff_result.get("ok"):
        if "generated_artifact" not in handoff_result:
            handoff_result["generated_artifact"] = {
                "path": str(spec_file),
                "completion_marker": SPEC_COMPLETION_MARKER,
            }
        handoff_result["spec_file"] = str(spec_file)
        return handoff_result

    generated_artifact = dict(
        handoff_result.get("generated_artifact")
        or {
            "path": str(spec_file),
            "completion_marker": SPEC_COMPLETION_MARKER,
        }
    )
    generated_artifact["path"] = str(spec_file)
    generated_artifact["completion_marker"] = SPEC_COMPLETION_MARKER

    return {
        **handoff_result,
        "next_phase": handoff_result.get("next_phase") or determine_next_phase("specify"),
        "generated_artifact": generated_artifact,
        "spec_file": str(spec_file),
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for bootstrap-only specify runs."""
    parser = argparse.ArgumentParser(description="Specify bootstrap and deterministic step runner")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary output")
    parser.add_argument("--short-name", default="", help="Optional short name for the feature")
    parser.add_argument(
        "feature_description",
        nargs="?",
        default="",
        help="Feature description used to bootstrap a new spec scaffold",
    )
    return parser


def main(argv: list[str]) -> int:
    """Bootstrap the scaffold and return its metadata for manual spec completion."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = _build_uv_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _trace(f"main start short_name={str(args.short_name).strip()!r}")

    description = str(args.feature_description).strip()
    if not description:
        print("ERROR: No feature description provided", file=sys.stderr)
        return 1

    try:
        step_result = _run_bootstrap_only_mode(
            description=description,
            short_name=str(args.short_name).strip(),
            env=env,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _trace(
        "main done "
        f"ok={step_result.get('ok')!r} feature_id={step_result.get('feature_id')!r} "
        f"branch_name={step_result.get('branch_name')!r}"
    )
    print(json.dumps(step_result, separators=(",", ":")))
    return int(step_result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
