from __future__ import annotations

from pathlib import Path

import scripts.specify_fastpath as fastpath


def test_extract_terms_filters_generic_words() -> None:
    """Discovery terms should keep signal and skip generic filler words."""
    assert fastpath._extract_terms("Build a playable Tetris game in the app.") == ["tetris"]


def test_main_runs_discovery_before_scaffold(monkeypatch, tmp_path: Path, capsys) -> None:
    """The fast path should discover code before it scaffolds the checklist."""
    calls: list[str] = []

    monkeypatch.setattr(fastpath, "_build_uv_env", lambda: {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")})
    monkeypatch.setattr(fastpath, "_extract_terms", lambda _description: ["tetris"])

    def _run_discovery(terms: list[str], env: dict[str, str]) -> list[dict[str, object]]:
        calls.append(f"discover:{terms[0]}:{env['UV_CACHE_DIR']}")
        return [
            {
                "term": terms[0],
                "returncode": 0,
                "stdout": "No content matches found for 'tetris'",
                "stderr": "",
                "has_matches": False,
            }
        ]

    def _create_feature(description: str, short_name: str, env: dict[str, str]) -> dict[str, str]:
        calls.append(f"create:{short_name}:{env['UV_CACHE_DIR']}")
        return {
            "BRANCH_NAME": "028-tetris-game",
            "FEATURE_NUM": "028",
            "SPEC_FILE": str(tmp_path / "specs" / "028-tetris-game" / "spec.md"),
        }

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _scaffold_checklist(feature_dir: Path, feature_name: str, env: dict[str, str]) -> _Result:
        calls.append(f"scaffold:{feature_name}:{env['UV_CACHE_DIR']}")
        return _Result()

    monkeypatch.setattr(fastpath, "_run_discovery", _run_discovery)
    monkeypatch.setattr(fastpath, "_create_feature", _create_feature)
    monkeypatch.setattr(fastpath, "_scaffold_checklist", _scaffold_checklist)

    exit_code = fastpath.main(["--short-name", "tetris-game", "Build a playable Tetris game in the app."])
    capsys.readouterr()

    assert exit_code == 0
    assert calls == [
        f"discover:tetris:{tmp_path / '.uv-cache'}",
        f"create:tetris-game:{tmp_path / '.uv-cache'}",
        f"scaffold:Tetris Game:{tmp_path / '.uv-cache'}",
    ]
