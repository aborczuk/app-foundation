"""Run a Codex CLI handoff and materialize the generated artifact."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


def _load_payload(stdin_text: str) -> dict[str, Any]:
    """Parse the driver payload from stdin."""
    if not stdin_text.strip():
        raise ValueError("stdin payload is required")
    parsed = json.loads(stdin_text)
    if not isinstance(parsed, dict):
        raise ValueError("stdin payload must be a JSON object")
    return parsed


def _source_codex_home() -> Path:
    """Return the Codex home that holds the user's auth material."""
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home)
    return Path.home() / ".codex"


def _copy_codex_home(source_home: Path, target_home: Path) -> None:
    """Seed a writable CODEX_HOME with the user's auth files."""
    target_home.mkdir(parents=True, exist_ok=True)
    for filename in ("auth.json", "config.toml"):
        source_path = source_home / filename
        if source_path.exists():
            shutil.copy2(source_path, target_home / filename)
    if not (target_home / "auth.json").exists():
        raise FileNotFoundError(f"missing Codex auth file: {source_home / 'auth.json'}")


def _build_codex_prompt(payload: Mapping[str, Any]) -> str:
    """Ask Codex for a short summary string for the generated artifact."""
    handoff = payload.get("handoff", {})
    if not isinstance(handoff, Mapping):
        raise ValueError("handoff must be a mapping")
    prompt_payload = {
        "feature_id": payload.get("feature_id"),
        "phase": payload.get("phase"),
        "correlation_id": payload.get("correlation_id"),
        "handoff_id": handoff.get("handoff_id"),
        "step_name": handoff.get("step_name"),
        "completion_marker": handoff.get("completion_marker", "## Summary"),
    }
    return "\n".join(
        [
            "Return JSON only with a single key named `summary`.",
            "The summary must be one short sentence that mentions the feature_id and phase.",
            "Do not wrap the response in markdown fences.",
            "Input:",
            json.dumps(prompt_payload, sort_keys=True, indent=2),
        ]
    )


def _run_codex_exec(
    *,
    prompt: str,
    repo_root: Path,
    codex_home: Path,
    output_schema_path: Path,
    output_last_message_path: Path,
) -> subprocess.CompletedProcess[str]:
    """Invoke `codex exec` non-interactively and capture the final message."""
    codex_bin = os.environ.get("CODEX_BIN") or shutil.which("codex")
    if not codex_bin:
        raise FileNotFoundError("codex binary not found on PATH; set CODEX_BIN to override")

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    command = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--cd",
        str(repo_root),
        "--output-last-message",
        str(output_last_message_path),
        "--output-schema",
        str(output_schema_path),
    ]
    return subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=repo_root,
    )


def _write_output_schema(schema_path: Path) -> None:
    """Write the JSON schema that constrains the Codex response."""
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
                "additionalProperties": False,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _render_artifact(
    *,
    artifact_path: Path,
    payload: Mapping[str, Any],
    summary: str,
    completion_marker: str,
) -> None:
    """Write the generated artifact using the model summary and handoff metadata."""
    handoff = payload.get("handoff", {})
    if not isinstance(handoff, Mapping):
        raise ValueError("handoff must be a mapping")
    lines = [
        "# Codex Handoff",
        "",
        f"- feature_id: {payload.get('feature_id')}",
        f"- phase: {payload.get('phase')}",
        f"- correlation_id: {payload.get('correlation_id')}",
        f"- handoff_id: {handoff.get('handoff_id')}",
        f"- step_name: {handoff.get('step_name')}",
        "",
        completion_marker,
        "",
        summary.strip(),
        "",
    ]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("\n".join(lines), encoding="utf-8")


def run_handoff(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run a live Codex handoff and return the driver-compatible result payload."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a mapping")
    handoff = payload.get("handoff", {})
    if not isinstance(handoff, Mapping):
        raise ValueError("handoff must be a mapping")

    artifact_value = handoff.get("output_template_path")
    if not isinstance(artifact_value, str) or not artifact_value.strip():
        raise ValueError("handoff.output_template_path is required")
    artifact_path = Path(artifact_value)

    completion_marker = handoff.get("completion_marker")
    if not isinstance(completion_marker, str) or not completion_marker.strip():
        completion_marker = "## Summary"

    repo_root = Path(__file__).resolve().parents[1]
    prompt = _build_codex_prompt(payload)

    with tempfile.TemporaryDirectory(prefix="codex-home-") as codex_home_name, tempfile.TemporaryDirectory(
        prefix="codex-run-"
    ) as run_dir_name:
        codex_home = Path(codex_home_name)
        run_dir = Path(run_dir_name)
        _copy_codex_home(_source_codex_home(), codex_home)

        output_schema_path = run_dir / "output-schema.json"
        output_last_message_path = run_dir / "last-message.json"
        _write_output_schema(output_schema_path)

        execution = _run_codex_exec(
            prompt=prompt,
            repo_root=repo_root,
            codex_home=codex_home,
            output_schema_path=output_schema_path,
            output_last_message_path=output_last_message_path,
        )
        if execution.returncode != 0:
            raise RuntimeError(
                "codex exec failed with exit code "
                f"{execution.returncode}: {execution.stderr.strip() or execution.stdout.strip()}"
            )

        last_message_text = output_last_message_path.read_text(encoding="utf-8").strip()
        if not last_message_text:
            raise RuntimeError("codex exec did not write a last message")
        parsed_message = json.loads(last_message_text)
        if not isinstance(parsed_message, dict):
            raise RuntimeError("codex last message must be a JSON object")

        summary = parsed_message.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError("codex summary response is missing")

        _render_artifact(
            artifact_path=artifact_path,
            payload=payload,
            summary=summary,
            completion_marker=completion_marker,
        )

    return {
        "artifact_path": str(artifact_path),
        "completion_marker": completion_marker,
        "summary": summary,
        "runner": "codex exec",
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Read the driver payload from stdin and emit the runner result as JSON."""
    del argv
    payload = _load_payload(sys.stdin.read())
    result = run_handoff(payload)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
