"""Unit tests for scripts/codex_handoff_runner.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


codex_handoff_runner = _load_script_module("codex_handoff_runner", "codex_handoff_runner.py")


def test_run_handoff_writes_artifact_from_codex_summary(tmp_path: Path, monkeypatch) -> None:
    """Verify the wrapper writes the artifact from a Codex JSON summary response."""
    source_home = tmp_path / "source-codex-home"
    source_home.mkdir()
    source_home.joinpath("auth.json").write_text("{}", encoding="utf-8")
    source_home.joinpath("config.toml").write_text("[default]\n", encoding="utf-8")
    monkeypatch.setattr(codex_handoff_runner, "_source_codex_home", lambda: source_home)

    def _fake_run_codex_exec(*, prompt, repo_root, codex_home, output_schema_path, output_last_message_path):
        """Simulate a successful Codex CLI call."""
        del prompt, repo_root, codex_home, output_schema_path
        output_last_message_path.write_text(
            json.dumps({"summary": "Codex generated the live handoff summary"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=["codex", "exec"], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(codex_handoff_runner, "_run_codex_exec", _fake_run_codex_exec)

    artifact_path = tmp_path / "artifact.md"
    result = codex_handoff_runner.run_handoff(
        {
            "feature_id": "019",
            "phase": "plan",
            "correlation_id": "run_20260410T120000Z_019:speckit.plan",
            "handoff": {
                "handoff_id": "handoff-001",
                "step_name": "speckit.plan",
                "required_inputs": [],
                "output_template_path": str(artifact_path),
                "completion_marker": "## Summary",
            },
        }
    )

    assert result["artifact_path"] == str(artifact_path)
    assert result["completion_marker"] == "## Summary"
    assert result["summary"] == "Codex generated the live handoff summary"
    assert artifact_path.exists()
    artifact_text = artifact_path.read_text(encoding="utf-8")
    assert "## Summary" in artifact_text
    assert "Codex generated the live handoff summary" in artifact_text

