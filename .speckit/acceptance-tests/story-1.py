from pathlib import Path


def test_story1_code_symbol_lookup_returns_metadata_and_empty_results(tmp_path: Path) -> None:
    """US1: semantic code-symbol lookup should return actionable metadata."""
    repo = tmp_path / "fixture-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "specs").mkdir(parents=True)
    (repo / ".claude").mkdir(parents=True)
    (repo / "src" / "webhook_tools.py").write_text(
        """def dedupe_webhooks(payload):
    \"\"\"webhook deduplication helper\"\"\"
    return payload
"""
    )
    (repo / "src" / "other.py").write_text(
        """def unrelated():
    return 1
"""
    )
    (repo / "specs" / "notes.md").write_text(
        """# Notes

Webhook deduplication should be easy to find.
"""
    )
    (repo / ".claude" / "policy.md").write_text(
        """# Policy

Webhook authentication guidance lives here.
"""
    )

    from src.mcp_codebase.index.domain import IndexScope
    from src.mcp_codebase.index.service import build_vector_index_service

    service = build_vector_index_service(project_root=repo, storage_path=tmp_path / "index")
    service.build_full_index()

    result = service.query("webhook deduplication", scope=IndexScope.code, top_k=5)
    assert result.results, "expected at least one ranked code-symbol result"
    first = result.results[0]
    assert first.file_path.endswith("webhook_tools.py")
    assert first.line_start <= first.line_end
    assert first.symbol_type

    empty = service.query("nonexistent concept XYZ", scope=IndexScope.code, top_k=5)
    assert empty.results == []
