#!/usr/bin/env python3
"""State helpers for the deterministic pipeline driver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

EVENT_TO_PHASE: dict[str, str] = {
    "backlog_registered": "specify",
    "spec_clarified": "specify",
    "research_completed": "research",
    "plan_started": "plan",
    "planreview_completed": "plan",
    "feasibility_spike_completed": "plan",
    "feasibility_spike_failed": "plan",
    "plan_approved": "plan",
    "sketch_completed": "solution",
    "solutionreview_completed": "solution",
    "estimation_completed": "solution",
    "tasking_completed": "solution",
    "solution_approved": "solution",
    "analysis_completed": "analyze",
    "e2e_generated": "implement",
    "feature_closed": "closed",
}

PHASE_TRANSITIONS: dict[str, str] = {
    "specify": "research",
    "research": "plan",
    "plan": "solution",
    "solution": "implement",
    "implement": "closed",
}


def advance_phase(current_phase: str) -> str:
    """Return the next pipeline phase after current_phase."""
    return PHASE_TRANSITIONS.get(current_phase, current_phase)

REQUIRED_ARTIFACTS_BY_EVENT: dict[str, tuple[str, ...]] = {
    "plan_approved": ("plan.md",),
    "solution_approved": ("tasks.md", "estimates.md"),
    "analysis_completed": ("analysis.md",),
    "e2e_generated": ("e2e.md",),
}

_PIPELINE_LEDGER_MODULE: Any | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _lock_file_path(feature_id: str, locks_dir: Path | str) -> Path:
    return Path(locks_dir).resolve() / f"{feature_id}.lock"


def _load_lock_record(lock_path: Path) -> dict[str, Any] | None:
    if not lock_path.exists():
        return None
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"invalid": True}
    if not isinstance(payload, dict):
        return {"invalid": True}
    return payload


def _is_stale_lock(record: Mapping[str, Any], now_utc: datetime) -> bool:
    if bool(record.get("invalid", False)):
        return True
    expires_at = _parse_utc_timestamp(record.get("expires_at_utc"))
    if expires_at is None:
        return True
    return expires_at <= now_utc


def _write_lock_record(lock_path: Path, record: Mapping[str, Any]) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")


def _load_pipeline_ledger_module() -> Any:
    global _PIPELINE_LEDGER_MODULE
    if _PIPELINE_LEDGER_MODULE is not None:
        return _PIPELINE_LEDGER_MODULE

    script_path = Path(__file__).resolve().parent / "pipeline_ledger.py"
    spec = importlib.util.spec_from_file_location("pipeline_ledger_for_driver_state", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load pipeline_ledger module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _PIPELINE_LEDGER_MODULE = module
    return module


def acquire_feature_lock(
    feature_id: str,
    *,
    owner: str,
    locks_dir: Path | str = ".speckit/locks",
    lease_seconds: int = 300,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Acquire a feature-scoped lock with stale-owner takeover semantics."""

    if not feature_id:
        raise ValueError("feature_id is required")
    if not owner:
        raise ValueError("owner is required")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be a positive integer")

    now = now_utc or _utc_now()
    lock_path = _lock_file_path(feature_id, locks_dir)
    acquired_at_utc = _format_utc_timestamp(now)
    expires_at_utc = _format_utc_timestamp(now + timedelta(seconds=lease_seconds))
    new_record = {
        "feature_id": feature_id,
        "owner": owner,
        "acquired_at_utc": acquired_at_utc,
        "expires_at_utc": expires_at_utc,
    }

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(new_record, sort_keys=True))
        return {
            "acquired": True,
            "reused": False,
            "stale_replaced": False,
            "reason": None,
            "lock_path": str(lock_path),
            "record": new_record,
        }

    existing = _load_lock_record(lock_path) or {}
    existing_owner = existing.get("owner") if isinstance(existing.get("owner"), str) else None
    stale = _is_stale_lock(existing, now)

    if existing_owner == owner and not stale:
        return {
            "acquired": True,
            "reused": True,
            "stale_replaced": False,
            "reason": None,
            "lock_path": str(lock_path),
            "record": existing,
        }

    if stale:
        _write_lock_record(lock_path, new_record)
        return {
            "acquired": True,
            "reused": False,
            "stale_replaced": True,
            "reason": "stale_lock_replaced",
            "lock_path": str(lock_path),
            "previous_owner": existing_owner,
            "record": new_record,
        }

    return {
        "acquired": False,
        "reused": False,
        "stale_replaced": False,
        "reason": "feature_lock_held",
        "lock_path": str(lock_path),
        "owner": owner,
        "existing_owner": existing_owner,
        "record": existing,
    }


def release_feature_lock(
    feature_id: str,
    *,
    owner: str,
    locks_dir: Path | str = ".speckit/locks",
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Release a feature lock if owner matches, or clean stale/corrupt locks."""

    if not feature_id:
        raise ValueError("feature_id is required")
    if not owner:
        raise ValueError("owner is required")

    now = now_utc or _utc_now()
    lock_path = _lock_file_path(feature_id, locks_dir)
    if not lock_path.exists():
        return {
            "released": True,
            "reason": "lock_absent",
            "lock_path": str(lock_path),
        }

    existing = _load_lock_record(lock_path) or {}
    existing_owner = existing.get("owner") if isinstance(existing.get("owner"), str) else None
    stale = _is_stale_lock(existing, now)

    if existing_owner == owner or stale:
        lock_path.unlink(missing_ok=True)
        return {
            "released": True,
            "reason": "released_by_owner" if existing_owner == owner else "stale_lock_released",
            "lock_path": str(lock_path),
            "previous_owner": existing_owner,
        }

    return {
        "released": False,
        "reason": "lock_owned_by_other",
        "lock_path": str(lock_path),
        "owner": owner,
        "existing_owner": existing_owner,
    }


def resolve_phase_state(
    feature_id: str,
    *,
    pipeline_state: Mapping[str, Any] | None = None,
    ledger_path: Path | str = ".speckit/pipeline-ledger.jsonl",
    feature_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Resolve feature phase from ledger state and detect drift conditions.

    If pipeline_state includes dry_run=True, no mutations occur (read-only mode).
    """

    if not feature_id:
        raise ValueError("feature_id is required")

    state = dict(pipeline_state or {})
    drift_reasons: list[str] = []
    last_event: str | None = None
    event_count = 0
    approved_plan = False
    approved_solution = False

    resolved_feature_dir: Path | None = None
    if feature_dir is not None:
        resolved_feature_dir = Path(feature_dir).resolve()
    elif isinstance(state.get("feature_dir"), str) and state["feature_dir"]:
        resolved_feature_dir = Path(str(state["feature_dir"])).resolve()

    try:
        pipeline_ledger = _load_pipeline_ledger_module()
        all_events = pipeline_ledger.read_events(Path(ledger_path))
        feature_events = [
            event for event in all_events if str(event.get("feature_id", "")).strip() == feature_id
        ]
        event_count = len(feature_events)

        if feature_events:
            sequence_errors, feature_states = pipeline_ledger.validate_sequence(feature_events)
            if sequence_errors:
                drift_reasons.append("ledger_sequence_invalid")
            feature_state = feature_states.get(feature_id)
            if feature_state is not None:
                approved_plan = bool(getattr(feature_state, "approved_plan", False))
                approved_solution = bool(getattr(feature_state, "approved_solution", False))

            raw_last_event = feature_events[-1].get("event")
            if isinstance(raw_last_event, str) and raw_last_event:
                last_event = raw_last_event
    except SystemExit:
        drift_reasons.append("ledger_read_failed")
    except Exception:
        drift_reasons.append("ledger_read_failed")

    derived_phase = EVENT_TO_PHASE.get(last_event or "", "unknown")
    hinted_phase = state.get("phase")
    if derived_phase == "unknown" and isinstance(hinted_phase, str) and hinted_phase:
        phase = hinted_phase
    else:
        phase = derived_phase
        if (
            isinstance(hinted_phase, str)
            and hinted_phase
            and hinted_phase != derived_phase
            and last_event is not None
        ):
            drift_reasons.append("phase_hint_conflicts_with_ledger")

    if resolved_feature_dir is not None and last_event in REQUIRED_ARTIFACTS_BY_EVENT:
        for artifact_name in REQUIRED_ARTIFACTS_BY_EVENT[last_event]:
            artifact_path = resolved_feature_dir / artifact_name
            if not artifact_path.exists():
                drift_reasons.append(f"missing_artifact:{artifact_name}")

    drift_detected = bool(drift_reasons) or bool(state.get("drift_detected", False))
    return {
        "feature_id": feature_id,
        "phase": phase,
        "last_event": last_event,
        "ledger_event_count": event_count,
        "approved_plan": approved_plan,
        "approved_solution": approved_solution,
        "blocked": bool(state.get("blocked", False)) or drift_detected,
        "drift_detected": drift_detected,
        "drift_reasons": sorted(set(drift_reasons)),
        "dry_run": bool(state.get("dry_run", False)),
    }
