"""Shared orchestration contract helpers for Speckit implement and QA flows."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

SUBAGENT_INITIAL_WAIT_SECONDS = 60
SUBAGENT_EXTENDED_WAIT_SECONDS = 120
INVALID_COMPLETION_RETRY_LIMIT = 1

VALID_QA_VERDICTS = {"PASS", "FIX_REQUIRED"}


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_payload_run_id(task_id: str, attempt: int, now: datetime | None = None) -> str:
    """Build a deterministic payload run identifier for one task attempt."""
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    safe_task = (task_id or "unknown").lower()
    return f"offline-qa-payload-{safe_task}-attempt-{attempt}-{timestamp}"


def compute_payload_digest(payload: Mapping[str, Any]) -> str:
    """Hash a payload deterministically while ignoring the digest field itself."""
    normalized = {key: value for key, value in payload.items() if key != "payload_digest"}
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _nonempty_string(value: Any) -> bool:
    """Return whether a value is a non-empty string after stripping."""
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, allow_empty: bool = False) -> bool:
    """Return whether a value is a list of non-empty strings."""
    if not isinstance(value, list):
        return False
    if not value:
        return allow_empty
    return all(_nonempty_string(item) for item in value)


def existing_payload_reasons(
    payload: Mapping[str, Any],
    *,
    feature_id: str,
    task_id: str,
    attempt: int,
) -> list[str]:
    """Return reasons an existing payload cannot be safely reused."""
    reasons: list[str] = []
    if payload.get("feature_id") != feature_id:
        reasons.append("feature_id_mismatch")
    if payload.get("task_id") != task_id:
        reasons.append("task_id_mismatch")
    if payload.get("attempt") != attempt:
        reasons.append("attempt_mismatch")
    if not _nonempty_string(payload.get("payload_run_id")):
        reasons.append("missing_payload_run_id")
    digest = payload.get("payload_digest")
    if not _nonempty_string(digest):
        reasons.append("missing_payload_digest")
    elif compute_payload_digest(payload) != digest:
        reasons.append("payload_digest_mismatch")
    return reasons


def offline_result_reasons(
    result: Mapping[str, Any],
    *,
    feature_id: str,
    task_id: str,
    payload_run_id: str,
    payload_digest: str,
) -> list[str]:
    """Return reasons an offline QA result is invalid for the active task attempt."""
    reasons: list[str] = []
    if result.get("feature_id") != feature_id:
        reasons.append("result_feature_id_mismatch")
    if result.get("task_id") != task_id:
        reasons.append("result_task_id_mismatch")
    if result.get("payload_run_id") != payload_run_id:
        reasons.append("result_payload_run_id_mismatch")
    if result.get("payload_digest") != payload_digest:
        reasons.append("result_payload_digest_mismatch")
    if not _nonempty_string(result.get("qa_run_id")):
        reasons.append("missing_qa_run_id")
    verdict = result.get("verdict")
    if not _nonempty_string(verdict):
        reasons.append("missing_verdict")
    elif verdict not in VALID_QA_VERDICTS:
        reasons.append("invalid_verdict")
    if not _string_list(result.get("changed_files_considered"), allow_empty=False):
        reasons.append("invalid_changed_files_considered")
    return reasons
