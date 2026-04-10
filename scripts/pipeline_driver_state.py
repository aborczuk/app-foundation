#!/usr/bin/env python3
"""State helpers for the deterministic pipeline driver."""

from __future__ import annotations

from typing import Any, Mapping


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

