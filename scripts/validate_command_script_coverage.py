#!/usr/bin/env python3
"""Validate deterministic command-to-script coverage from manifest contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

REQUIRED_BASH_SCAFFOLDS: dict[str, str] = {
    "speckit.specify": "create-new-feature.sh",
    "speckit.plan": "setup-plan.sh",
}


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a mapping")
    return payload


def _artifact_has_template(artifact: Mapping[str, Any]) -> bool:
    template = artifact.get("template")
    return isinstance(template, str) and bool(template.strip())


def build_coverage_report(
    manifest: Mapping[str, Any],
    *,
    scaffold_script_path: Path,
    bash_scripts_dir: Path,
) -> dict[str, Any]:
    """Build coverage report from manifest: identify covered and uncovered commands."""
    commands = manifest.get("commands", {})
    if not isinstance(commands, Mapping):
        raise ValueError("manifest.commands must be a mapping")

    report: dict[str, Any] = {
        "covered_commands": [],
        "uncovered_commands": [],
        "reasons": [],
    }

    if not scaffold_script_path.exists():
        report["reasons"].append(f"missing_pipeline_scaffold:{scaffold_script_path}")

    for command_id, command_def in commands.items():
        command_reasons: list[str] = []
        if not isinstance(command_id, str) or not command_id:
            report["reasons"].append("invalid_command_id")
            continue
        if not isinstance(command_def, Mapping):
            command_reasons.append("invalid_command_definition")
            report["uncovered_commands"].append({"command": command_id, "reasons": command_reasons})
            continue

        artifacts = command_def.get("artifacts", [])
        if not isinstance(artifacts, list):
            command_reasons.append("invalid_artifacts_list")
            report["uncovered_commands"].append({"command": command_id, "reasons": command_reasons})
            continue

        has_template_artifact = False
        declared_scaffold_names: set[str] = set()

        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                command_reasons.append("invalid_artifact_entry")
                continue

            if _artifact_has_template(artifact):
                has_template_artifact = True

            scaffold_name = artifact.get("scaffold_script")
            if scaffold_name is None:
                continue
            if not isinstance(scaffold_name, str) or not scaffold_name.strip():
                command_reasons.append("invalid_scaffold_script_name")
                continue

            normalized_name = scaffold_name.strip()
            declared_scaffold_names.add(normalized_name)
            expected_path = bash_scripts_dir / normalized_name
            if not expected_path.exists():
                command_reasons.append(f"missing_scaffold_script:{normalized_name}")

        required_scaffold = REQUIRED_BASH_SCAFFOLDS.get(command_id)
        if required_scaffold is not None and required_scaffold not in declared_scaffold_names:
            command_reasons.append(f"missing_required_scaffold_reference:{required_scaffold}")

        if has_template_artifact and not scaffold_script_path.exists():
            command_reasons.append("missing_pipeline_scaffold")

        if command_reasons:
            report["uncovered_commands"].append(
                {"command": command_id, "reasons": sorted(set(command_reasons))}
            )
        else:
            report["covered_commands"].append(command_id)

    report["covered_commands"] = sorted(report["covered_commands"])
    report["uncovered_commands"] = sorted(
        report["uncovered_commands"], key=lambda item: str(item.get("command", ""))
    )
    report["reasons"] = sorted(set(report["reasons"]))
    return report


def validate_command_script_coverage(
    *,
    canonical_manifest_path: Path,
    mirror_manifest_path: Path | None = None,
    scaffold_script_path: Path,
    bash_scripts_dir: Path,
) -> dict[str, Any]:
    """Validate command coverage from the canonical command manifest."""
    manifest = _load_manifest(canonical_manifest_path)
    report = build_coverage_report(
        manifest,
        scaffold_script_path=scaffold_script_path,
        bash_scripts_dir=bash_scripts_dir,
    )

    reasons = list(report["reasons"])

    payload = {
        "canonical_manifest": str(canonical_manifest_path),
        "mirror_manifest": str(mirror_manifest_path) if mirror_manifest_path else None,
        "scaffold_script": str(scaffold_script_path),
        "bash_scripts_dir": str(bash_scripts_dir),
        "covered_commands": report["covered_commands"],
        "uncovered_commands": report["uncovered_commands"],
        "reasons": sorted(set(reasons)),
    }
    payload["ok"] = len(payload["reasons"]) == 0 and len(payload["uncovered_commands"]) == 0
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical-manifest",
        default="command-manifest.yaml",
        help="Path to canonical manifest.",
    )
    parser.add_argument(
        "--mirror-manifest",
        default="",
        help="Optional legacy mirror manifest path (not used for validation).",
    )
    parser.add_argument(
        "--scaffold-script",
        default=".specify/scripts/pipeline-scaffold.py",
        help="Path to shared pipeline scaffold script.",
    )
    parser.add_argument(
        "--bash-scripts-dir",
        default=".specify/scripts/bash",
        help="Directory containing referenced bash scaffold scripts.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate deterministic command-to-script coverage from manifest contracts."""
    args = _build_parser().parse_args(argv)
    payload = validate_command_script_coverage(
        canonical_manifest_path=Path(args.canonical_manifest).resolve(),
        mirror_manifest_path=(
            Path(args.mirror_manifest).resolve() if args.mirror_manifest else None
        ),
        scaffold_script_path=Path(args.scaffold_script).resolve(),
        bash_scripts_dir=Path(args.bash_scripts_dir).resolve(),
    )

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "PASS" if payload["ok"] else "FAIL"
        print(f"status={status}")
        if payload["reasons"]:
            print("reasons=" + ",".join(payload["reasons"]))
        if payload["uncovered_commands"]:
            print("uncovered=" + ",".join(item["command"] for item in payload["uncovered_commands"]))

    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
