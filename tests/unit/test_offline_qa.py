"""Unit tests for scripts/offline_qa.py result building."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module():
    """Load scripts/offline_qa.py directly from the repo."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "offline_qa.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("offline_qa", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_result_carries_payload_identity_and_changed_files(monkeypatch) -> None:
    """Offline QA results should carry the active payload identity and changed files."""
    offline_qa = _load_module()
    monkeypatch.setattr(offline_qa, "utc_now_iso", lambda: "2026-05-11T00:00:00Z")
    monkeypatch.setattr(offline_qa, "build_qa_run_id", lambda task_id: f"offline-qa-{task_id.lower()}-test")

    result = offline_qa.build_result(
        {
            "feature_id": "029",
            "task_id": "T005",
            "payload_run_id": "payload-run-1",
            "payload_digest": "digest-1",
            "acceptance_criteria": ["criterion"],
            "changed_files": ["src/example.py"],
            "diff": "diff",
            "test_runs": [{"command": "pytest", "exit_code": 0, "output": "ok"}],
        },
        {"verdict": "PASS", "warnings": []},
    )

    assert result["qa_run_id"] == "offline-qa-t005-test"
    assert result["payload_run_id"] == "payload-run-1"
    assert result["payload_digest"] == "digest-1"
    assert result["changed_files_considered"] == ["src/example.py"]
