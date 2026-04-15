from pathlib import Path


def test_story2_markdown_section_lookup_returns_breadcrumb(tmp_path: Path) -> None:
    """US2: markdown queries should return breadcrumbed sections with previews."""
    repo = tmp_path / "fixture-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "specs").mkdir(parents=True)
    (repo / ".claude").mkdir(parents=True)
    (repo / "src" / "webhook_tools.py").write_text(
        """def dedupe_webhooks(payload):
    return payload
"""
    )
    (repo / "specs" / "webhook.md").write_text(
        """# Webhook Authentication

## Local Policy

This section covers webhook authentication and operator flow.
"""
    )
    (repo / ".claude" / "governance.md").write_text(
        """# Governance

## Webhook Authentication

Checklist for webhook authentication.
"""
    )

    from src.mcp_codebase.index.domain import IndexScope
    from src.mcp_codebase.index.service import build_vector_index_service

    service = build_vector_index_service(project_root=repo, storage_path=tmp_path / "index")
    service.build_full_index()

    result = service.query("webhook authentication", scope=IndexScope.markdown, top_k=5)
    assert result.results, "expected at least one ranked markdown section"
    first = result.results[0]
    assert first.file_path.endswith("webhook.md") or first.file_path.endswith("governance.md")
    assert first.breadcrumb
    assert first.preview
    assert len(first.preview) <= 200
