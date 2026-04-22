from pathlib import Path


def test_story3_agent_rules_documentation_contract(tmp_path: Path) -> None:
    """US3: agent-facing documentation for read-code rules."""
    agents = Path("AGENTS.md").read_text()
    quickstart = Path("specs/025-intent-anchor-routing/quickstart.md").read_text()
    assert "read-code rules" in agents
    assert "top-5" in agents
    assert "90/100" in agents
    assert "shortlist" in quickstart
    assert "follow-up" in quickstart
