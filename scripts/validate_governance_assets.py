#!/usr/bin/env python3
"""Validate machine-readable governance assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    """Validate governance YAML assets and return process exit status."""
    repo_root = Path(".").resolve()
    failures: list[str] = []

    pipeline_path = repo_root / "docs/governance/pipeline-matrix.yaml"
    codes_path = repo_root / "docs/governance/gate-reason-codes.yaml"
    graph_path = repo_root / "docs/governance/doc-graph.yaml"
    manifest_primary = repo_root / ".specify/command-manifest.yaml"
    manifest_mirror = repo_root / "command-manifest.yaml"

    for path in (pipeline_path, codes_path, graph_path, manifest_primary, manifest_mirror):
        _expect(path.exists(), f"missing_file:{path.relative_to(repo_root)}", failures)
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    pipeline = _load_yaml(pipeline_path)
    _expect(isinstance(pipeline, dict), "invalid_pipeline_root", failures)
    steps = pipeline.get("steps", []) if isinstance(pipeline, dict) else []
    _expect(isinstance(steps, list) and len(steps) > 0, "invalid_pipeline_steps", failures)
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            failures.append(f"invalid_pipeline_step:{index}")
            continue
        for key in ("id", "command", "prerequisite", "output_artifact", "audit_event"):
            if key not in step:
                failures.append(f"missing_pipeline_field:{index}:{key}")

    reason_codes = _load_yaml(codes_path)
    _expect(isinstance(reason_codes, dict), "invalid_reason_codes_root", failures)
    codes = reason_codes.get("codes", []) if isinstance(reason_codes, dict) else []
    _expect(isinstance(codes, list) and len(codes) > 0, "invalid_reason_codes_list", failures)
    seen_codes: set[str] = set()
    for index, item in enumerate(codes):
        if not isinstance(item, dict):
            failures.append(f"invalid_reason_code_item:{index}")
            continue
        code = str(item.get("code", "")).strip()
        if not code:
            failures.append(f"missing_reason_code:{index}")
            continue
        if code in seen_codes:
            failures.append(f"duplicate_reason_code:{code}")
        seen_codes.add(code)
        for key in ("gate", "remediation"):
            if not str(item.get(key, "")).strip():
                failures.append(f"missing_reason_field:{code}:{key}")

    graph = _load_yaml(graph_path)
    _expect(isinstance(graph, dict), "invalid_doc_graph_root", failures)
    docs = graph.get("documents", []) if isinstance(graph, dict) else []
    _expect(isinstance(docs, list) and len(docs) > 0, "invalid_doc_graph_documents", failures)
    for index, doc in enumerate(docs):
        if not isinstance(doc, dict):
            failures.append(f"invalid_doc_graph_document:{index}")
            continue
        rel_path = str(doc.get("path", "")).strip()
        if not rel_path:
            failures.append(f"missing_doc_graph_path:{index}")
            continue
        target = repo_root / rel_path
        if not target.exists():
            failures.append(f"doc_graph_target_missing:{rel_path}")

    manifest_data = _load_yaml(manifest_primary)
    _expect(isinstance(manifest_data, dict), "invalid_command_manifest_root", failures)
    mirror_data = _load_yaml(manifest_mirror)
    if manifest_data != mirror_data:
        failures.append("command_manifest_mirror_mismatch")

    manifest_meta = manifest_data.get("manifest", {}) if isinstance(manifest_data, dict) else {}
    _expect(isinstance(manifest_meta, dict), "invalid_command_manifest_meta", failures)
    _expect(
        bool(str(manifest_meta.get("version", "")).strip()),
        "missing_command_manifest_version",
        failures,
    )
    _expect(
        bool(str(manifest_meta.get("updated_utc", "")).strip()),
        "missing_command_manifest_updated_utc",
        failures,
    )
    ledger_sync_policy = (
        manifest_meta.get("ledger_sync_policy", [])
        if isinstance(manifest_meta, dict)
        else []
    )
    _expect(
        isinstance(ledger_sync_policy, list) and len(ledger_sync_policy) > 0,
        "missing_command_manifest_ledger_sync_policy",
        failures,
    )

    commands = manifest_data.get("commands", []) if isinstance(manifest_data, dict) else []
    _expect(isinstance(commands, dict) and len(commands) > 0, "invalid_manifest_commands", failures)
    for command_name, command_def in (commands.items() if isinstance(commands, dict) else []):
        if not isinstance(command_def, dict):
            failures.append(f"invalid_manifest_command_def:{command_name}")
            continue
        scripts = command_def.get("scripts")
        if not isinstance(scripts, list) or len(scripts) == 0:
            failures.append(f"missing_manifest_command_scripts:{command_name}")
            continue
        for script_path in scripts:
            if not isinstance(script_path, str) or not script_path.strip():
                failures.append(f"invalid_manifest_script_entry:{command_name}")
                continue
            if "${" in script_path:
                continue
            candidate = repo_root / script_path
            if not candidate.exists():
                failures.append(f"manifest_script_target_missing:{command_name}:{script_path}")

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("PASS: governance assets are structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
