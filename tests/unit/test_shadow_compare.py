"""Unit tests for temporary shadow compare rollout helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(module_name: str, relative_path: str):
    script_path = Path(__file__).resolve().parents[2] / "src" / relative_path
    script_dir = script_path.parent
    script_dir_str = str(script_dir)
    if script_dir_str not in sys.path:
        sys.path.insert(0, script_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shadow_compare = _load_module("shadow_compare", "mcp_codebase/orchestration/shadow_compare.py")


def test_compare_outputs_reports_matches() -> None:
    report = shadow_compare.compare_outputs(
        {
            "stdout": "hello\n",
            "stderr": "",
            "exit_code": 0,
        },
        {
            "stdout": "hello\n",
            "stderr": "",
            "exit_code": 0,
        },
    )

    assert report["ok"] is True
    assert report["differences"] == []
    assert report["stdout_match"] is True
    assert report["stderr_match"] is True
    assert report["exit_code_match"] is True


def test_compare_outputs_emits_normalized_diffs() -> None:
    report = shadow_compare.compare_outputs(
        {
            "stdout": "/tmp/shell/repo/output\n",
            "stderr": "shell warning\n",
            "exit_code": 1,
        },
        {
            "stdout": "/tmp/python/repo/output\n",
            "stderr": "python warning\n",
            "exit_code": 0,
        },
        normalize_replacements=[
            ("/tmp/shell/repo", "<REPO_ROOT>"),
            ("/tmp/python/repo", "<REPO_ROOT>"),
        ],
    )

    assert report["ok"] is False
    assert report["stdout_match"] is True
    assert report["stderr_match"] is False
    assert report["exit_code_match"] is False
    assert any(item["channel"] == "stderr" for item in report["differences"])
    assert any(item["channel"] == "exit_code" for item in report["differences"])


def test_compare_outputs_includes_unified_diff_when_text_changes() -> None:
    report = shadow_compare.compare_outputs(
        {"stdout": "alpha\n", "stderr": "", "exit_code": 0},
        {"stdout": "beta\n", "stderr": "", "exit_code": 0},
    )

    assert report["ok"] is False
    assert report["stdout_match"] is False
    assert report["differences"][0]["channel"] == "stdout"
    assert "--- legacy:stdout" in report["differences"][0]["diff"]
    assert "+++ python:stdout" in report["differences"][0]["diff"]
