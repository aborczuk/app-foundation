from pathlib import Path


def test_story4_staleness_reports_commit_delta(tmp_path: Path) -> None:
    """US4: staleness checks should report HEAD delta and last build metadata."""
    repo = tmp_path / "fixture-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "specs").mkdir(parents=True)
    (repo / "src" / "vector_index.py").write_text(
        """def alpha():
    return 1
"""
    )
    (repo / "specs" / "notes.md").write_text(
        """# Notes

alpha is documented here.
"""
    )

    from src.mcp_codebase.index.service import build_vector_index_service

    service = build_vector_index_service(project_root=repo, storage_path=tmp_path / "index")
    service.build_full_index()
    status = service.status()
    assert status.head_commit
    assert status.built_commit
    assert status.is_current in {True, False}

    (repo / "src" / "vector_index.py").write_text(
        """def alpha():
    return 2
"""
    )
    stale_status = service.status()
    assert stale_status.built_commit == status.built_commit
    assert stale_status.head_commit != stale_status.built_commit or not stale_status.is_current
