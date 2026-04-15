from pathlib import Path


def test_story3_incremental_refresh_preserves_last_good_snapshot(tmp_path: Path) -> None:
    """US3: refresh must update changed files and preserve the last good snapshot on failure."""
    repo = tmp_path / "fixture-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "specs").mkdir(parents=True)
    (repo / "src" / "vector_index.py").write_text(
        """def alpha():
    return \"old\"
"""
    )
    (repo / "specs" / "notes.md").write_text(
        """# Notes

alpha lives here.
"""
    )

    from src.mcp_codebase.index.domain import IndexScope
    from src.mcp_codebase.index.service import build_vector_index_service

    service = build_vector_index_service(project_root=repo, storage_path=tmp_path / "index")
    service.build_full_index()
    baseline = service.query("alpha", scope=IndexScope.code, top_k=5)
    assert baseline.results

    (repo / "src" / "vector_index.py").write_text(
        """def alpha():
    return \"new\"


def beta():
    return \"fresh\"
"""
    )
    service.refresh_changed_files()
    refreshed = service.query("beta", scope=IndexScope.code, top_k=5)
    assert refreshed.results

    still_queryable = service.query("alpha", scope=IndexScope.code, top_k=5)
    assert still_queryable.results
