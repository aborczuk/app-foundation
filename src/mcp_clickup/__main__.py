"""CLI entrypoint and async lifecycle guards for mcp_clickup."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from src.mcp_clickup.artifact_parser import discover_spec_artifacts
from src.mcp_clickup.clickup_client import (
    ClickUpApiError,
    ClickUpAuthError,
    ClickUpClient,
    ClickUpNotFoundError,
    ClickUpRateLimitError,
    ClickUpTimeoutError,
)
from src.mcp_clickup.manifest import ManifestVersionError, load_manifest, save_manifest
from src.mcp_clickup.sync_engine import (
    ClickUpTransportProtocol,
    ManifestRebuildAmbiguousError,
    MissingCustomFieldsError,
    SyncEngine,
)

_TOKEN_RE = re.compile(r"\bpk_[A-Za-z0-9]+\b")
_BEARER_RE = re.compile(r"(?i)authorization:\s*bearer\s+[^\s]+")


def _sanitize_message(message: str) -> str:
    """Redact token-like content from surfaced error messages."""
    sanitized = _TOKEN_RE.sub("[REDACTED_TOKEN]", message)
    sanitized = _BEARER_RE.sub("Authorization: Bearer [REDACTED_TOKEN]", sanitized)
    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    if token:
        sanitized = sanitized.replace(token, "[REDACTED_TOKEN]")
    return sanitized


def _print_error(code: str, message: str, hint: str) -> None:
    print(f"ERROR [{code}]: {_sanitize_message(message)}", file=sys.stderr)
    print(f"  -> {hint}", file=sys.stderr)


def _result_payload(
    *,
    mode: str,
    ok: bool,
    exit_code: int,
    space_id: str | None = None,
    error_code: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Build a structured CLI result payload for automation callers."""
    return {
        "mode": mode,
        "ok": ok,
        "exit_code": exit_code,
        "space_id": space_id,
        "error_code": error_code,
        "message": message,
    }


def build_direct_clickup_transport(api_token: str) -> ClickUpClient:
    """Build the current direct ClickUp transport implementation."""
    return ClickUpClient(api_token=api_token)


@asynccontextmanager
async def build_transport(api_token: str) -> AsyncIterator[ClickUpTransportProtocol]:
    """Build the runtime transport context consumed by sync orchestration."""
    async with build_direct_clickup_transport(api_token) as transport:
        yield transport


def _runtime_paths() -> tuple[Path, Path]:
    root = Path(os.environ.get("SPECKIT_ROOT", Path.cwd())).resolve()
    return root / "specs", root / ".speckit" / "clickup-manifest.json"


def _load_runtime_env() -> tuple[str, str] | None:
    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    space_id = os.environ.get("CLICKUP_SPACE_ID", "").strip()
    if not token or not space_id:
        _print_error(
            "missing_env",
            "CLICKUP_API_TOKEN and CLICKUP_SPACE_ID are required",
            "Set CLICKUP_API_TOKEN and CLICKUP_SPACE_ID in your environment before running",
        )
        return None
    return token, space_id


def _render_status_summary(space_id: str, summary: object) -> None:
    """Render grouped status summary to stdout."""
    print("ClickUp Subtask Status")
    print(f"  Space: {space_id}")
    print("")

    by_list = getattr(summary, "by_list", {})
    for feature_num in sorted(by_list.keys()):
        item = by_list[feature_num]
        print(f"  {item.list_name}")
        print(f"    Done         {item.done}")
        print(f"    In Progress  {item.in_progress}")
        print(f"    Blocked      {item.blocked}")
        print(f"    Not Started  {item.not_started}")
        if item.drift:
            for drift_key in item.drift:
                print(f"    Drift        {drift_key}")
        print("")


async def bootstrap_async() -> int:
    """Run bootstrap flow asynchronously."""
    return (await bootstrap_async_result())["exit_code"]


async def bootstrap_async_result() -> dict[str, Any]:
    """Run bootstrap flow and return a structured result payload."""
    env = _load_runtime_env()
    if env is None:
        return _result_payload(
            mode="bootstrap",
            ok=False,
            exit_code=1,
            error_code="missing_env",
            message="CLICKUP_API_TOKEN and CLICKUP_SPACE_ID are required",
        )

    token, space_id = env
    specs_root, manifest_path = _runtime_paths()
    artifacts = discover_spec_artifacts(specs_root)

    manifest = None
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
        except ManifestVersionError as exc:
            _print_error("manifest_version", str(exc), "Regenerate or migrate the manifest schema")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="manifest_version",
                message=str(exc),
            )

    async with build_transport(token) as transport:
        engine = SyncEngine(transport)
        try:
            await engine.bootstrap_from_artifacts(
                artifacts=artifacts,
                space_id=space_id,
                manifest=manifest,
                flush_manifest=lambda m: save_manifest(manifest_path, m),
            )
        except MissingCustomFieldsError as exc:
            _print_error("missing_field", str(exc), "Pre-create missing routing fields at the Space level")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=2,
                space_id=space_id,
                error_code="missing_field",
                message=str(exc),
            )
        except ClickUpNotFoundError as exc:
            _print_error("space_not_found", str(exc), "Verify CLICKUP_SPACE_ID and token access")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="space_not_found",
                message=str(exc),
            )
        except ClickUpRateLimitError as exc:
            _print_error("rate_limit", str(exc), "Re-run bootstrap; manifest retains partial progress")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="rate_limit",
                message=str(exc),
            )
        except ManifestRebuildAmbiguousError as exc:
            _print_error(
                "manifest_rebuild_ambiguous",
                str(exc),
                "Resolve duplicate ClickUp items for the same canonical key and rerun",
            )
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="manifest_rebuild_ambiguous",
                message=str(exc),
            )
        except ClickUpAuthError as exc:
            _print_error("auth_error", str(exc), "Verify CLICKUP_API_TOKEN")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="auth_error",
                message=str(exc),
            )
        except (ClickUpTimeoutError, ClickUpApiError) as exc:
            _print_error("api_error", str(exc), "Retry and inspect ClickUp availability")
            return _result_payload(
                mode="bootstrap",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="api_error",
                message=str(exc),
            )

    return _result_payload(mode="bootstrap", ok=True, exit_code=0, space_id=space_id)


async def status_async() -> int:
    """Run read-only status flow asynchronously."""
    return (await status_async_result())["exit_code"]


async def status_async_result() -> dict[str, Any]:
    """Run read-only status flow and return a structured result payload."""
    env = _load_runtime_env()
    if env is None:
        return _result_payload(
            mode="status",
            ok=False,
            exit_code=1,
            error_code="missing_env",
            message="CLICKUP_API_TOKEN and CLICKUP_SPACE_ID are required",
        )

    token, space_id = env
    _, manifest_path = _runtime_paths()
    if not manifest_path.exists():
        _print_error(
            "manifest_missing",
            "Manifest file does not exist",
            "Run bootstrap first to create .speckit/clickup-manifest.json",
        )
        return _result_payload(
            mode="status",
            ok=False,
            exit_code=1,
            space_id=space_id,
            error_code="manifest_missing",
            message="Manifest file does not exist",
        )

    try:
        manifest = load_manifest(manifest_path)
    except ManifestVersionError as exc:
        _print_error("manifest_version", str(exc), "Regenerate or migrate the manifest schema")
        return _result_payload(
            mode="status",
            ok=False,
            exit_code=1,
            space_id=space_id,
            error_code="manifest_version",
            message=str(exc),
        )

    async with build_transport(token) as transport:
        engine = SyncEngine(transport)
        try:
            summary = await engine.status_from_manifest(manifest)
        except ClickUpNotFoundError as exc:
            _print_error("space_not_found", str(exc), "Verify CLICKUP_SPACE_ID and token access")
            return _result_payload(
                mode="status",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="space_not_found",
                message=str(exc),
            )
        except ClickUpRateLimitError as exc:
            _print_error("rate_limit", str(exc), "Retry status query after rate-limit window")
            return _result_payload(
                mode="status",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="rate_limit",
                message=str(exc),
            )
        except ClickUpAuthError as exc:
            _print_error("auth_error", str(exc), "Verify CLICKUP_API_TOKEN")
            return _result_payload(
                mode="status",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="auth_error",
                message=str(exc),
            )
        except (ClickUpTimeoutError, ClickUpApiError) as exc:
            _print_error("api_error", str(exc), "Retry and inspect ClickUp availability")
            return _result_payload(
                mode="status",
                ok=False,
                exit_code=1,
                space_id=space_id,
                error_code="api_error",
                message=str(exc),
            )

    _render_status_summary(space_id, summary)
    return _result_payload(mode="status", ok=True, exit_code=0, space_id=space_id)


def _run_entrypoint(factory: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    """Run an async CLI entrypoint unless already inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    raise RuntimeError("mcp_clickup CLI cannot run inside an active event loop")


def run_bootstrap() -> int:
    """Run bootstrap entrypoint from sync context."""
    return _run_entrypoint(bootstrap_async)


def run_bootstrap_result() -> dict[str, Any]:
    """Run bootstrap entrypoint and return a structured result."""
    return _run_entrypoint(bootstrap_async_result)


def run_status() -> int:
    """Run status entrypoint from sync context."""
    return _run_entrypoint(status_async)


def run_status_result() -> dict[str, Any]:
    """Run status entrypoint and return a structured result."""
    return _run_entrypoint(status_async_result)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI flags and execute bootstrap or status mode."""
    parser = argparse.ArgumentParser(prog="python -m mcp_clickup")
    parser.add_argument("--status", action="store_true", help="Run read-only status summary")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON result to stdout")
    args = parser.parse_args(argv)

    if args.status:
        result = run_status_result()
    else:
        result = run_bootstrap_result()
    if args.json:
        print(json.dumps(result))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
