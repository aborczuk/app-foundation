"""Typed domain models for the local vector index."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IndexScope(str, Enum):
    """The content scope stored in or queried from the index."""

    CODE = "code"
    MARKDOWN = "markdown"


class _SpanRecord(BaseModel):
    """Shared span metadata for code and markdown content units."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    file_path: Path
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    scope: IndexScope
    preview: str = ""

    @model_validator(mode="after")
    def _validate_span(self) -> Self:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class CodeSymbol(_SpanRecord):
    """Normalized Python symbol entry."""

    symbol_name: str = Field(min_length=1)
    qualified_name: str = ""
    signature: str = ""
    docstring: str = ""
    scope: IndexScope = IndexScope.CODE


class MarkdownSection(_SpanRecord):
    """Normalized markdown section entry."""

    heading: str = Field(min_length=1)
    breadcrumb: tuple[str, ...] = Field(default_factory=tuple)
    depth: int = Field(ge=1)
    scope: IndexScope = IndexScope.MARKDOWN


class IndexMetadata(BaseModel):
    """Freshness and build metadata for a local index snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_root: Path
    indexed_commit: str = Field(min_length=1)
    current_commit: str = Field(min_length=1)
    indexed_at: datetime
    entry_count: int = Field(ge=0)
    is_stale: bool = False
    stale_reason: str = ""
    scopes: tuple[IndexScope, ...] = Field(
        default_factory=lambda: (IndexScope.CODE, IndexScope.MARKDOWN)
    )

    @model_validator(mode="after")
    def _validate_freshness(self) -> Self:
        if self.indexed_commit == self.current_commit:
            if self.is_stale:
                raise ValueError("fresh metadata cannot be marked stale")
            if self.stale_reason:
                raise ValueError("fresh metadata must not include a stale_reason")
        else:
            if not self.is_stale:
                raise ValueError("stale metadata must set is_stale=True")
            if not self.stale_reason:
                raise ValueError("stale metadata must include a stale_reason")
        return self


class QueryResult(BaseModel):
    """Ranked query result that preserves typed content provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    content: CodeSymbol | MarkdownSection
