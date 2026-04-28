from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    module_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_module("hook_enforce_code_reads", "hook_enforce_code_reads.py")


def test_extract_read_code_policy_uses_window_line_count() -> None:
    """Parse the window helper's line count instead of its start line."""
    mode, target_path, requested_lines, allow_fallback = hook._extract_read_code_policy(
        "uv run --no-sync python scripts/read_code.py window scripts/read_code.py 161 40"
    )

    assert mode == "window"
    assert target_path == "scripts/read_code.py"
    assert requested_lines == 40
    assert allow_fallback is False


def test_main_allows_window_reads_starting_past_the_helper_threshold(capsys, monkeypatch) -> None:
    """Keep the deny guard tied to window size, not the requested start line."""
    payload = {"tool_input": {"command": "uv run --no-sync python scripts/read_code.py window scripts/read_code.py 161 40"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    exit_code = hook.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
