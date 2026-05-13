"""Unit tests for scripts/speckit_offline_qa_handoff.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    """Load scripts/speckit_offline_qa_handoff.py directly from the repo."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "speckit_offline_qa_handoff.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("speckit_offline_qa_handoff", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_handoff_rejects_result_task_scope_mismatch(tmp_path: Path, monkeypatch) -> None:
    """Offline QA handoff should reject a result file for the wrong task/run scope."""
    handoff = _load_module()
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(
        json.dumps(
            {
                "feature_id": "029",
                "task_id": "T005",
                "hud_path": "specs/029-make-tetris/huds/T005.md",
                "diff": "diff",
                "acceptance_criteria": ["criterion"],
                "quality_guards": ["guard"],
                "changed_files": ["src/example.py"],
                "test_runs": [{"command": "pytest", "exit_code": 0, "output": "ok"}],
                "payload_run_id": "payload-run-1",
                "payload_digest": "digest-1",
            }
        ),
        encoding="utf-8",
    )
    result_file = tmp_path / "result.json"
    result_file.write_text(
        json.dumps(
            {
                "feature_id": "029",
                "task_id": "T004",
                "payload_run_id": "payload-run-1",
                "payload_digest": "digest-1",
                "qa_run_id": "offline-qa-t004-test",
                "verdict": "PASS",
                "changed_files_considered": ["src/example.py"],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        handoff,
        "_run",
        lambda cmd, cwd: (0, "{}", "") if "validate-offline-qa-payload" in cmd else (0, "", ""),
    )
    monkeypatch.setattr(handoff, "_load_json_file", lambda path: json.loads(path.read_text(encoding="utf-8")))

    payload = handoff.run_offline_qa_handoff(
        feature_id="029",
        task_id="T005",
        payload_file=payload_file,
        result_file=result_file,
        no_autobuild_payload=True,
    )

    assert payload["ok"] is False
    assert "result_task_id_mismatch" in payload["reasons"]
