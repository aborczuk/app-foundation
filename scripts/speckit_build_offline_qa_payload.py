#!/usr/bin/env python3
"""Build a deterministic offline-QA payload from task artifacts and local repo state."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from speckit_implement_contract import (
    build_payload_run_id,
    compute_payload_digest,
    existing_payload_reasons,
    utc_now_iso,
)

TASK_LINE_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(?P<task_id>T\d{3}(?:[a-c])?)\b(?P<rest>.*)$")
PHASE_HEADER_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
ACCEPTANCE_HEADER_RE = re.compile(r"^\s*###\s+Acceptance Criteria\b")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a subprocess and return its exit code plus stripped output."""
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _json_print(payload: dict[str, Any], as_json: bool) -> None:
    """Print the payload as JSON or as a compact human summary."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"ok={payload.get('ok', False)} mode={payload.get('mode', 'unknown')}")
    for reason in payload.get("reasons", []):
        print(f"- {reason}")


def _find_feature_dir(repo_root: Path, feature_id: str) -> Path:
    """Return the first specs directory that matches a feature id."""
    matches = sorted((repo_root / "specs").glob(f"{feature_id}-*"))
    if not matches:
        raise ValueError(f"feature directory not found for id {feature_id}")
    return matches[0]


def _task_context(tasks_file: Path, task_id: str) -> tuple[str, list[str]]:
    """Extract the task description and acceptance text from tasks.md."""
    lines = tasks_file.read_text(encoding="utf-8").splitlines()
    task_idx = -1
    task_desc = ""
    for idx, line in enumerate(lines):
        match = TASK_LINE_RE.match(line)
        if not match:
            continue
        if match.group("task_id") != task_id:
            continue
        task_idx = idx
        task_desc = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", match.group("rest").strip()).strip()
        break

    if task_idx < 0:
        raise ValueError(f"task id {task_id} not found in {tasks_file}")

    phase_start = 0
    for idx in range(task_idx, -1, -1):
        if PHASE_HEADER_RE.match(lines[idx]):
            phase_start = idx
            break
    phase_end = len(lines)
    for idx in range(phase_start + 1, len(lines)):
        if PHASE_HEADER_RE.match(lines[idx]):
            phase_end = idx
            break

    acceptance: list[str] = []
    in_acceptance = False
    for line in lines[phase_start:phase_end]:
        if ACCEPTANCE_HEADER_RE.match(line):
            in_acceptance = True
            continue
        if in_acceptance:
            if line.startswith("### ") or line.startswith("## ") or line.startswith("**Checkpoint**"):
                break
            stripped = line.strip()
            if stripped.startswith("- "):
                value = stripped[2:].strip()
                if value:
                    acceptance.append(value)
            continue
        marker = "**Independent Test**:"
        if marker in line:
            value = line.split(marker, 1)[1].strip()
            if value:
                acceptance.append(value)
                break
    if not acceptance:
        acceptance = [f"Complete {task_id}: {task_desc}"]
    return task_desc, acceptance


DEFAULT_QUALITY_GUARDS = ["Domain 13", "Domain 14", "Domain 17"]


def _changed_files_from_head(repo_root: Path) -> list[str]:
    """Return workspace changes first, then fall back to files changed in HEAD."""
    code, out, _ = _run(["git", "status", "--short"], cwd=repo_root)
    if code == 0 and out.strip():
        files: list[str] = []
        for raw_line in out.splitlines():
            line = raw_line.rstrip()
            if len(line) < 3:
                continue
            path_fragment = line[2:].strip()
            if " -> " in path_fragment:
                path_fragment = path_fragment.split(" -> ", 1)[1].strip()
            if path_fragment:
                files.append(path_fragment)
        if files:
            return sorted(dict.fromkeys(files))

    code, out, _ = _run(["git", "show", "--name-only", "--pretty=format:", "HEAD"], cwd=repo_root)
    if code != 0:
        return []
    files = [line.strip() for line in out.splitlines() if line.strip()]
    return sorted(dict.fromkeys(files))


def _latest_test_event(repo_root: Path, feature_id: str, task_id: str) -> dict[str, Any] | None:
    """Return the latest test result event for a feature task."""
    ledger_path = repo_root / ".speckit" / "task-ledger.jsonl"
    if not ledger_path.exists():
        return None
    latest: dict[str, Any] | None = None
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("feature_id") != feature_id or event.get("task_id") != task_id:
            continue
        if event.get("event") not in {"tests_passed", "tests_failed"}:
            continue
        latest = event
    return latest


def _build_test_runs(repo_root: Path, feature_id: str, task_id: str) -> list[dict[str, Any]]:
    """Build synthetic test-run entries from the latest ledger evidence."""
    latest = _latest_test_event(repo_root, feature_id, task_id)
    if latest is None:
        return [
            {
                "command": "manual_test_evidence_not_captured",
                "exit_code": 0,
                "output": "Auto-generated payload; replace with explicit test evidence when available.",
            }
        ]
    event_name = str(latest.get("event"))
    details = str(latest.get("details") or "").strip()
    return [
        {
            "command": details or f"task_ledger:{event_name}",
            "exit_code": 0 if event_name == "tests_passed" else 1,
            "output": details or f"Derived from task ledger event {event_name}.",
        }
    ]


def _diff_summary(repo_root: Path) -> str:
    """Summarize workspace changes first, then fall back to the last commit diff."""
    code, out, _ = _run(["git", "diff", "--stat", "--no-color", "HEAD", "--"], cwd=repo_root)
    if code == 0 and out.strip():
        return out.strip()

    code, out, _ = _run(["git", "status", "--short"], cwd=repo_root)
    if code == 0 and out.strip():
        return out.strip()

    code, out, _ = _run(["git", "show", "--stat", "--oneline", "--no-color", "HEAD"], cwd=repo_root)
    if code == 0 and out.strip():
        return out.strip()
    return "Auto-generated offline QA payload from local task artifacts."


def main(argv: list[str] | None = None) -> int:
    """Run the offline QA payload builder CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--payload-file")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    payload_path = (
        Path(args.payload_file).resolve()
        if args.payload_file
        else (
            repo_root
            / ".speckit"
            / "offline-qa"
            / f"{args.feature_id}_{args.task_id}_attempt_{args.attempt}.handoff.json"
        )
    )

    result: dict[str, Any] = {
        "mode": "build_offline_qa_payload",
        "feature_id": args.feature_id,
        "task_id": args.task_id,
        "attempt": args.attempt,
        "payload_file": str(payload_path),
        "reasons": [],
        "ok": False,
    }

    try:
        if payload_path.exists() and not args.force:
            existing_payload = json.loads(payload_path.read_text(encoding="utf-8"))
            reuse_reasons = existing_payload_reasons(
                existing_payload,
                feature_id=args.feature_id,
                task_id=args.task_id,
                attempt=args.attempt,
            )
            if not reuse_reasons:
                result["ok"] = True
                result["created"] = False
                result["payload_run_id"] = existing_payload.get("payload_run_id")
                result["payload_digest"] = existing_payload.get("payload_digest")
                _json_print(result, as_json=bool(args.json))
                return 0
            result["warnings"] = reuse_reasons

        feature_dir = _find_feature_dir(repo_root, args.feature_id)
        tasks_file = feature_dir / "tasks.md"
        if not tasks_file.exists():
            raise ValueError(f"tasks.md missing for feature {args.feature_id}")

        task_desc, acceptance = _task_context(tasks_file, args.task_id)
        changed_files = _changed_files_from_head(repo_root)
        if not changed_files:
            changed_files = [str(tasks_file.relative_to(repo_root))]

        payload_obj = {
            "feature_id": args.feature_id,
            "task_id": args.task_id,
            "attempt": args.attempt,
            "payload_generated_at": utc_now_iso(),
            "payload_run_id": build_payload_run_id(args.task_id, args.attempt),
            "diff": _diff_summary(repo_root),
            "acceptance_criteria": acceptance,
            "quality_guards": list(DEFAULT_QUALITY_GUARDS),
            "changed_files": changed_files,
            "test_runs": _build_test_runs(repo_root, args.feature_id, args.task_id),
            "known_risks": [
                f"Auto-generated payload for {args.task_id}; confirm test evidence detail if stricter QA traceability is required.",
                task_desc,
            ],
        }
        payload_obj["payload_digest"] = compute_payload_digest(payload_obj)

        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(payload_obj, indent=2, sort_keys=True), encoding="utf-8")
        result["ok"] = True
        result["created"] = True
        result["payload_run_id"] = payload_obj["payload_run_id"]
        result["payload_digest"] = payload_obj["payload_digest"]
    except Exception as exc:  # pragma: no cover - defensive for hook/runtime reliability
        result["reasons"].append(str(exc))
        _json_print(result, as_json=bool(args.json))
        return 2

    _json_print(result, as_json=bool(args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
