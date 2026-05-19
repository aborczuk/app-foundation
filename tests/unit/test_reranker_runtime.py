"""Unit tests for shared reranker daemon runtime path selection."""

from __future__ import annotations

from pathlib import Path

from src.mcp_codebase.index import reranker_runtime


def test_reranker_runtime_dir_defaults_to_shared_repo_local_dir(monkeypatch) -> None:
    """The default runtime dir should stay repo-local so sandbox and host share the same markers."""
    monkeypatch.delenv("SPECKIT_READ_CODE_RERANKER_RUNTIME_ROOT", raising=False)
    repo_root = Path("/tmp/example-repo")

    assert reranker_runtime.reranker_runtime_dir(repo_root) == reranker_runtime.reranker_shared_runtime_dir(repo_root)


def test_reranker_runtime_dir_honors_explicit_override(monkeypatch, tmp_path: Path) -> None:
    """An explicit runtime-root override should still win for isolated tests."""
    monkeypatch.setenv("SPECKIT_READ_CODE_RERANKER_RUNTIME_ROOT", str(tmp_path / "runtime-root"))
    repo_root = Path("/tmp/example-repo")

    assert reranker_runtime.reranker_runtime_dir(repo_root) == (
        (tmp_path / "runtime-root").resolve() / reranker_runtime._repo_runtime_slug(repo_root)
    )


def test_reranker_socket_path_keeps_the_literal_tmp_prefix() -> None:
    """The socket path should stay on /tmp without resolving to a longer host-specific path."""
    repo_root = Path("/tmp/example-repo")

    assert str(reranker_runtime.reranker_socket_path(repo_root)).startswith("/tmp/appf-rcd-")
