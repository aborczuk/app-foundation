"""mcp_codebase — Python LSP Bridge for AI Agents.

Exposes two MCP tools backed by pyright:
- get_type: type inference via persistent pyright --lsp subprocess
- get_diagnostics: diagnostic list via per-call pyright --outputjson subprocess
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TypeInfo(BaseModel):
    """Result returned by get_type."""

    symbol_name: str = Field(min_length=1)
    inferred_type: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    line: int = Field(ge=1)


class DiagnosticResult(BaseModel):
    """One diagnostic entry returned by get_diagnostics."""

    message: str = Field(min_length=1)
    severity: str = Field(pattern=r"^(error|warning|information)$")
    file_path: str = Field(min_length=1)
    line: int = Field(ge=1)
    column: int = Field(ge=0)
    rule: str = ""


class ToolError(BaseModel):
    """Structured error envelope for tool failures."""

    code: str = Field(
        pattern=r"^(PATH_OUT_OF_SCOPE|FILE_NOT_FOUND|SYMBOL_NOT_FOUND|LSP_UNAVAILABLE|INVALID_ARGUMENT)$"
    )
    message: str = Field(min_length=1)
