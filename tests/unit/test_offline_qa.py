"""Unit tests for the local offline QA runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "offline_qa.py"


def _run(payload: dict, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    payload_file = tmp_path / "handoff.json"
    result_file = tmp_path / "result.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--payload-file",
            str(payload_file),
            "--result-file",
            str(result_file),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    stdout_result = json.loads(proc.stdout.strip())
    file_result = json.loads(result_file.read_text(encoding="utf-8"))
    assert stdout_result == file_result
    return proc, stdout_result


def _valid_payload() -> dict:
    return {
        "feature_id": "015",
        "task_id": "T047",
        "acceptance_criteria": [
            "Runner emits explicit PASS/FIX_REQUIRED verdict.",
            "Runner validates handoff payload structure.",
        ],
        "changed_files": [
            "scripts/offline_qa.py",
            "tests/unit/test_offline_qa.py",
        ],
        "diff": "diff --git a/scripts/offline_qa.py b/scripts/offline_qa.py",
        "test_runs": [
            {"command": "uv run pytest tests/unit/test_offline_qa.py", "exit_code": 0},
        ],
        "known_risks": [],
    }


def test_offline_qa_returns_pass_for_valid_payload(tmp_path: Path) -> None:
    """Test the expected behavior."""
    proc, result = _run(_valid_payload(), tmp_path)
    assert proc.returncode == 0
    assert result["verdict"] == "PASS"
    assert result["feature_id"] == "015"
    assert result["task_id"] == "T047"
    assert result["findings"] == []


def test_offline_qa_returns_fix_required_when_test_failed(tmp_path: Path) -> None:
    """Test the expected behavior."""
    payload = _valid_payload()
    payload["test_runs"] = [
        {"command": "uv run pytest tests/unit/test_offline_qa.py", "exit_code": 1},
    ]
    proc, result = _run(payload, tmp_path)
    assert proc.returncode == 1
    assert result["verdict"] == "FIX_REQUIRED"
    assert any("test_runs[1] failed" in finding for finding in result["findings"])


def test_offline_qa_returns_fix_required_for_missing_required_fields(tmp_path: Path) -> None:
    """Test the expected behavior."""
    payload = _valid_payload()
    payload["acceptance_criteria"] = []
    payload["changed_files"] = []
    payload["diff"] = ""
    proc, result = _run(payload, tmp_path)
    assert proc.returncode == 1
    assert result["verdict"] == "FIX_REQUIRED"
    assert any("acceptance_criteria" in finding for finding in result["findings"])
    assert any("changed_files" in finding for finding in result["findings"])
    assert any("diff" in finding for finding in result["findings"])


def test_offline_qa_returns_fix_required_for_invalid_json(tmp_path: Path) -> None:
    """Test the expected behavior."""
    payload_file = tmp_path / "handoff.json"
    payload_file.write_text("{ this is invalid json", encoding="utf-8")
    result_file = tmp_path / "result.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--payload-file",
            str(payload_file),
            "--result-file",
            str(result_file),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    result = json.loads(proc.stdout.strip())

    assert proc.returncode == 1
    assert result["verdict"] == "FIX_REQUIRED"
    assert any("invalid JSON" in finding for finding in result["findings"])
