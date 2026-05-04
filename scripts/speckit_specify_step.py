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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_MAX_TERMS = 5
SPEC_ROUTING_MARKER = "## Routing Contract"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline_driver_state import determine_next_phase  # noqa: E402

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "build",
    "app",
    "browser",
    "feature",
    "for",
    "from",
    "game",
    "in",
    "into",
    "make",
    "of",
    "on",
    "or",
    "playable",
    "the",
    "to",
    "up",
    "with",
}


def _build_uv_env() -> dict[str, str]:
    """Return the repo-local environment for specify workflows."""
    from uv_env import repo_uv_env

    os.environ.update(repo_uv_env())
    return os.environ.copy()


def _extract_terms(description: str) -> list[str]:
    """Extract a compact set of discovery terms from the feature description."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*", description):
        normalized = token.strip("-").lower()
        if len(normalized) < 3 or normalized in STOP_WORDS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= DISCOVERY_MAX_TERMS:
            break
    return terms or ["feature"]


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


def _render_discovery_result(result: dict[str, Any]) -> str:
    """Render one discovery result block for the terminal and discovery.md."""
    term = result.get("term", "unknown")
    has_matches = bool(result.get("has_matches"))
    stdout = str(result.get("stdout") or "").rstrip()
    stderr = str(result.get("stderr") or "").rstrip()
    lines = [f"- {term}", f"  has_matches: {str(has_matches).lower()}"]
    if stdout:
        lines.append("  stdout:")
        lines.extend(f"    {line}" for line in stdout.splitlines())
    if stderr:
        lines.append("  stderr:")
        lines.extend(f"    {line}" for line in stderr.splitlines())
    return "\n".join(lines)


def _run_discovery(terms: Iterable[str], env: dict[str, str]) -> list[dict[str, Any]]:
    """Run semantic code discovery for each search term in parallel."""
    term_list = list(terms)
    if not term_list:
        return []

    with ThreadPoolExecutor(max_workers=min(len(term_list), 5)) as pool:
        future_map = {
            pool.submit(_run_uv_command, ["python3", "scripts/read_code.py", "context", term], env=env): term
            for term in term_list
        }
        results: list[dict[str, Any]] = []
        for future, term in future_map.items():
            proc = future.result()
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            results.append(
                {
                    "term": term,
                    "returncode": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                    "has_matches": proc.returncode == 0 and "ERROR: No match found" not in stdout + stderr,
                }
            )

    results.sort(key=lambda item: term_list.index(item["term"]))
    return results


def _create_feature(description: str, short_name: str, env: dict[str, str]) -> dict[str, Any]:
    """Create the feature scaffold and return the parsed JSON payload."""
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
    return payload


def _write_discovery_artifact(feature_dir: Path, discovery: list[dict[str, Any]]) -> Path:
    """Write the captured discovery output into discovery.md for the feature."""
    discovery_path = feature_dir / "discovery.md"
    discovery_path.parent.mkdir(parents=True, exist_ok=True)
    blocks = ["# Discovery", ""]
    for result in discovery:
        blocks.append(_render_discovery_result(result))
        blocks.append("")
    discovery_path.write_text("\n".join(blocks).rstrip() + "\n", encoding="utf-8")
    return discovery_path


def _default_handoff_runner(repo_root: Path) -> str:
    """Return the canonical local Codex runner command."""
    runner_path = (repo_root / "scripts" / "speckit_codex_handoff_runner.py").resolve()
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(runner_path))}"


def _load_feature_paths(env: dict[str, str]) -> dict[str, str]:
    """Resolve the current feature paths from the repo-local prerequisite helper."""
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
    discovery_file: Path,
) -> str:
    """Build the Codex instructions used to fill the specify scaffold."""
    template_path = (REPO_ROOT / ".specify" / "templates" / "spec-template.md").resolve()
    lines = [
        "You are filling the scaffolded specification for speckit.specify.",
        f"Repository root: {REPO_ROOT}",
        f"Feature id: {feature_id}",
        f"Feature dir: {feature_dir}",
        f"Spec file: {spec_file}",
        f"Discovery file: {discovery_file}",
        f"Template file: {template_path}",
        "",
        "Use the scaffolded spec and discovery notes to write the specification in place.",
        "Replace all placeholders with concrete, user-value-focused content.",
        "Keep the routing contract vocabulary exact and deterministic.",
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
    discovery_file: Path,
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
        "completion_marker": SPEC_ROUTING_MARKER,
        "instructions": _build_specify_instructions(
            feature_description=feature_description,
            feature_id=feature_id,
            feature_dir=feature_dir,
            spec_file=spec_file,
            discovery_file=discovery_file,
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
    return payload


def _validate_spec_routing(spec_file: Path, env: dict[str, str]) -> dict[str, Any]:
    """Validate the routing contract inside the scaffolded spec."""
    proc = _run_uv_command(
        ["python3", "scripts/speckit_spec_gate.py", "validate-routing", "--spec-file", str(spec_file), "--json"],
        env=env,
    )

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise RuntimeError("spec routing validation returned invalid JSON")
    if not isinstance(payload, dict):
        raise RuntimeError("spec routing validation returned invalid payload")
    payload["process_exit_code"] = proc.returncode
    payload["stdout"] = proc.stdout or ""
    payload["stderr"] = proc.stderr or ""
    return payload


def _ensure_discovery_artifact(
    *,
    env: dict[str, str],
    feature_dir: Path,
    spec_file: Path,
) -> Path:
    """Ensure discovery.md exists, deriving it from the stored spec description when needed."""
    discovery_path = feature_dir / "discovery.md"
    if discovery_path.is_file():
        return discovery_path

    description = _load_spec_description(spec_file)
    discovery_terms = _extract_terms(description or feature_dir.name)
    discovery = _run_discovery(discovery_terms, env)
    return _write_discovery_artifact(feature_dir, discovery)


def _run_bootstrap_mode(description: str, short_name: str, env: dict[str, str]) -> dict[str, Any]:
    """Bootstrap a new feature scaffold and persist the discovery artifact."""
    terms = _extract_terms(description)
    discovery = _run_discovery(terms, env)

    feature = _create_feature(description, short_name, env)
    feature_dir = Path(feature["SPEC_FILE"]).resolve().parent
    spec_file = Path(feature["SPEC_FILE"]).resolve()
    _persist_bootstrap_description(spec_file, description)
    discovery_path = _write_discovery_artifact(feature_dir, discovery)

    return {
        "BRANCH_NAME": feature["BRANCH_NAME"],
        "FEATURE_NUM": feature["FEATURE_NUM"],
        "FEATURE_DIR": str(feature_dir),
        "SPEC_FILE": str(spec_file),
        "DISCOVERY_FILE": str(discovery_path),
        "DISCOVERY_TERMS": terms,
        "DISCOVERY": discovery,
        "FEATURE_DESCRIPTION": description,
    }


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

    discovery_path = _ensure_discovery_artifact(env=env, feature_dir=feature_dir, spec_file=spec_file)
    feature_description = _load_spec_description(spec_file) or feature_dir.name
    handoff_input = _build_specify_handoff_input(
        feature_id=feature_id,
        phase=phase,
        correlation_id=correlation_id,
        feature_dir=feature_dir,
        spec_file=spec_file,
        discovery_file=discovery_path,
        feature_description=feature_description,
    )

    handoff_result = _run_specify_handoff_round(
        env=env,
        handoff_input=handoff_input,
        timeout_seconds=timeout_seconds,
    )
    if not handoff_result.get("ok"):
        if "generated_artifact" not in handoff_result:
            handoff_result["generated_artifact"] = {
                "path": str(spec_file),
                "completion_marker": SPEC_ROUTING_MARKER,
            }
        handoff_result["spec_file"] = str(spec_file)
        handoff_result["discovery_file"] = str(discovery_path)
        return handoff_result

    validation_result = _validate_spec_routing(spec_file, env)
    retry_index = 0
    while not bool(validation_result.get("ok")) and retry_index < 1:
        retry_index += 1
        retry_handoff_input = _build_specify_handoff_input(
            feature_id=feature_id,
            phase=phase,
            correlation_id=correlation_id,
            feature_dir=feature_dir,
            spec_file=spec_file,
            discovery_file=discovery_path,
            feature_description=feature_description,
            resume_session=True,
            retry_index=retry_index,
            qa_feedback=validation_result,
        )
        handoff_result = _run_specify_handoff_round(
            env=env,
            handoff_input=retry_handoff_input,
            timeout_seconds=timeout_seconds,
        )
        if not handoff_result.get("ok"):
            if "generated_artifact" not in handoff_result:
                handoff_result["generated_artifact"] = {
                    "path": str(spec_file),
                    "completion_marker": SPEC_ROUTING_MARKER,
                }
            handoff_result["spec_file"] = str(spec_file)
            handoff_result["discovery_file"] = str(discovery_path)
            return handoff_result
        validation_result = _validate_spec_routing(spec_file, env)

    if not bool(validation_result.get("ok")):
        debug_path = _write_debug_payload(
            correlation_id=correlation_id,
            payload={
                "stage": "validation",
                "feature_id": feature_id,
                "feature_dir": str(feature_dir),
                "spec_file": str(spec_file),
                "discovery_file": str(discovery_path),
                "handoff_result": handoff_result,
                "validation_result": validation_result,
            },
        )
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "spec_validation",
            "reasons": list(validation_result.get("reasons") or ["routing_contract_invalid"]),
            "error_code": None,
            "next_phase": None,
            "debug_path": debug_path,
            "generated_artifact": handoff_result.get("generated_artifact")
            or {
                "path": str(spec_file),
                "completion_marker": SPEC_ROUTING_MARKER,
            },
            "validation": validation_result,
            "spec_file": str(spec_file),
            "discovery_file": str(discovery_path),
        }

    generated_artifact = dict(
        handoff_result.get("generated_artifact")
        or {
            "path": str(spec_file),
            "completion_marker": SPEC_ROUTING_MARKER,
        }
    )
    generated_artifact["path"] = str(spec_file)
    generated_artifact["completion_marker"] = SPEC_ROUTING_MARKER

    return {
        **handoff_result,
        "next_phase": determine_next_phase("specify", routing_contract=validation_result),
        "generated_artifact": generated_artifact,
        "validation": validation_result,
        "spec_file": str(spec_file),
        "discovery_file": str(discovery_path),
    }


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for both bootstrap and deterministic step modes."""
    parser = argparse.ArgumentParser(description="Specify bootstrap and deterministic step runner")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary output")
    parser.add_argument("--short-name", default="", help="Optional short name for the feature")
    parser.add_argument("--feature-id", default="", help="Feature id for deterministic step mode")
    parser.add_argument("--phase", default="specify", help="Pipeline phase for deterministic step mode")
    parser.add_argument(
        "--correlation-id",
        default="",
        help="Correlation id for deterministic step mode",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout for the Codex handoff runner in deterministic step mode",
    )
    parser.add_argument(
        "--handoff-runner",
        default="",
        help="Optional command used to execute the Codex handoff runner",
    )
    parser.add_argument(
        "feature_description",
        nargs="?",
        default="",
        help="Feature description used to bootstrap a new spec scaffold",
    )
    return parser


def main(argv: list[str]) -> int:
    """Run the bootstrap helper or deterministic specify step."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        env = _build_uv_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    feature_id = str(args.feature_id).strip()
    correlation_id = str(args.correlation_id).strip()
    phase = str(args.phase).strip() or "specify"

    if feature_id and correlation_id:
        try:
            step_result = _run_step_mode(
                feature_id=feature_id,
                phase=phase,
                correlation_id=correlation_id,
                env=env,
                timeout_seconds=max(1, int(args.timeout_seconds)),
            )
        except RuntimeError as exc:
            debug_path = _write_debug_payload(
                correlation_id=correlation_id or "unknown",
                payload={
                    "stage": "deterministic_step",
                    "error_code": "specify_step_unhandled_exception",
                    "exception": str(exc),
                    "feature_id": feature_id,
                    "phase": phase,
                },
            )
            step_result = {
                "schema_version": "1.0.0",
                "ok": False,
                "exit_code": 2,
                "correlation_id": correlation_id or "unknown",
                "gate": None,
                "reasons": ["specify_step_unhandled_exception"],
                "error_code": "specify_step_unhandled_exception",
                "next_phase": None,
                "debug_path": debug_path,
            }

        print(json.dumps(step_result, separators=(",", ":")))
        return int(step_result.get("exit_code", 1))

    description = str(args.feature_description).strip()
    if not description:
        print("ERROR: No feature description provided", file=sys.stderr)
        return 1

    try:
        summary = _run_bootstrap_mode(description, str(args.short_name).strip(), env)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, separators=(",", ":")))
        return 0

    print("Discovery")
    for result in summary["DISCOVERY"]:
        print(_render_discovery_result(result))
        print()
    print()
    print("Scaffolded")
    print(f"- spec: {summary['SPEC_FILE']}")
    print(f"- discovery: {summary['DISCOVERY_FILE']}")
    print(f"- branch: {summary['BRANCH_NAME']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
