"""get_diagnostics tool: pyright diagnostics via per-call subprocess.

Runs pyright --outputjson as an asyncio subprocess, parses the JSON
output, and maps results/errors to the contract-defined response shapes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.mcp_codebase import config
from src.mcp_codebase.security import validate_path

logger = logging.getLogger(__name__)


async def get_diagnostics_impl(
    file_path: str,
    *,
    project_root: Path,
    pyright_command: str | None = None,
    timeout_s: float | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Core get_diagnostics logic, decoupled from MCP registration.

    Returns either a list of DiagnosticResult dicts or an error envelope dict.
    """
    start_time = time.monotonic()
    cmd = pyright_command or config.PYRIGHT_CLI_COMMAND
    timeout = timeout_s if timeout_s is not None else config.DIAGNOSTICS_TIMEOUT_S

    # Input validation
    if not file_path or not file_path.strip():
        return {
            "error": {
                "code": "INVALID_ARGUMENT",
                "message": "INVALID_ARGUMENT: file_path must not be empty",
            }
        }

    # Path validation
    try:
        resolved = validate_path(file_path, project_root=project_root)
    except ValueError as exc:
        code = _extract_error_code(str(exc))
        return {"error": {"code": code, "message": str(exc)}}

    # Run pyright --outputjson
    try:
        process = await asyncio.create_subprocess_exec(
            cmd,
            "--outputjson",
            str(resolved),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_root),
        )
    except (FileNotFoundError, PermissionError) as exc:
        logger.error(
            "get_diagnostics: subprocess launch failed",
            extra={"error": str(exc), "command": cmd},
        )
        return {
            "error": {
                "code": "LSP_UNAVAILABLE",
                "message": "Type checker is not available",
            }
        }

    # Wait with timeout
    timeout_killed = False
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        timeout_killed = True
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        logger.warning(
            "get_diagnostics: subprocess timed out",
            extra={"timeout_s": timeout, "file_path": file_path},
        )
        return {
            "error": {
                "code": "LSP_UNAVAILABLE",
                "message": f"Type checker timed out after {timeout}s",
            }
        }

    latency_ms = (time.monotonic() - start_time) * 1000
    exit_code = process.returncode

    # Parse output
    try:
        diagnostics = _parse_pyright_output(
            stdout.decode("utf-8", errors="replace"), file_path=file_path
        )
    except ValueError:
        logger.error(
            "get_diagnostics: non-parseable output",
            extra={
                "exit_code": exit_code,
                "stdout_len": len(stdout),
                "file_path": file_path,
            },
        )
        return {
            "error": {
                "code": "LSP_UNAVAILABLE",
                "message": "Type checker returned non-parseable output",
            }
        }

    logger.info(
        "get_diagnostics: success",
        extra={
            "file_path": file_path,
            "diagnostic_count": len(diagnostics),
            "latency_ms": round(latency_ms, 1),
            "exit_code": exit_code,
            "timeout_killed": timeout_killed,
        },
    )

    return diagnostics


def _parse_pyright_output(
    stdout: str, *, file_path: str
) -> list[dict[str, Any]]:
    """Parse pyright --outputjson stdout into DiagnosticResult dicts.

    Args:
        stdout: Raw stdout from pyright --outputjson.
        file_path: Original relative file_path for the response.

    Returns:
        List of diagnostic dicts with 1-based line numbers.

    Raises:
        ValueError: If output is not valid JSON or missing expected fields.
    """
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        raise ValueError("LSP_UNAVAILABLE: non-parseable pyright output")

    if "generalDiagnostics" not in data:
        raise ValueError("LSP_UNAVAILABLE: missing generalDiagnostics field")

    diagnostics: list[dict[str, Any]] = []
    for diag in data["generalDiagnostics"]:
        start = diag.get("range", {}).get("start", {})
        diagnostics.append({
            "message": diag.get("message", ""),
            "severity": diag.get("severity", "error"),
            "file_path": file_path,
            "line": start.get("line", 0) + 1,  # 0-based → 1-based
            "column": start.get("character", 0),
            "rule": diag.get("rule", ""),
        })

    return diagnostics


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
