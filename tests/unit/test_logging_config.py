"""Unit tests for per-run logging path resolution and metadata pointers."""

from __future__ import annotations

import json
from pathlib import Path

from csp_trader.config import StorageConfig
from csp_trader.logging_config import (
    prepare_run_logging,
    resolve_latest_run_pointer_path,
    resolve_run_log_path,
)


def test_resolve_run_log_path_defaults() -> None:
    """Test the expected behavior."""
    storage = StorageConfig()
    run_id = "20260318T010101Z-abcdef12"
    assert resolve_run_log_path(storage, run_id) == f"logs/{run_id}/trading.jsonl"


def test_resolve_run_log_path_uses_template() -> None:
    """Test the expected behavior."""
    storage = StorageConfig(log_path_template="logs/custom/{run_id}/events.jsonl")
    run_id = "run-123"
    assert resolve_run_log_path(storage, run_id) == "logs/custom/run-123/events.jsonl"


def test_resolve_run_log_path_supports_legacy_template_field() -> None:
    """Test the expected behavior."""
    storage = StorageConfig(log_path="legacy/{run_id}/trading.jsonl")
    run_id = "run-legacy"
    assert resolve_run_log_path(storage, run_id) == "legacy/run-legacy/trading.jsonl"


def test_resolve_run_log_path_ignores_legacy_static_log_path() -> None:
    """Test the expected behavior."""
    storage = StorageConfig(log_path="trading.log", log_root_dir="logs/paper")
    run_id = "run-static"
    assert resolve_run_log_path(storage, run_id) == "logs/paper/run-static/trading.jsonl"


def test_prepare_run_logging_writes_pointer_metadata(tmp_path: Path) -> None:
    """Test the expected behavior."""
    storage = StorageConfig(log_root_dir=str(tmp_path / "logs"), run_log_file_name="trading.jsonl")
    run_id, log_path, pointer_path = prepare_run_logging(
        storage,
        mode="trading",
        config_path="config/paper.yaml",
        run_id="run-fixed",
    )

    assert run_id == "run-fixed"
    assert log_path == str(tmp_path / "logs" / "run-fixed" / "trading.jsonl")
    assert pointer_path == str(tmp_path / "logs" / "latest-run.json")
    assert Path(log_path).parent.exists()

    payload = json.loads(Path(pointer_path).read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-fixed"
    assert payload["log_path"] == log_path
    assert payload["mode"] == "trading"
    assert payload["config_path"] == "config/paper.yaml"


def test_resolve_latest_run_pointer_path_defaults() -> None:
    """Test the expected behavior."""
    storage = StorageConfig(log_root_dir="logs/e2e", latest_run_pointer_file="latest-run.json")
    assert resolve_latest_run_pointer_path(storage) == "logs/e2e/latest-run.json"
