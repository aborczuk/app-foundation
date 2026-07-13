"""Unit tests for offline QA payload validation in speckit_implement_gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _load_module():
    """Load scripts/speckit_implement_gate.py directly from the repo."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "speckit_implement_gate.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("speckit_implement_gate_payload", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_validate_offline_payload_rejects_invalid_digest(tmp_path: Path) -> None:
    """Payload validation should reject stale or forged payload digests."""
    gate = _load_module()
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(
        json.dumps(
            {
                "feature_id": "029",
                "task_id": "T005",
                "diff": "diff",
                "acceptance_criteria": ["criterion"],
                "quality_guards": ["guard"],
                "changed_files": ["src/example.py"],
                "test_runs": [{"command": "pytest", "exit_code": 0, "output": "ok"}],
                "payload_run_id": "payload-run-1",
                "payload_digest": "bad-digest",
            }
        ),
        encoding="utf-8",
    )

    exit_code, payload = gate._offline_qa_payload(argparse.Namespace(payload_file=str(payload_file), json=True))

    assert exit_code == 2
    assert "invalid_payload_digest" in payload["reasons"]
