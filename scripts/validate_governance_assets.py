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

    for path in (pipeline_path, codes_path, graph_path):
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

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        return 1

    print("PASS: governance assets are structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
