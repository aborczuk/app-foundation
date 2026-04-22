"""Smoke tests for the speckit analyze command doc and manifest artifact contract."""

from __future__ import annotations

from pathlib import Path


def test_speckit_analyze_doc_mentions_traceable_analysis_artifact() -> None:
    """Keep the analyze command aligned to the traceable analysis.md artifact."""
    doc_path = Path(__file__).resolve().parents[2] / ".claude" / "commands" / "speckit.analyze.md"
    manifest_path = Path(__file__).resolve().parents[2] / "command-manifest.yaml"
    template_path = Path(__file__).resolve().parents[2] / ".specify" / "templates" / "analysis-template.md"

    doc_text = doc_path.read_text(encoding="utf-8")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    template_text = template_path.read_text(encoding="utf-8")

    assert "FEATURE_DIR/analysis.md" in doc_text
    assert "pipeline-scaffold.py" in doc_text
    assert "STRICTLY READ-ONLY" in doc_text
    assert "do **not** modify spec.md, plan.md, tasks.md, or code" in doc_text
    assert "analysis-template.md" in doc_text
    assert "analysis.md" in manifest_text
    assert "${FEATURE_DIR}/analysis.md" in manifest_text
    assert "pipeline-scaffold.py" in manifest_text
    assert "analysis-template.md" in manifest_text
    assert "Specification Analysis Report" in template_text
