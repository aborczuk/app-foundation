"""Unit tests for deterministic command/script coverage validation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_script_module(module_name: str, script_name: str):
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


coverage_validator = _load_script_module(
    "validate_command_script_coverage", "validate_command_script_coverage.py"
)


def _write_manifest(path: Path, *, include_plan_scaffold: bool = True) -> None:
    scaffold_line = "        scaffold_script: setup-plan.sh" if include_plan_scaffold else ""
    path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.specify:",
                "    description: \"spec\"",
                "    artifacts:",
                "      - output_path: \"${FEATURE_DIR}/spec.md\"",
                "        template: \"spec-template.md\"",
                "        scaffold_script: create-new-feature.sh",
                "    emits: []",
                "  speckit.plan:",
                "    description: \"plan\"",
                "    artifacts:",
                "      - output_path: \"${FEATURE_DIR}/plan.md\"",
                "        template: \"plan-template.md\"",
                scaffold_line,
                "    emits: []",
            ]
        ),
        encoding="utf-8",
    )


def test_validate_command_script_coverage_passes_with_required_scripts(tmp_path: Path) -> None:
    canonical_manifest = tmp_path / ".specify" / "command-manifest.yaml"
    mirror_manifest = tmp_path / "command-manifest.yaml"
    scaffold_script = tmp_path / ".specify" / "scripts" / "pipeline-scaffold.py"
    bash_scripts_dir = tmp_path / ".specify" / "scripts" / "bash"

    canonical_manifest.parent.mkdir(parents=True, exist_ok=True)
    scaffold_script.parent.mkdir(parents=True, exist_ok=True)
    bash_scripts_dir.mkdir(parents=True, exist_ok=True)

    _write_manifest(canonical_manifest)
    mirror_manifest.write_text(canonical_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    scaffold_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (bash_scripts_dir / "create-new-feature.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (bash_scripts_dir / "setup-plan.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    payload = coverage_validator.validate_command_script_coverage(
        canonical_manifest_path=canonical_manifest,
        mirror_manifest_path=mirror_manifest,
        scaffold_script_path=scaffold_script,
        bash_scripts_dir=bash_scripts_dir,
    )
    assert payload["ok"] is True
    assert payload["uncovered_commands"] == []
    assert payload["reasons"] == []


def test_validate_command_script_coverage_reports_missing_required_reference(tmp_path: Path) -> None:
    canonical_manifest = tmp_path / ".specify" / "command-manifest.yaml"
    mirror_manifest = tmp_path / "command-manifest.yaml"
    scaffold_script = tmp_path / ".specify" / "scripts" / "pipeline-scaffold.py"
    bash_scripts_dir = tmp_path / ".specify" / "scripts" / "bash"

    canonical_manifest.parent.mkdir(parents=True, exist_ok=True)
    scaffold_script.parent.mkdir(parents=True, exist_ok=True)
    bash_scripts_dir.mkdir(parents=True, exist_ok=True)

    _write_manifest(canonical_manifest, include_plan_scaffold=False)
    mirror_manifest.write_text(canonical_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    scaffold_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    (bash_scripts_dir / "create-new-feature.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (bash_scripts_dir / "setup-plan.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    payload = coverage_validator.validate_command_script_coverage(
        canonical_manifest_path=canonical_manifest,
        mirror_manifest_path=mirror_manifest,
        scaffold_script_path=scaffold_script,
        bash_scripts_dir=bash_scripts_dir,
    )
    assert payload["ok"] is False
    uncovered = {item["command"]: item["reasons"] for item in payload["uncovered_commands"]}
    assert "speckit.plan" in uncovered
    assert "missing_required_scaffold_reference:setup-plan.sh" in uncovered["speckit.plan"]

