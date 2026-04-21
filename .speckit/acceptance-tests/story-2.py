from pathlib import Path


def test_story2_follow_up_body_helper_contract(tmp_path: Path) -> None:
    """US2: bounded non-top candidate body follow-up."""
    plan = Path("specs/025-intent-anchor-routing/plan.md").read_text()
    tasks = Path("specs/025-intent-anchor-routing/tasks.md").read_text()
    assert "follow-up body helper" in plan
    assert "bounded follow-up helper" in tasks
    assert "shortlist candidate" in plan
    assert "non-top" in tasks
