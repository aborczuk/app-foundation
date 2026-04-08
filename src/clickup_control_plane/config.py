"""Runtime environment configuration for the ClickUp control-plane service."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when required runtime configuration is missing or malformed."""


@dataclass(frozen=True)
class ScopeAllowlist:
    """Allowlisted ClickUp scope identifiers accepted for dispatch."""

    space_ids: tuple[str, ...]
    list_ids: tuple[str, ...]


@dataclass(frozen=True)
class ControlPlaneRuntimeConfig:
    """Validated runtime configuration loaded from environment variables."""

    clickup_api_token: str
    clickup_webhook_secret: str
    n8n_dispatch_base_url: str
    control_plane_db_path: Path
    allowlist: ScopeAllowlist
    request_timeout_seconds: float = 10.0
    completion_callback_token: str | None = None
    qa_trigger_status: str = "Ready for QA"
    qa_build_status: str = "Build"
    qa_pass_status: str = "Done"
    qa_max_failures: int = 3
    hitl_waiting_status: str = "Waiting for Input"
    hitl_blocked_status: str = "Blocked"
    hitl_timeout_seconds: int = 86400


def load_runtime_config(env: Mapping[str, str] | None = None) -> ControlPlaneRuntimeConfig:
    """Load and validate runtime env vars for the control-plane service."""
    source = env if env is not None else os.environ
    clickup_api_token = _require_env(source, "CLICKUP_API_TOKEN")
    clickup_webhook_secret = _require_env(source, "CLICKUP_WEBHOOK_SECRET")
    n8n_dispatch_base_url = _validate_http_url(
        _require_env(source, "N8N_DISPATCH_BASE_URL"),
        env_key="N8N_DISPATCH_BASE_URL",
    )
    allowlist = _parse_allowlist(_require_env(source, "CONTROL_PLANE_ALLOWLIST"))

    db_path_raw = source.get("CONTROL_PLANE_DB_PATH", ".speckit/control-plane.db").strip()
    if not db_path_raw:
        raise ConfigError("CONTROL_PLANE_DB_PATH cannot be blank.")
    control_plane_db_path = Path(db_path_raw)

    timeout_raw = source.get("CONTROL_PLANE_REQUEST_TIMEOUT_SECONDS", "10").strip()
    try:
        request_timeout_seconds = float(timeout_raw)
    except ValueError as exc:
        raise ConfigError(
            "CONTROL_PLANE_REQUEST_TIMEOUT_SECONDS must be a numeric value."
        ) from exc
    if request_timeout_seconds <= 0:
        raise ConfigError("CONTROL_PLANE_REQUEST_TIMEOUT_SECONDS must be > 0.")

    completion_callback_token = source.get("CONTROL_PLANE_COMPLETION_TOKEN")
    if completion_callback_token is not None:
        completion_callback_token = completion_callback_token.strip() or None

    qa_trigger_status = _read_non_empty_with_default(
        source,
        env_key="CONTROL_PLANE_QA_TRIGGER_STATUS",
        default="Ready for QA",
    )
    qa_build_status = _read_non_empty_with_default(
        source,
        env_key="CONTROL_PLANE_BUILD_STATUS",
        default="Build",
    )
    qa_pass_status = _read_non_empty_with_default(
        source,
        env_key="CONTROL_PLANE_QA_PASS_STATUS",
        default="Done",
    )
    qa_max_failures = _parse_positive_int_with_default(
        source,
        env_key="CONTROL_PLANE_QA_MAX_FAILURES",
        default=3,
    )
    hitl_waiting_status = _read_non_empty_with_default(
        source,
        env_key="CONTROL_PLANE_HITL_WAITING_STATUS",
        default="Waiting for Input",
    )
    hitl_blocked_status = _read_non_empty_with_default(
        source,
        env_key="CONTROL_PLANE_HITL_BLOCKED_STATUS",
        default="Blocked",
    )
    hitl_timeout_seconds = _parse_positive_int_with_default(
        source,
        env_key="CONTROL_PLANE_HITL_TIMEOUT_SECONDS",
        default=86400,
    )

    return ControlPlaneRuntimeConfig(
        clickup_api_token=clickup_api_token,
        clickup_webhook_secret=clickup_webhook_secret,
        n8n_dispatch_base_url=n8n_dispatch_base_url,
        control_plane_db_path=control_plane_db_path,
        allowlist=allowlist,
        request_timeout_seconds=request_timeout_seconds,
        completion_callback_token=completion_callback_token,
        qa_trigger_status=qa_trigger_status,
        qa_build_status=qa_build_status,
        qa_pass_status=qa_pass_status,
        qa_max_failures=qa_max_failures,
        hitl_waiting_status=hitl_waiting_status,
        hitl_blocked_status=hitl_blocked_status,
        hitl_timeout_seconds=hitl_timeout_seconds,
    )


def _require_env(env: Mapping[str, str], key: str) -> str:
    value = env.get(key, "")
    if not value or not value.strip():
        raise ConfigError(f"Missing required environment variable: {key}")
    return value.strip()


def _validate_http_url(raw_url: str, *, env_key: str) -> str:
    parsed = urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{env_key} must be a valid http(s) URL.")
    return raw_url


def _parse_allowlist(raw: str) -> ScopeAllowlist:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError("CONTROL_PLANE_ALLOWLIST must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ConfigError("CONTROL_PLANE_ALLOWLIST must decode to an object.")

    space_ids = _coerce_string_list(payload.get("space_ids"), field_name="space_ids")
    list_ids = _coerce_string_list(payload.get("list_ids"), field_name="list_ids")
    if not space_ids and not list_ids:
        raise ConfigError(
            "CONTROL_PLANE_ALLOWLIST must include at least one space_ids/list_ids entry."
        )
    return ScopeAllowlist(space_ids=tuple(space_ids), list_ids=tuple(list_ids))


def _coerce_string_list(value: object, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"CONTROL_PLANE_ALLOWLIST.{field_name} must be a list of strings.")

    coerced: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"CONTROL_PLANE_ALLOWLIST.{field_name} must contain non-empty strings."
            )
        coerced.append(item.strip())
    return coerced


def _read_non_empty_with_default(
    env: Mapping[str, str],
    *,
    env_key: str,
    default: str,
) -> str:
    raw = env.get(env_key)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        raise ConfigError(f"{env_key} cannot be blank.")
    return value


def _parse_positive_int_with_default(
    env: Mapping[str, str],
    *,
    env_key: str,
    default: int,
) -> int:
    raw = env.get(env_key)
    if raw is None:
        return default
    value = raw.strip()
    if not value:
        raise ConfigError(f"{env_key} cannot be blank.")
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{env_key} must be an integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{env_key} must be > 0.")
    return parsed
