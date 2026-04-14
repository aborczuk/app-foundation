"""Unit tests for query-tool validation and failure handling."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.mcp_codebase.diag_tool import get_diagnostics_impl
from src.mcp_codebase.type_tool import get_type_impl


def _seed_repo(root: Path) -> Path:
    source = root / "src" / "module.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    return source


@pytest.mark.asyncio
async def test_query_tools_return_invalid_argument_for_empty_file_path(tmp_path: Path) -> None:
    type_result = await get_type_impl(
        "",
        line=1,
        column=0,
        project_root=tmp_path,
        pyright_client=None,
    )
    diagnostics_result = await get_diagnostics_impl(
        "",
        project_root=tmp_path,
    )

    assert type_result["error"]["code"] == "INVALID_ARGUMENT"
    assert diagnostics_result["error"]["code"] == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_get_type_distinguishes_missing_symbol_from_query_failure(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    class _MissingSymbolClient:
        state = "ready"

        async def hover(self, file_path: Path, *, line: int, column: int) -> str | None:
            return None

    class _QueryFailureClient:
        state = "ready"

        async def hover(self, file_path: Path, *, line: int, column: int) -> str | None:
            raise ConnectionError("pyright hover transport failed")

    missing_symbol = await get_type_impl(
        "src/module.py",
        line=1,
        column=0,
        project_root=tmp_path,
        pyright_client=_MissingSymbolClient(),
    )
    query_failure = await get_type_impl(
        "src/module.py",
        line=1,
        column=0,
        project_root=tmp_path,
        pyright_client=_QueryFailureClient(),
    )

    assert missing_symbol["error"]["code"] == "SYMBOL_NOT_FOUND"
    assert query_failure["error"]["code"] == "QUERY_FAILED"
    assert "query failed" in query_failure["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_diagnostics_reports_unavailable_on_subprocess_launch_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_repo(tmp_path)

    async def fake_create_subprocess_exec(*args, **kwargs):
        raise FileNotFoundError("pyright not installed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await get_diagnostics_impl(
        "src/module.py",
        project_root=tmp_path,
        pyright_command="pyright",
    )

    assert result["error"]["code"] == "LSP_UNAVAILABLE"
    assert "not available" in result["error"]["message"].lower()
