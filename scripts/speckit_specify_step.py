#!/usr/bin/env python3
"""Deterministic specify runner and bootstrap helper for speckit.specify."""

from __future__ import annotations

import argparse
import json
import os
import re
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

from pipeline_driver import _resolve_feature_dir, build_correlation_id  # noqa: E402
from pipeline_driver_state import determine_next_phase  # noqa: E402
from speckit_spec_gate import _extract_clarifications  # noqa: E402

TEMPLATE_PLACEHOLDERS = (
    "[FEATURE NAME]",
    "[###-feature-name]",
    "[DATE]",
    "[Single sentence: who does what to achieve what outcome]",
    "[Single sentence: who/what consumes this and in what context]",
    "[Single sentence: observable state in production that means this feature is shipped]",
    "[Describe this user journey in plain language]",
)


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




def _load_feature_paths(env: dict[str, str], *, feature_id: str = "") -> dict[str, str]:
    """Resolve paths for an explicit feature or the current checkout feature."""
    if feature_id:
        feature_dir = _resolve_feature_dir(feature_id)
        if feature_dir is None:
            raise RuntimeError(f"feature_dir_not_found:{feature_id}")
        feature_spec = (feature_dir / "spec.md").resolve()
        if not feature_spec.is_file():
            raise RuntimeError(f"spec_file_not_found:{feature_spec}")
        return {"FEATURE_DIR": str(feature_dir), "FEATURE_SPEC": str(feature_spec)}

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


def _validate_spec_file(spec_file: Path) -> list[str]:
    """Validate a locally authored spec.md without invoking any subrunner."""
    text = spec_file.read_text(encoding="utf-8")
    reasons: list[str] = []
    if not text.strip():
        return ["spec_file_empty"]
    if SPEC_COMPLETION_MARKER not in text:
        reasons.append("missing_definition_of_done")
    if any(placeholder in text for placeholder in TEMPLATE_PLACEHOLDERS):
        reasons.append("spec_has_template_placeholders")
    _status, clarification_payload = _extract_clarifications(spec_file)
    if not clarification_payload.get("ok"):
        for reason in clarification_payload.get("reasons", []):
            reason_text = str(reason).strip()
            if reason_text and reason_text not in reasons:
                reasons.append(reason_text)
    return reasons


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
    correlation_id: str,
) -> dict[str, Any]:
    """Bootstrap one scaffold and return a canonical driver result."""
    _trace(f"_run_bootstrap_only_mode start description={description!r} short_name={short_name!r}")
    bootstrap = _run_bootstrap_mode(description, short_name, env)
    feature_id = str(bootstrap.get("BRANCH_NAME") or bootstrap.get("FEATURE_NUM") or "").strip()
    result = {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "phase": "specify",
        "feature_id": feature_id,
        "spec_name": str(bootstrap.get("BRANCH_NAME") or ""),
        "feature_num": str(bootstrap.get("FEATURE_NUM") or ""),
        "feature_dir": str(bootstrap.get("FEATURE_DIR") or ""),
        "spec_file": str(bootstrap.get("SPEC_FILE") or ""),
        "generated_artifact": {
            "path": str(bootstrap.get("SPEC_FILE") or ""),
            "completion_marker": SPEC_COMPLETION_MARKER,
        },
        "next_phase": "specify",
        "next_step": "fill_spec_scaffold",
    }
    _trace(
        "_run_bootstrap_only_mode done "
        f"feature_id={feature_id!r} spec_name={result['spec_name']!r} "
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
        paths = _load_feature_paths(env, feature_id=feature_id)
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

    generated_artifact = {
        "path": str(spec_file),
        "completion_marker": SPEC_COMPLETION_MARKER,
    }
    reasons = _validate_spec_file(spec_file)
    _trace(
        "_run_step_mode validation complete "
        f"feature_id={feature_id!r} ok={not reasons!r} reasons={reasons!r} "
        f"spec_file={str(spec_file)!r}"
    )
    if reasons:
        debug_path = _write_debug_payload(
            correlation_id=correlation_id,
            payload={
                "stage": "spec_validation",
                "feature_id": feature_id,
                "spec_file": str(spec_file),
                "reasons": reasons,
            },
        )
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "spec_validation",
            "reasons": reasons,
            "error_code": None,
            "phase": "specify",
            "feature_id": feature_id,
            "next_phase": "specify",
            "generated_artifact": generated_artifact,
            "spec_file": str(spec_file),
            "debug_path": debug_path,
        }

    return {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "gate": None,
        "reasons": [],
        "error_code": None,
        "phase": "specify",
        "feature_id": feature_id,
        "next_phase": determine_next_phase("specify"),
        "generated_artifact": generated_artifact,
        "pipeline_event_request": {"event": "backlog_registered", "fields": {}},
        "spec_file": str(spec_file),
        "debug_path": None,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for bootstrap and driver-managed specify runs."""
    parser = argparse.ArgumentParser(description="Specify bootstrap and deterministic step runner")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary output")
    parser.add_argument("--short-name", default="", help="Optional short name for the feature")
    parser.add_argument("--feature-id", default="", help="Existing feature selected by the pipeline driver")
    parser.add_argument("--phase", default="", help="Pipeline phase selected by the pipeline driver")
    parser.add_argument("--correlation-id", default="", help="Pipeline-driver correlation identifier")
    parser.add_argument("--timeout-seconds", type=int, default=300, help="Handoff timeout in seconds")
    parser.add_argument(
        "feature_description",
        nargs="?",
        default="",
        help="Feature description used to bootstrap a new spec scaffold",
    )
    return parser


def main(argv: list[str]) -> int:
    """Run bootstrap mode or the pipeline driver's existing-feature specify step."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = _build_uv_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    feature_id = str(args.feature_id).strip()
    phase = str(args.phase).strip()
    correlation_id = str(args.correlation_id).strip() or build_correlation_id(
        feature_id or "bootstrap", phase or "specify"
    )
    _trace(f"main start feature_id={feature_id!r} phase={phase!r}")

    if feature_id or phase:
        if not feature_id or phase != "specify":
            step_result = _build_step_failure(
                correlation_id=correlation_id,
                error_code="invalid_driver_route",
                reason="invalid_driver_route",
                debug_stage="parse_args",
                details={"feature_id": feature_id, "phase": phase},
            )
        else:
            step_result = _run_step_mode(
                feature_id=feature_id,
                phase=phase,
                correlation_id=correlation_id,
                env=env,
                timeout_seconds=int(args.timeout_seconds),
            )
    else:
        description = str(args.feature_description).strip()
        if not description:
            step_result = _build_step_failure(
                correlation_id=correlation_id,
                error_code="missing_feature_description",
                reason="missing_feature_description",
                debug_stage="parse_args",
                details={},
            )
        else:
            try:
                step_result = _run_bootstrap_only_mode(
                    description=description,
                    short_name=str(args.short_name).strip(),
                    env=env,
                    correlation_id=correlation_id,
                )
            except RuntimeError as exc:
                step_result = _build_step_failure(
                    correlation_id=correlation_id,
                    error_code="bootstrap_failed",
                    reason="bootstrap_failed",
                    debug_stage="bootstrap",
                    details={"error": str(exc)},
                )

    _trace(
        "main done "
        f"ok={step_result.get('ok')!r} feature_id={step_result.get('feature_id')!r} "
        f"spec_name={step_result.get('spec_name')!r}"
    )
    print(json.dumps(step_result, separators=(",", ":")))
    return int(step_result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
