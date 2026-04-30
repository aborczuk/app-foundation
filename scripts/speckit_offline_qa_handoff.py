#!/usr/bin/env python3
"""Run offline QA handoff using deterministic defaults and gate checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _default_paths(repo_root: Path, feature_id: str, task_id: str, attempt: int) -> tuple[Path, Path]:
    qa_dir = repo_root / ".speckit" / "offline-qa"
    stem = f"{feature_id}_{task_id}_attempt_{attempt}"
    return qa_dir / f"{stem}.handoff.json", qa_dir / f"{stem}.result.json"


def _json_print(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload['ok']} mode={payload['mode']}")
    print(f"payload_file={payload['payload_file']}")
    print(f"result_file={payload['result_file']}")
    for reason in payload.get("reasons", []):
        print(f"- {reason}")


def run_offline_qa_handoff(
    *,
    feature_id: str,
    task_id: str,
    attempt: int = 1,
    payload_file: Path | None = None,
    result_file: Path | None = None,
    no_autobuild_payload: bool = False,
) -> dict[str, Any]:
    """Run the offline QA handoff and return the structured payload."""
    repo_root = Path(__file__).resolve().parent.parent
    default_payload, default_result = _default_paths(repo_root, feature_id, task_id, attempt)

    payload_file = Path(payload_file).resolve() if payload_file else default_payload
    result_file = Path(result_file).resolve() if result_file else default_result

    payload: dict[str, Any] = {
        "mode": "offline_qa_handoff",
        "feature_id": feature_id,
        "task_id": task_id,
        "attempt": attempt,
        "payload_file": str(payload_file),
        "result_file": str(result_file),
        "reasons": [],
        "ok": False,
    }

    if not payload_file.exists():
        if no_autobuild_payload:
            payload["reasons"].append("missing_payload_file")
            return payload

        build_cmd = [
            sys.executable,
            str(repo_root / "scripts" / "speckit_build_offline_qa_payload.py"),
            "--feature-id",
            feature_id,
            "--task-id",
            task_id,
            "--attempt",
            str(attempt),
            "--payload-file",
            str(payload_file),
            "--json",
        ]
        build_code, build_out, build_err = _run(build_cmd, cwd=repo_root)
        payload["payload_autobuild_exit_code"] = build_code
        payload["payload_autobuild_stdout"] = build_out
        if build_err:
            payload["payload_autobuild_stderr"] = build_err
        if build_code != 0 or not payload_file.exists():
            payload["reasons"].append("payload_autobuild_failed")
            return payload
        payload["payload_autobuild"] = "created"

    validate_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "speckit_implement_gate.py"),
        "validate-offline-qa-payload",
        "--payload-file",
        str(payload_file),
        "--json",
    ]
    validate_code, validate_out, validate_err = _run(validate_cmd, cwd=repo_root)
    payload["validate_exit_code"] = validate_code
    payload["validate_stdout"] = validate_out
    if validate_err:
        payload["validate_stderr"] = validate_err
    if validate_code != 0:
        payload["reasons"].append("offline_payload_invalid")
        return payload

    result_file.parent.mkdir(parents=True, exist_ok=True)
    qa_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "offline_qa.py"),
        "--payload-file",
        str(payload_file),
        "--result-file",
        str(result_file),
    ]
    qa_code, qa_out, qa_err = _run(qa_cmd, cwd=repo_root)
    payload["offline_qa_exit_code"] = qa_code
    payload["offline_qa_stdout"] = qa_out
    if qa_err:
        payload["offline_qa_stderr"] = qa_err

    if result_file.exists():
        try:
            result_json = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload["reasons"].append("invalid_result_json")
            return payload
        payload["result_verdict"] = result_json.get("verdict")
        payload["qa_run_id"] = result_json.get("qa_run_id")

    payload["ok"] = qa_code == 0
    return payload


def main(argv: list[str] | None = None) -> int:
    """Validate and execute one offline-QA handoff attempt for a task."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--payload-file")
    parser.add_argument("--result-file")
    parser.add_argument(
        "--no-autobuild-payload",
        action="store_true",
        help="Disable automatic payload generation when payload file is missing.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = run_offline_qa_handoff(
        feature_id=args.feature_id,
        task_id=args.task_id,
        attempt=args.attempt,
        payload_file=Path(args.payload_file) if args.payload_file else None,
        result_file=Path(args.result_file) if args.result_file else None,
        no_autobuild_payload=args.no_autobuild_payload,
    )
    _json_print(payload, as_json=bool(args.json))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
