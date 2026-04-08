"""CLI entrypoint and async lifecycle guards for mcp_clickup."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from collections.abc import Callable, Coroutine
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


def build_client(api_token: str) -> ClickUpClient:
    """Build the runtime ClickUp client instance."""
    return ClickUpClient(api_token=api_token)


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
    env = _load_runtime_env()
    if env is None:
        return 1

    token, space_id = env
    specs_root, manifest_path = _runtime_paths()
    artifacts = discover_spec_artifacts(specs_root)

    manifest = None
    if manifest_path.exists():
        try:
            manifest = load_manifest(manifest_path)
        except ManifestVersionError as exc:
            _print_error("manifest_version", str(exc), "Regenerate or migrate the manifest schema")
            return 1

    async with build_client(token) as client:
        engine = SyncEngine(client)
        try:
            await engine.bootstrap_from_artifacts(
                artifacts=artifacts,
                space_id=space_id,
                manifest=manifest,
                flush_manifest=lambda m: save_manifest(manifest_path, m),
            )
        except MissingCustomFieldsError as exc:
            _print_error("missing_field", str(exc), "Pre-create missing routing fields at the Space level")
            return 2
        except ClickUpNotFoundError as exc:
            _print_error("space_not_found", str(exc), "Verify CLICKUP_SPACE_ID and token access")
            return 1
        except ClickUpRateLimitError as exc:
            _print_error("rate_limit", str(exc), "Re-run bootstrap; manifest retains partial progress")
            return 1
        except ManifestRebuildAmbiguousError as exc:
            _print_error(
                "manifest_rebuild_ambiguous",
                str(exc),
                "Resolve duplicate ClickUp items for the same canonical key and rerun",
            )
            return 1
        except ClickUpAuthError as exc:
            _print_error("auth_error", str(exc), "Verify CLICKUP_API_TOKEN")
            return 1
        except (ClickUpTimeoutError, ClickUpApiError) as exc:
            _print_error("api_error", str(exc), "Retry and inspect ClickUp availability")
            return 1

    return 0


async def status_async() -> int:
    """Run read-only status flow asynchronously."""
    env = _load_runtime_env()
    if env is None:
        return 1

    token, space_id = env
    _, manifest_path = _runtime_paths()
    if not manifest_path.exists():
        _print_error(
            "manifest_missing",
            "Manifest file does not exist",
            "Run bootstrap first to create .speckit/clickup-manifest.json",
        )
        return 1

    try:
        manifest = load_manifest(manifest_path)
    except ManifestVersionError as exc:
        _print_error("manifest_version", str(exc), "Regenerate or migrate the manifest schema")
        return 1

    async with build_client(token) as client:
        engine = SyncEngine(client)
        try:
            summary = await engine.status_from_manifest(manifest)
        except ClickUpNotFoundError as exc:
            _print_error("space_not_found", str(exc), "Verify CLICKUP_SPACE_ID and token access")
            return 1
        except ClickUpRateLimitError as exc:
            _print_error("rate_limit", str(exc), "Retry status query after rate-limit window")
            return 1
        except ClickUpAuthError as exc:
            _print_error("auth_error", str(exc), "Verify CLICKUP_API_TOKEN")
            return 1
        except (ClickUpTimeoutError, ClickUpApiError) as exc:
            _print_error("api_error", str(exc), "Retry and inspect ClickUp availability")
            return 1

    _render_status_summary(space_id, summary)
    return 0


def _run_entrypoint(factory: Callable[[], Coroutine[Any, Any, int]]) -> int:
    """Run an async CLI entrypoint unless already inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    raise RuntimeError("mcp_clickup CLI cannot run inside an active event loop")


def run_bootstrap() -> int:
    """Run bootstrap entrypoint from sync context."""
    return _run_entrypoint(bootstrap_async)


def run_status() -> int:
    """Run status entrypoint from sync context."""
    return _run_entrypoint(status_async)


def main(argv: list[str] | None = None) -> int:
    """Parse CLI flags and execute bootstrap or status mode."""
    parser = argparse.ArgumentParser(prog="python -m mcp_clickup")
    parser.add_argument("--status", action="store_true", help="Run read-only status summary")
    args = parser.parse_args(argv)

    if args.status:
        return run_status()
    return run_bootstrap()


if __name__ == "__main__":
    raise SystemExit(main())
