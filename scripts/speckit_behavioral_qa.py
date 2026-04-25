#!/usr/bin/env python3
"""Behavioral QA agent for verifying implementation against acceptance criteria.

Reads HUD acceptance criteria, runs actual tests for changed files,
and checks for implementation drift against the task contract.

Emits a structured verdict: PASS or FIX_REQUIRED with specific findings.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

VERDICT_PASS = "PASS"
VERDICT_FIX_REQUIRED = "FIX_REQUIRED"


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> tuple[int, str, str]:
    """Execute a subprocess command and capture output."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"


def _json_print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _read_hud(hud_path: Path) -> dict[str, Any]:
    """Parse HUD markdown and extract key sections."""
    if not hud_path.exists():
        return {"error": f"HUD not found: {hud_path}"}

    content = hud_path.read_text(encoding="utf-8")
    hud: dict[str, Any] = {
        "acceptance_criteria": "",
        "file_symbol": "",
        "quality_guards": [],
        "touched_symbols": [],
    }

    # Extract acceptance criteria from Functional Goal section
    ac_match = re.search(
        r"##\s+Functional Goal\s+.*?\*\*Acceptance Criteria\*\*:\s*(.*?)(?=\n##|\Z)",
        content,
        re.DOTALL,
    )
    if ac_match:
        hud["acceptance_criteria"] = ac_match.group(1).strip()

    # Extract File:Symbol
    fs_match = re.search(r"\*\*File:Symbol\*\*:\s*`?([^`\n]+)`?", content)
    if fs_match:
        hud["file_symbol"] = fs_match.group(1).strip()

    # Extract quality guards
    in_qg = False
    for line in content.splitlines():
        if line.strip().startswith("## Quality Guards"):
            in_qg = True
            continue
        if in_qg and line.startswith("## "):
            break
        if in_qg and line.strip().startswith("-"):
            guard = line.strip().lstrip("- ").strip()
            if guard:
                hud["quality_guards"].append(guard)

    return hud


def _read_tasks_acceptance(tasks_file: Path, task_id: str) -> str:
    """Extract 'Independent Test' from tasks.md for the task's phase."""
    if not tasks_file.exists():
        return ""

    lines = tasks_file.read_text(encoding="utf-8").splitlines()
    task_idx = -1
    for idx, line in enumerate(lines):
        if task_id in line and line.strip().startswith("-"):
            task_idx = idx
            break

    if task_idx < 0:
        return ""

    # Find phase bounds
    phase_start = 0
    for idx in range(task_idx, -1, -1):
        if lines[idx].startswith("## "):
            phase_start = idx
            break

    phase_end = len(lines)
    for idx in range(phase_start + 1, len(lines)):
        if lines[idx].startswith("## "):
            phase_end = idx
            break

    for line in lines[phase_start:phase_end]:
        marker = "**Independent Test**:"
        if marker in line:
            return line.split(marker, 1)[1].strip()

    return ""


def _run_tests_for_files(
    repo_root: Path, changed_files: list[str], task_id: str
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    """Run pytest for test files related to changed files."""
    test_runs: list[dict[str, Any]] = []
    warnings: list[str] = []

    # Find test files that might cover the changed files
    test_files: set[str] = set()
    for cf in changed_files:
        if cf.startswith("tests/"):
            test_files.add(cf)
            continue
        # Guess test file from source file
        if cf.startswith("src/"):
            rel = cf[4:]  # strip src/
            parts = rel.split("/")
            module = parts[-1].replace(".py", "")
            # Look for matching test files
            test_path = repo_root / "tests" / "unit" / f"test_{module}.py"
            if test_path.exists():
                test_files.add(str(test_path.relative_to(repo_root)))
            test_path = repo_root / "tests" / "integration" / f"test_{module}.py"
            if test_path.exists():
                test_files.add(str(test_path.relative_to(repo_root)))

    if not test_files:
        warnings.append(f"No test files found for changed files: {changed_files}")
        # Try running pytest with task_id as keyword filter
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "-k",
            task_id.lower(),
            "--tb=short",
        ]
        exit_code, stdout, stderr = _run(cmd, cwd=repo_root)
        test_runs.append(
            {
                "command": " ".join(cmd),
                "exit_code": exit_code,
                "output": stdout + (f"\nSTDERR:\n{stderr}" if stderr else ""),
            }
        )
        return exit_code == 0, test_runs, warnings

    for tf in sorted(test_files):
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            tf,
            "-v",
            "--tb=short",
        ]
        exit_code, stdout, stderr = _run(cmd, cwd=repo_root)
        test_runs.append(
            {
                "command": " ".join(cmd),
                "exit_code": exit_code,
                "output": stdout + (f"\nSTDERR:\n{stderr}" if stderr else ""),
            }
        )

    all_passed = all(run["exit_code"] == 0 for run in test_runs)
    return all_passed, test_runs, warnings


def _check_file_symbol_changed(
    repo_root: Path, changed_files: list[str], file_symbol: str
) -> tuple[bool, str]:
    """Check if the HUD's File:Symbol was actually modified."""
    if not file_symbol:
        return True, "No file_symbol in HUD"

    file_part = file_symbol.split(":")[0].strip()
    if file_part in changed_files:
        return True, f"Primary file {file_part} was modified"

    # Check if any related file was changed
    for cf in changed_files:
        if cf.endswith(file_part.split("/")[-1]):
            return True, f"Related file {cf} was modified"

    return False, f"Primary file {file_part} NOT in changed_files: {changed_files}"


def _check_acceptance_in_diff(
    repo_root: Path, changed_files: list[str], acceptance_criteria: str
) -> tuple[bool, list[str]]:
    """Heuristic check: does the diff plausibly address acceptance criteria?"""
    if not acceptance_criteria:
        return False, ["Missing acceptance criteria in HUD or tasks.md"]

    findings: list[str] = []

    # Extract key nouns/verbs from acceptance criteria
    keywords = set()
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", acceptance_criteria):
        if len(word) > 3 and word.lower() not in {
            "the", "and", "for", "with", "from", "that", "this", "into", "over",
            "add", "implementation", "deterministic", "behavior", "verified",
        }:
            keywords.add(word.lower())

    # Read changed files and look for keyword matches
    matched_any = False
    for cf in changed_files:
        if not cf.endswith(".py"):
            continue
        path = repo_root / cf
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").lower()
        matches = [kw for kw in keywords if kw in content]
        if matches:
            matched_any = True

    if not matched_any:
        findings.append(
            f"Changed files do not appear to address acceptance criteria keywords: {sorted(keywords)[:10]}"
        )

    return len(findings) == 0, findings


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for behavioral QA agent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--result-file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    payload_path = Path(args.payload_file).resolve()
    result_path = Path(args.result_file) if args.result_file else None

    findings: list[str] = []
    warnings: list[str] = []
    test_runs: list[dict[str, Any]] = []

    result: dict[str, Any] = {
        "mode": "behavioral_qa",
        "payload_file": str(payload_path),
        "verdict": VERDICT_FIX_REQUIRED,
        "findings": findings,
        "warnings": warnings,
        "test_runs": test_runs,
    }

    # Read payload
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        findings.append(f"Invalid payload: {exc}")
        _json_print(result)
        if result_path:
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return 1

    feature_id = payload.get("feature_id", "")
    task_id = payload.get("task_id", "")
    result["feature_id"] = feature_id
    result["task_id"] = task_id

    # Resolve feature directory
    specs_root = repo_root / "specs"
    feature_dirs = list(specs_root.glob(f"{feature_id}-*"))
    if not feature_dirs:
        findings.append(f"Feature directory not found for {feature_id}")
        _json_print(result)
        if result_path:
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return 1

    feature_dir = feature_dirs[0]
    tasks_file = feature_dir / "tasks.md"
    hud_path = feature_dir / "huds" / f"{task_id}.md"

    # Read HUD or tasks.md for acceptance criteria
    hud = _read_hud(hud_path)
    acceptance = hud.get("acceptance_criteria", "")
    file_symbol = hud.get("file_symbol", "")

    if not acceptance:
        acceptance = _read_tasks_acceptance(tasks_file, task_id)

    if not acceptance:
        findings.append("MISSING_ACCEPTANCE_CRITERIA: No acceptance criteria found in HUD or tasks.md")

    # Check changed files
    changed_files = payload.get("changed_files", [])
    if not changed_files:
        findings.append("MISSING_CHANGED_FILES: No changed files in payload")

    # Check if primary file was modified
    if file_symbol and changed_files:
        symbol_ok, symbol_msg = _check_file_symbol_changed(repo_root, changed_files, file_symbol)
        if not symbol_ok:
            findings.append(f"IMPLEMENTATION_DRIFT: {symbol_msg}")
        else:
            warnings.append(f"file_symbol_check: {symbol_msg}")

    # Check acceptance criteria against diff
    if acceptance and changed_files:
        ac_ok, ac_findings = _check_acceptance_in_diff(repo_root, changed_files, acceptance)
        findings.extend(ac_findings)

    # Run actual tests
    if changed_files:
        tests_passed, runs, test_warnings = _run_tests_for_files(repo_root, changed_files, task_id)
        test_runs.extend(runs)
        warnings.extend(test_warnings)
        if not tests_passed:
            findings.append("TESTS_FAILED: One or more test runs failed")
    else:
        findings.append("MISSING_TEST_EVIDENCE: No changed files to test")

    # Determine verdict
    if not findings:
        result["verdict"] = VERDICT_PASS
        warnings.append("Behavioral QA passed: acceptance criteria, file changes, and tests verified.")

    result["findings"] = findings
    result["warnings"] = warnings
    result["test_runs"] = test_runs
    result["acceptance_criteria"] = acceptance
    result["file_symbol"] = file_symbol

    _json_print(result)

    if result_path:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    return 0 if result["verdict"] == VERDICT_PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
