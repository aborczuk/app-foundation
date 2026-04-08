"""Unit tests for `csp_trader.cgc_guard` safety enforcement."""

from __future__ import annotations

from pathlib import Path

from csp_trader.cgc_guard import CgcGuardError, enforce_cgc_guard


def _assert_guard_error(expected_fragment: str, fn) -> None:
    try:
        fn()
    except CgcGuardError as exc:
        assert expected_fragment in str(exc)
        return
    raise AssertionError("Expected CgcGuardError was not raised")


def test_blocks_force_without_opt_in(tmp_path: Path) -> None:
    """Force indexing requires explicit opt-in."""
    def _call() -> None:
        enforce_cgc_guard(
            ["index", "--force", "src/clickup_control_plane"],
            env={},
            root=tmp_path,
        )
    _assert_guard_error("Refusing forced index", _call)


def test_allows_force_with_opt_in_for_scoped_path(tmp_path: Path) -> None:
    """Scoped forced index is allowed when opt-in is present."""
    enforce_cgc_guard(
        ["index", "--force", "src/clickup_control_plane"],
        env={"CGC_ALLOW_FORCE": "1"},
        root=tmp_path,
    )


def test_blocks_forced_full_repo_even_with_opt_in(tmp_path: Path) -> None:
    """Forced full-repo index is always blocked."""
    def _call() -> None:
        enforce_cgc_guard(
            ["index", "--force", "."],
            env={"CGC_ALLOW_FORCE": "1", "CGC_ALLOW_REPO_INDEX": "1"},
            root=tmp_path,
        )
    _assert_guard_error("full-repo force re-index", _call)


def test_blocks_default_full_repo_index_without_opt_in(tmp_path: Path) -> None:
    """Default full-repo index should require explicit opt-in."""
    def _call() -> None:
        enforce_cgc_guard(
            ["index", "."],
            env={},
            root=tmp_path,
        )
    _assert_guard_error("default full-repo index target", _call)


def test_allows_default_full_repo_index_with_opt_in(tmp_path: Path) -> None:
    """Intentional full-repo non-force index is allowed with explicit opt-in."""
    enforce_cgc_guard(
        ["index", "."],
        env={"CGC_ALLOW_REPO_INDEX": "1"},
        root=tmp_path,
    )


def test_non_index_commands_are_not_blocked(tmp_path: Path) -> None:
    """Read-only commands should bypass index safety policy."""
    enforce_cgc_guard(
        ["find", "pattern", "foo"],
        env={},
        root=tmp_path,
    )
