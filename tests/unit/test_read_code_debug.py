from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def _load_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "read_code_debug.py"
    spec = importlib.util.spec_from_file_location("read_code_debug_tests", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_main_enables_break_glass_and_delegates(monkeypatch) -> None:
    debug = _load_module()
    seen_args: list[list[str]] = []

    monkeypatch.delenv(debug.READ_CODE_ALLOW_SYMBOL_DUMP_ENV, raising=False)
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.setattr(debug, "read_code_symbols", lambda args: (seen_args.append(list(args)), 0)[1])

    exit_code = debug.main(["scripts/read_code.py", "--allow-repeat"])

    assert exit_code == 0
    assert seen_args == [["scripts/read_code.py", "--allow-repeat"]]
    assert os.environ[debug.READ_CODE_ALLOW_SYMBOL_DUMP_ENV] == "1"
    assert os.environ["UV_CACHE_DIR"].endswith(".codegraphcontext/.uv-cache")
