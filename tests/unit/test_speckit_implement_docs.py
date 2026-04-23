"""Unit tests for deterministic implement-doc updater."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


docs = _load_script_module("speckit_implement_docs", "speckit_implement_docs.py")


def test_apply_update_bootstraps_and_updates_both_sections(tmp_path: Path) -> None:
    """Missing quickstart should be bootstrapped and receive both section updates."""
    feature_dir = tmp_path / "feature"
    request = docs.UpdateRequest(
        feature_dir=feature_dir,
        entry_id="T100",
        runbook_notes=("runbook note A",),
        decision_log_entries=("decision entry A",),
    )

    result = docs.apply_update(request)
    quickstart = feature_dir / "quickstart.md"

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["runbook_updated"] is True
    assert result["decision_log_updated"] is True
    assert quickstart.exists()
    text = quickstart.read_text(encoding="utf-8")
    assert docs.RUNBOOK_HEADING in text
    assert docs.RUNBOOK_SUBHEADING in text
    assert docs.DECISION_LOG_HEADING in text
    assert "- runbook note A" in text
    assert "- decision entry A" in text


def test_apply_update_is_idempotent_for_same_entry_id(tmp_path: Path) -> None:
    """Repeated request with same entry id should return no-op reasons."""
    feature_dir = tmp_path / "feature"
    request = docs.UpdateRequest(
        feature_dir=feature_dir,
        entry_id="T101",
        runbook_notes=("runbook note B",),
        decision_log_entries=("decision entry B",),
    )
    first = docs.apply_update(request)
    second = docs.apply_update(request)

    assert first["changed"] is True
    assert second["changed"] is False
    assert "entry_already_recorded" in second["reasons"]


def test_main_rejects_missing_updates(tmp_path: Path, capsys) -> None:
    """CLI should fail when no runbook or decision-log entries are provided."""
    exit_code = docs.main(
        [
            "--feature-dir",
            str(tmp_path),
            "--entry-id",
            "T102",
            "--json",
        ]
    )
    payload = capsys.readouterr().out

    assert exit_code == 2
    assert "no_updates_requested" in payload
