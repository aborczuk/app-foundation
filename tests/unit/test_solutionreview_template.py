from __future__ import annotations

from pathlib import Path


def test_solutionreview_template_matches_solutionreview_playbook() -> None:
    """Ensure the solution-review scaffold mirrors the playbook steps and review outputs."""
    template_path = Path(".specify/templates/solutionreview-template.md")
    template = template_path.read_text(encoding="utf-8")

    required_headings = [
        "## 1. Setup",
        "## 2. Gate checks",
        "## 3. Load review context",
        "### CodeGraphContext Findings",
        "## 4. Hard completeness check on sketch structure",
        "## 5. Spec-to-sketch traceability review (mandatory)",
        "## 6. Plan-to-sketch fidelity review (mandatory)",
        "## 7. Solution narrative and construction strategy review (mandatory)",
        "## 8. Repo grounding and touched-surface review (mandatory)",
        "## 9. Command / script / manifest review (mandatory)",
        "## 10. Symbol strategy and interface review (mandatory)",
        "## 11. Reuse strategy review (mandatory)",
        "## 12. Blast-radius and risk-surface review (mandatory)",
        "## 13. State / lifecycle / failure model review (mandatory)",
        "## 14. Human-task and operator-boundary review (mandatory)",
        "## 15. Verification-strategy review (mandatory)",
        "## 16. Domain guardrail review (mandatory)",
        "## 17. Design-to-tasking contract review (mandatory)",
        "## 17b. Narrative and reuse gate rubric (mandatory)",
        "## 18. Cross-slice DRY and coherence review (mandatory)",
        "## 19. Write `solutionreview.md`",
        "## 20. Emit pipeline event",
        "## 21. Decision rule",
        "## 22. Report",
        "## Artifact Scaffolding (Phase 5)",
        "## Behavior rules",
    ]

    last_index = -1
    for heading in required_headings:
        index = template.index(heading)
        assert index > last_index
        last_index = index

    assert "codegraph-grounding" in template
    assert "HUDs / exact symbols reviewed" in template
    assert "exact symbol/HUD references where applicable" in template
