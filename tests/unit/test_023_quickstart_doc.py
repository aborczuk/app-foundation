"""Quickstart documentation regression tests for feature 023."""

from __future__ import annotations

from pathlib import Path


def test_023_quickstart_doc_describes_producer_only_handoff() -> None:
    """The quickstart should describe solution ownership as producer-only and driver-recorded."""
    quickstart_path = (
        Path(__file__).resolve().parents[2]
        / "specs"
        / "023-deterministic-phase-orchestration"
        / "quickstart.md"
    )
    quickstart_text = quickstart_path.read_text(encoding="utf-8")

    assert "producer-vs-driver ownership boundary" in quickstart_text
    assert "the pipeline driver records the event after the payload is accepted." in quickstart_text
    assert "Do not hand-write `.speckit/pipeline-ledger.jsonl`" in quickstart_text
