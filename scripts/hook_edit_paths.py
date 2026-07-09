#!/usr/bin/env python3
"""Shared path-check helpers for edit-related hooks."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PYTHON_SUFFIXES = {".py", ".pyi"}
PATCH_FILE_PATTERN = re.compile(
    r"^\*\*\* (?P<op>Add|Update|Delete) File: (?P<path>.+)$",
    re.MULTILINE,
)
DIRECT_EDIT_BRANCH_EXEMPT_MARKDOWN_ROOTS = (
    Path("specs"),
    Path("docs") / "governance",
)


def patch_changed_paths(patch: str) -> list[str]:
    """Return file path candidates extracted from an apply_patch-style patch payload."""
    candidates: list[str] = []
    for match in PATCH_FILE_PATTERN.finditer(patch):
        raw_path = match.group("path").strip()
        if not raw_path:
            continue
        if match.group("op") == "Delete":
            candidates.append(str(Path(raw_path).parent))
        else:
            candidates.append(raw_path)
    return candidates


def collect_changed_paths(payload: dict[str, Any], *, root: Path) -> list[Path]:
    """Resolve repo-local changed paths from direct tool-input keys or patch text."""
    tool_input = payload.get("tool_input") or {}
    candidates: list[str] = []

    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    for key in ("file_paths", "paths"):
        value = tool_input.get(key)
        if isinstance(value, list):
            candidates.extend(item.strip() for item in value if isinstance(item, str) and item.strip())

    patch = tool_input.get("patch")
    if isinstance(patch, str) and patch.strip():
        candidates.extend(patch_changed_paths(patch))

    resolved: set[Path] = set()
    for raw in candidates:
        path = Path(raw)
        if not path.is_absolute():
            path = (root / path).resolve()
        else:
            path = path.resolve()

        try:
            path.relative_to(root)
        except ValueError:
            continue

        resolved.add(path)

    return sorted(resolved)


def python_paths(paths: Iterable[Path]) -> list[Path]:
    """Return repo-local changed paths that need Python validation."""
    return [path for path in paths if path.suffix.lower() in PYTHON_SUFFIXES]


def direct_edit_branch_guard_paths(paths: Iterable[Path], *, root: Path) -> list[Path]:
    """Return direct-edit paths that must stay behind the feature-branch guard."""
    return [path for path in paths if not is_branch_exempt_direct_edit_path(path, root=root)]


def is_branch_exempt_direct_edit_path(path: Path, *, root: Path) -> bool:
    """Return true when a direct edit targets exempt Markdown-only spec or governance docs."""
    if path.suffix.lower() != ".md":
        return False

    try:
        relative_path = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False

    return any(
        relative_path == exempt_root or exempt_root in relative_path.parents
        for exempt_root in DIRECT_EDIT_BRANCH_EXEMPT_MARKDOWN_ROOTS
    )
