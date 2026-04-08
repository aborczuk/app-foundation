#!/usr/bin/env python3
"""Local offline QA runner for per-task implementation handoffs.

The runner evaluates a task handoff payload and emits a deterministic verdict:
- PASS
- FIX_REQUIRED

This is intentionally local/offline and does not require network calls.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERDICT_PASS = "PASS"
VERDICT_FIX_REQUIRED = "FIX_REQUIRED"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_qa_run_id(task_id: str) -> str:
    """Build a deterministic offline QA run identifier for a task."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_task = (task_id or "unknown").lower()
    return f"offline-qa-{safe_task}-{timestamp}"


def read_payload(path: Path) -> dict[str, Any]:
    """Load and validate the handoff payload JSON object from disk."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Payload file not found: {path}") from exc
    except OSError as exc:
        raise ValueError(f"Unable to read payload file {path}: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Payload file contains invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Payload JSON must be an object.")
    return parsed


def _as_non_empty_str(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return ""


def evaluate_payload(payload: dict[str, Any]) -> tuple[str, str, list[str], list[str]]:
    """Validate payload contract and return feature/task IDs with findings/messages."""
    findings: list[str] = []
    warnings: list[str] = []

    feature_id = _as_non_empty_str(payload.get("feature_id"))
    task_id = _as_non_empty_str(payload.get("task_id"))
    if not feature_id:
        findings.append("Missing required non-empty string field: feature_id.")
    if not task_id:
        findings.append("Missing required non-empty string field: task_id.")

    acceptance = payload.get("acceptance_criteria")
    if not isinstance(acceptance, list) or not acceptance:
        findings.append("Missing required non-empty list field: acceptance_criteria.")
    elif any(not _as_non_empty_str(item) for item in acceptance):
        findings.append("acceptance_criteria must contain only non-empty strings.")

    changed_files = payload.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files:
        findings.append("Missing required non-empty list field: changed_files.")
    elif any(not _as_non_empty_str(item) for item in changed_files):
        findings.append("changed_files must contain only non-empty strings.")

    diff_text = payload.get("diff")
    if not _as_non_empty_str(diff_text):
        findings.append("Missing required non-empty string field: diff.")

    test_runs = payload.get("test_runs")
    if (not isinstance(test_runs, list) or not test_runs) and isinstance(
        payload.get("test_commands"), list
    ):
        normalized_runs: list[dict[str, Any]] = []
        for raw in payload["test_commands"]:
            if not isinstance(raw, dict):
                continue
            normalized_runs.append(
                {
                    "command": raw.get("command"),
                    "exit_code": raw.get("exit_code", 0),
                    "output": raw.get("output"),
                }
            )
        if normalized_runs:
            test_runs = normalized_runs
            warnings.append("Normalized legacy test_commands payload into test_runs.")

    if not isinstance(test_runs, list) or not test_runs:
        findings.append("Missing required non-empty list field: test_runs.")
    else:
        for idx, run in enumerate(test_runs, start=1):
            if not isinstance(run, dict):
                findings.append(f"test_runs[{idx}] must be an object.")
                continue
            command = _as_non_empty_str(run.get("command"))
            exit_code = run.get("exit_code")
            if not command:
                findings.append(f"test_runs[{idx}] missing non-empty command.")
            if not isinstance(exit_code, int):
                findings.append(f"test_runs[{idx}] missing integer exit_code.")
                continue
            if exit_code != 0:
                findings.append(
                    f"test_runs[{idx}] failed: command={command!r} exit_code={exit_code}."
                )

    known_risks = payload.get("known_risks")
    if isinstance(known_risks, list):
        warnings.extend(
            f"Known risk: {risk.strip()}"
            for risk in known_risks
            if isinstance(risk, str) and risk.strip()
        )

    if findings:
        summary = (
            f"Offline QA found {len(findings)} blocking issue(s); task requires fixes."
        )
        return feature_id, task_id, findings, [summary, *warnings]

    summary = "Offline QA passed: payload contract and test evidence are valid."
    return feature_id, task_id, findings, [summary, *warnings]


def build_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the final QA verdict payload for stdout/result-file emission."""
    feature_id, task_id, findings, messages = evaluate_payload(payload)
    verdict = VERDICT_PASS if not findings else VERDICT_FIX_REQUIRED
    result: dict[str, Any] = {
        "timestamp_utc": utc_now_iso(),
        "qa_run_id": build_qa_run_id(task_id),
        "feature_id": feature_id,
        "task_id": task_id,
        "verdict": verdict,
        "findings": findings,
        "messages": messages,
    }
    return result


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the offline QA runner."""
    parser = argparse.ArgumentParser(
        description="Evaluate a local offline QA handoff payload and emit PASS/FIX_REQUIRED.",
    )
    parser.add_argument(
        "--payload-file",
        required=True,
        help="Path to JSON handoff payload.",
    )
    parser.add_argument(
        "--result-file",
        help="Optional path to write verdict JSON.",
    )
    return parser.parse_args()


def write_result(path: Path, payload: dict[str, Any]) -> None:
    """Persist the result JSON to disk, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def main() -> int:
    """Run offline QA evaluation and return POSIX-style success/failure codes."""
    args = parse_args()
    payload_path = Path(args.payload_file)
    result_path = Path(args.result_file) if args.result_file else None

    try:
        payload = read_payload(payload_path)
        result = build_result(payload)
    except ValueError as exc:
        result = {
            "timestamp_utc": utc_now_iso(),
            "qa_run_id": build_qa_run_id("unknown"),
            "feature_id": "",
            "task_id": "",
            "verdict": VERDICT_FIX_REQUIRED,
            "findings": [str(exc)],
            "messages": ["Offline QA failed to parse handoff payload."],
        }

    output = json.dumps(result, sort_keys=True)
    print(output)

    if result_path:
        write_result(result_path, result)

    return 0 if result["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
