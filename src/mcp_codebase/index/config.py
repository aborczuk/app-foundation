"""Index service configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.mcp_codebase.index.domain import IndexScope

EXCLUDE_PATTERNS_ENV = "MCP_CODEBASE_INDEX_EXCLUDE_PATTERNS"


class IndexConfig(BaseModel):
    """Repo-local vector index configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_root: Path
    db_path: Path
    embedding_model: str = Field(min_length=1)
    collection_name: str = Field(default="codebase-vector-index", min_length=1)
    default_scopes: tuple[IndexScope, ...] = Field(
        default_factory=lambda: (IndexScope.CODE, IndexScope.MARKDOWN)
    )
    exclude_patterns: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _normalize_paths_and_patterns(self) -> Self:
        repo_root = self.repo_root.expanduser().resolve()

        db_path = self.db_path.expanduser()
        if not db_path.is_absolute():
            db_path = (repo_root / db_path).resolve()
        else:
            db_path = db_path.resolve()

        try:
            db_path.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError("db_path must reside within repo_root") from exc

        if not self.embedding_model.strip():
            raise ValueError("embedding_model must not be blank")

        cleaned_patterns: list[str] = []
        for pattern in self.exclude_patterns:
            if not pattern or not pattern.strip():
                raise ValueError("exclude_patterns must not contain blank entries")
            cleaned_patterns.append(pattern.strip())

        object.__setattr__(self, "repo_root", repo_root)
        object.__setattr__(self, "db_path", db_path)
        object.__setattr__(self, "exclude_patterns", tuple(cleaned_patterns))
        return self


def load_exclude_patterns(raw_value: str | None = None) -> tuple[str, ...]:
    """Load configured exclude patterns from an environment string."""
    if raw_value is None:
        raw_value = os.getenv(EXCLUDE_PATTERNS_ENV, "")
    if not raw_value.strip():
        return ()
    patterns = [part.strip() for part in re.split(r"[,\n;]", raw_value) if part.strip()]
    return tuple(patterns)
