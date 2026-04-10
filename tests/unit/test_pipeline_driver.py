"""Unit-level skeleton tests for scripts/pipeline_driver.py."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest


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


pipeline_driver = _load_script_module("pipeline_driver", "pipeline_driver.py")
pipeline_driver_contracts = _load_script_module(
    "pipeline_driver_contracts", "pipeline_driver_contracts.py"
)
pipeline_driver_state = _load_script_module("pipeline_driver_state", "pipeline_driver_state.py")


def test_main_outputs_minimal_step_result(capsys) -> None:
    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "setup"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["feature_id"] == "019"
    assert payload["step_result"]["exit_code"] == 0


def test_normalize_driver_mode_aliases() -> None:
    assert pipeline_driver_contracts.normalize_driver_mode(None) == "legacy"
    assert pipeline_driver_contracts.normalize_driver_mode("script") == "deterministic"
    assert pipeline_driver_contracts.normalize_driver_mode("llm") == "generative"
    assert pipeline_driver_contracts.normalize_driver_mode("LEGACY") == "legacy"


def test_normalize_driver_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        pipeline_driver_contracts.normalize_driver_mode("unsupported-mode")


def test_load_driver_routes_normalizes_mode_and_script_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".specify" / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    driver:",
                "      mode: script",
                "      script_path: scripts/example.sh",
                "      timeout_seconds: 30",
                "    emits:",
                "      - event: example_event",
                "        required_fields: []",
                "  speckit.fallback:",
                "    description: \"fallback\"",
                "    emits: []",
            ]
        ),
        encoding="utf-8",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    assert routes["speckit.example"]["mode"] == "deterministic"
    assert routes["speckit.example"]["driver_managed"] is True
    assert routes["speckit.example"]["timeout_seconds"] == 30
    assert routes["speckit.example"]["emits"] == ["example_event"]
    assert routes["speckit.example"]["script_path"] == str(
        (tmp_path / "scripts" / "example.sh").resolve()
    )

    assert routes["speckit.fallback"]["mode"] == "legacy"
    assert routes["speckit.fallback"]["driver_managed"] is False


def test_acquire_feature_lock_blocks_active_other_owner(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    first = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=60,
        now_utc=now,
    )
    assert first["acquired"] is True

    second = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        lease_seconds=60,
        now_utc=now + timedelta(seconds=10),
    )
    assert second["acquired"] is False
    assert second["reason"] == "feature_lock_held"
    assert second["existing_owner"] == "worker-a"


def test_acquire_feature_lock_replaces_stale_owner(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now,
    )

    takeover = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now + timedelta(seconds=60),
    )
    assert takeover["acquired"] is True
    assert takeover["stale_replaced"] is True
    assert takeover["reason"] == "stale_lock_replaced"
    assert takeover["previous_owner"] == "worker-a"


def test_release_feature_lock_requires_owner_unless_stale(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=120,
        now_utc=now,
    )

    blocked_release = pipeline_driver_state.release_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        now_utc=now + timedelta(seconds=10),
    )
    assert blocked_release["released"] is False
    assert blocked_release["reason"] == "lock_owned_by_other"

    owner_release = pipeline_driver_state.release_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        now_utc=now + timedelta(seconds=20),
    )
    assert owner_release["released"] is True
    assert owner_release["reason"] == "released_by_owner"
