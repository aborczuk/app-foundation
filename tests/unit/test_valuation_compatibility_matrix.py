"""Unit tests for valuation compatibility matrix validation script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():  # type: ignore[no-untyped-def]
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_valuation_compatibility_matrix.py"
    )
    spec = importlib.util.spec_from_file_location("check_valuation_compatibility_matrix", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compatibility_matrix_validator_passes_current_repo_state() -> None:
    """Test the expected behavior."""
    module = _load_module()
    root = Path(__file__).resolve().parents[2]
    errors = module.validate(root)
    assert errors == []
