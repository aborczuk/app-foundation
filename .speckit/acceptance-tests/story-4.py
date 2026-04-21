from pathlib import Path


def test_story4_shell_help_mentions_shortlist_contract(tmp_path: Path) -> None:
    """Cross-cutting regression: shell wrapper guidance stays aligned."""
    shell_help = Path("scripts/read-code.sh").read_text()
    assert "read_code_context" in shell_help
    assert "read_code_window" in shell_help
    assert "shortlist" in shell_help or "window" in shell_help
