"""Path and argument validation for codebase-lsp MCP tools.

All tool arguments from agents are untrusted. Paths are canonicalized
and checked against the project root before any file operation.
"""

from __future__ import annotations

from pathlib import Path


def validate_path(file_path: str, *, project_root: Path) -> Path:
    """Resolve and validate a file path against the project root.

    Args:
        file_path: Relative or absolute path to validate.
        project_root: The project root directory (trust boundary).

    Returns:
        The resolved absolute Path, guaranteed to be within project_root.

    Raises:
        ValueError: With error code prefix (INVALID_ARGUMENT, PATH_OUT_OF_SCOPE,
            FILE_NOT_FOUND) for the caller to map to a ToolError.
    """
    if not file_path or not file_path.strip():
        raise ValueError("INVALID_ARGUMENT: file_path must not be empty")

    resolved_root = project_root.resolve()
    candidate = (resolved_root / file_path).resolve()

    # Scope check: resolved path must be within the project root
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        raise ValueError(
            "PATH_OUT_OF_SCOPE: resolved path escapes the project root"
        )

    # Existence check
    if not candidate.exists():
        raise ValueError("FILE_NOT_FOUND: file does not exist")

    if not candidate.is_file():
        raise ValueError("FILE_NOT_FOUND: path is not a regular file")

    return candidate


def validate_line(line: int) -> None:
    """Validate that line is >= 1.

    Raises:
        ValueError: With INVALID_ARGUMENT prefix if line < 1.
    """
    if line < 1:
        raise ValueError("INVALID_ARGUMENT: line must be >= 1")


def validate_column(column: int) -> None:
    """Validate that column is >= 0.

    Raises:
        ValueError: With INVALID_ARGUMENT prefix if column < 0.
    """
    if column < 0:
        raise ValueError("INVALID_ARGUMENT: column must be >= 0")
