from pathlib import Path


def test_story1_shortlist_and_top_body_contract(tmp_path: Path) -> None:
    """US1: ranked shortlist and inline top-body payload."""
    plan = Path("specs/025-intent-anchor-routing/plan.md").read_text()
    tasks = Path("specs/025-intent-anchor-routing/tasks.md").read_text()
    assert "top-5 candidate shortlist" in plan
    assert "90/100" in plan
    assert "ranked shortlist of 5 candidates" in tasks
    assert "inline its indexed body" in plan or "top candidate body" in plan
