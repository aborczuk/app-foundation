"""Unit tests for shared implement orchestration contract helpers."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_module():
    """Load the shared contract helper module from scripts."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / "speckit_implement_contract.py"
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location("speckit_implement_contract", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compute_payload_digest_ignores_digest_field() -> None:
    """Digest calculation should ignore the digest field itself."""
    contract = _load_module()
    payload = {"feature_id": "029", "task_id": "T005", "payload_run_id": "run-1"}

    first = contract.compute_payload_digest(payload)
    payload["payload_digest"] = "placeholder"
    second = contract.compute_payload_digest(payload)

    assert first == second


def test_existing_payload_reasons_accepts_matching_payload() -> None:
    """A matching payload with a valid digest should be reusable."""
    contract = _load_module()
    payload = {
        "feature_id": "029",
        "task_id": "T005",
        "attempt": 1,
        "payload_run_id": contract.build_payload_run_id(
            "T005", 1, now=datetime(2026, 5, 11, tzinfo=timezone.utc)
        ),
    }
    payload["payload_digest"] = contract.compute_payload_digest(payload)

    reasons = contract.existing_payload_reasons(
        payload,
        feature_id="029",
        task_id="T005",
        attempt=1,
    )

    assert reasons == []


def test_offline_result_reasons_rejects_scope_mismatch() -> None:
    """Result validation should reject stale task-scope and changed-file mismatches."""
    contract = _load_module()
    reasons = contract.offline_result_reasons(
        {
            "feature_id": "029",
            "task_id": "T004",
            "payload_run_id": "stale-run",
            "payload_digest": "stale-digest",
            "qa_run_id": "",
            "verdict": "PASS",
            "changed_files_considered": [],
        },
        feature_id="029",
        task_id="T005",
        payload_run_id="active-run",
        payload_digest="active-digest",
    )

    assert "result_task_id_mismatch" in reasons
    assert "result_payload_run_id_mismatch" in reasons
    assert "result_payload_digest_mismatch" in reasons
    assert "missing_qa_run_id" in reasons
    assert "invalid_changed_files_considered" in reasons
