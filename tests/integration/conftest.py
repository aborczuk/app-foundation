"""Shared integration harness for deterministic pipeline-driver flow tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

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


pipeline_driver_state = _load_script_module("pipeline_driver_state", "pipeline_driver_state.py")


@pytest.fixture
def driver_flow_harness(tmp_path: Path):
    """Provide common feature sandbox, ledger seeding, and state helpers."""

    feature_dir = tmp_path / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    locks_dir = tmp_path / "locks"

    def make_event(event_name: str, timestamp_utc: str, **fields: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event": event_name,
            "feature_id": "019",
            "timestamp_utc": timestamp_utc,
        }
        payload.update(fields)
        return payload

    def seed_ledger(events: list[dict[str, Any]]) -> None:
        lines = [json.dumps(event, sort_keys=True) for event in events]
        ledger_path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    def resolve(feature_id: str = "019", phase_hint: str | None = None) -> dict[str, Any]:
        state: dict[str, Any] = {"feature_dir": str(feature_dir)}
        if phase_hint is not None:
            state["phase"] = phase_hint
        return pipeline_driver_state.resolve_phase_state(
            feature_id,
            pipeline_state=state,
            ledger_path=ledger_path,
            feature_dir=feature_dir,
        )

    def acquire(feature_id: str = "019", owner: str = "worker-a") -> dict[str, Any]:
        return pipeline_driver_state.acquire_feature_lock(
            feature_id,
            owner=owner,
            locks_dir=locks_dir,
        )

    def release(feature_id: str = "019", owner: str = "worker-a") -> dict[str, Any]:
        return pipeline_driver_state.release_feature_lock(
            feature_id,
            owner=owner,
            locks_dir=locks_dir,
        )

    return SimpleNamespace(
        feature_dir=feature_dir,
        ledger_path=ledger_path,
        locks_dir=locks_dir,
        make_event=make_event,
        seed_ledger=seed_ledger,
        resolve=resolve,
        acquire=acquire,
        release=release,
    )

