#!/usr/bin/env python3
"""State helpers for the deterministic pipeline driver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping


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
) -> dict[str, Any]:
    """Return a normalized phase-state shape for the given feature.

    This is intentionally lightweight for T002. Later tasks add ledger-backed
    state resolution and drift detection.
    """

    if not feature_id:
        raise ValueError("feature_id is required")

    state = dict(pipeline_state or {})
    return {
        "feature_id": feature_id,
        "phase": state.get("phase", "unknown"),
        "blocked": bool(state.get("blocked", False)),
        "drift_detected": bool(state.get("drift_detected", False)),
    }
