"""get_type tool: type inference via PyrightClient hover.

Validates inputs, delegates to PyrightClient.hover(), and maps
results/errors to the contract-defined response shapes.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any

from src.mcp_codebase.pyright_client import PyrightClient
from src.mcp_codebase.security import validate_column, validate_line, validate_path

logger = logging.getLogger(__name__)


async def get_type_impl(
    file_path: str,
    *,
    line: int,
    column: int,
    project_root: Path,
    pyright_client: PyrightClient | None,
) -> dict[str, Any]:
    """Core get_type logic, decoupled from MCP registration.

    Returns either a TypeInfo dict or an error envelope dict.
    """
    start_time = time.monotonic()

    # Input validation
    try:
        if not file_path or not file_path.strip():
            raise ValueError("INVALID_ARGUMENT: file_path must not be empty")
        validate_line(line)
        validate_column(column)
    except ValueError as exc:
        code = _extract_error_code(str(exc))
        return {"error": {"code": code, "message": str(exc)}}

    # Path validation
    try:
        resolved = validate_path(file_path, project_root=project_root)
    except ValueError as exc:
        code = _extract_error_code(str(exc))
        return {"error": {"code": code, "message": str(exc)}}

    # LSP availability
    if pyright_client is None or pyright_client.state not in ("ready",):
        return {
            "error": {
                "code": "LSP_UNAVAILABLE",
                "message": "Type checker is not available",
            }
        }

    # Hover request
    try:
        hover_result = await pyright_client.hover(resolved, line=line, column=column)
    except (asyncio.TimeoutError, ConnectionError):
        latency_ms = (time.monotonic() - start_time) * 1000
        logger.warning(
            "get_type: query failed",
            extra={
                "file_path": file_path,
                "line": line,
                "column": column,
                "latency_ms": round(latency_ms, 1),
                "failure_code": "QUERY_FAILED",
            },
        )
        return {
            "error": {
                "code": "QUERY_FAILED",
                "message": f"Type checker query failed at {file_path}:{line}:{column}",
            }
        }

    latency_ms = (time.monotonic() - start_time) * 1000

    if hover_result is None:
        logger.info(
            "get_type: symbol not found",
            extra={
                "file_path": file_path,
                "line": line,
                "column": column,
                "latency_ms": round(latency_ms, 1),
                "failure_code": "SYMBOL_NOT_FOUND",
            },
        )
        return {
            "error": {
                "code": "SYMBOL_NOT_FOUND",
                "message": f"No type information at {file_path}:{line}:{column}",
            }
        }

    # Parse symbol name and type from hover result
    symbol_name, inferred_type = _parse_symbol_and_type(hover_result)

    logger.info(
        "get_type: success",
        extra={
            "file_path": file_path,
            "line": line,
            "column": column,
            "symbol_name": symbol_name,
            "latency_ms": round(latency_ms, 1),
            "lifecycle_state": pyright_client.state,
        },
    )

    return {
        "symbol_name": symbol_name,
        "inferred_type": inferred_type,
        "file_path": file_path,
        "line": line,
    }


def _extract_error_code(message: str) -> str:
    """Extract the error code prefix from a validation error message."""
    for code in (
        "INVALID_ARGUMENT",
        "PATH_OUT_OF_SCOPE",
        "FILE_NOT_FOUND",
        "SYMBOL_NOT_FOUND",
        "LSP_UNAVAILABLE",
    ):
        if message.startswith(code):
            return code
    return "INVALID_ARGUMENT"


def _parse_symbol_and_type(hover_text: str) -> tuple[str, str]:
    """Extract symbol name and type string from parsed hover output.

    Input is the result of PyrightClient._parse_hover_markdown, e.g.:
    - "x: int"
    - "def add(a: int, b: int) -> int"
    - "class Foo"
    - "MyType = list[int]"
    """
    # "name: type" pattern (variable, parameter, property)
    colon_match = re.match(r"^(\w+)\s*:\s*(.+)$", hover_text)
    if colon_match:
        return colon_match.group(1), colon_match.group(2).strip()

    # "def name(...) -> type" pattern (function, method)
    def_match = re.match(r"^def\s+(\w+)\s*\(", hover_text)
    if def_match:
        return def_match.group(1), hover_text

    # "class Name" pattern
    class_match = re.match(r"^class\s+(\w+)", hover_text)
    if class_match:
        return class_match.group(1), hover_text

    # "Name = type" pattern (type alias)
    alias_match = re.match(r"^(\w+)\s*=\s*(.+)$", hover_text)
    if alias_match:
        return alias_match.group(1), alias_match.group(2).strip()

    # Fallback
    return hover_text.split()[0] if hover_text.split() else hover_text, hover_text
