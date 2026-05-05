from __future__ import annotations

import subprocess
from pathlib import Path

import scripts.speckit_research_step as research_step


def test_extract_terms_filters_generic_words() -> None:
    """Discovery terms should keep signal and skip generic filler words."""
    assert research_step._extract_terms("Build a playable Tetris game in the app.") == ["tetris"]


def test_run_discovery_uses_semantic_context_lookup(monkeypatch, tmp_path: Path) -> None:
    """Discovery should call the semantic read helper, not a structural content search."""
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run_uv_command(args: list[str], *, env: dict[str, str]):
        calls.append((tuple(args), env))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="file_path: /repo/item.py", stderr="")

    monkeypatch.setattr(research_step, "_run_uv_command", fake_run_uv_command)

    results = research_step._run_discovery(["tetris"], {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")})

    assert len(calls) == 1
    assert calls[0][0][-3:] == ("scripts/read_code.py", "context", "tetris")
    assert results[0]["has_matches"] is True
