from __future__ import annotations

import json
from pathlib import Path

import scripts.speckit_specify_step as specify_step


def test_main_bootstraps_scaffold_without_handoff(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """The fast path should bootstrap the scaffold and stop before handoff."""
    calls: list[str] = []

    monkeypatch.setattr(
        specify_step,
        "_build_uv_env",
        lambda: {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")},
    )

    def _create_feature(
        description: str, short_name: str, env: dict[str, str]
    ) -> dict[str, str]:
        calls.append(f"create:{short_name}:{env['UV_CACHE_DIR']}")
        feature_dir = tmp_path / "specs" / "028-tetris-game"
        feature_dir.mkdir(parents=True, exist_ok=True)
        spec_path = feature_dir / "spec.md"
        spec_path.write_text(
            "\n".join(
                [
                    "# Feature Specification: [FEATURE NAME]",
                    "",
                    "**Feature Branch**: `[###-feature-name]`",
                    "**Created**: [DATE]",
                    "**Status**: Draft",
                    '**Input**: User description: "$ARGUMENTS"',
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "BRANCH_NAME": "028-tetris-game",
            "FEATURE_NUM": "028",
            "SPEC_FILE": str(spec_path),
        }

    def _run_step_mode(**_kwargs):  # noqa: ANN001
        raise AssertionError("handoff should not run during bootstrap-only specify")

    monkeypatch.setattr(specify_step, "_create_feature", _create_feature)
    monkeypatch.setattr(specify_step, "_run_step_mode", _run_step_mode)

    exit_code = specify_step.main(
        ["--short-name", "tetris-game", "Build a playable Tetris game in the app."]
    )
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert calls == [f"create:tetris-game:{tmp_path / '.uv-cache'}"]
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["branch_name"] == "028-tetris-game"
    assert payload["feature_num"] == "028"
    assert payload["spec_file"] == str(tmp_path / "specs" / "028-tetris-game" / "spec.md")
    assert payload["generated_artifact"]["path"] == str(
        tmp_path / "specs" / "028-tetris-game" / "spec.md"
    )
    assert payload["next_step"] == "fill_spec_scaffold"


def test_main_bootstraps_with_short_name_only(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Bootstrap-only specify should still create a scaffold when only the short name is present."""
    calls: list[str] = []

    monkeypatch.setattr(
        specify_step,
        "_build_uv_env",
        lambda: {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")},
    )

    feature_dir = tmp_path / "specs" / "032-make-tetris"
    feature_dir.mkdir(parents=True, exist_ok=True)
    spec_file = feature_dir / "spec.md"

    def _create_feature(
        description: str, short_name: str, env: dict[str, str]
    ) -> dict[str, str]:
        calls.append(f"create:{short_name}:{env['UV_CACHE_DIR']}")
        spec_file.write_text(
            "\n".join(
                [
                    "# Feature Specification: Tetris",
                    "",
                    "**Feature Branch**: `[032-make-tetris]`",
                    "**Created**: [DATE]",
                    "**Status**: Draft",
                    '**Input**: User description: "make tetris"',
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "BRANCH_NAME": "032-make-tetris",
            "FEATURE_NUM": "032",
            "SPEC_FILE": str(spec_file),
        }

    def _run_step_mode(**_kwargs):  # noqa: ANN001
        raise AssertionError("handoff should not run during bootstrap-only specify")

    monkeypatch.setattr(specify_step, "_create_feature", _create_feature)
    monkeypatch.setattr(specify_step, "_run_step_mode", _run_step_mode)

    exit_code = specify_step.main(
        [
            "make tetris",
            "--short-name",
            "make-tetris",
        ]
    )
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert calls == [f"create:make-tetris:{tmp_path / '.uv-cache'}"]
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["branch_name"] == "032-make-tetris"
    assert payload["feature_num"] == "032"
    assert payload["feature_id"] == "032-make-tetris"
    assert payload["spec_file"] == str(spec_file)
    assert payload["generated_artifact"]["path"] == str(spec_file)
    assert payload["next_step"] == "fill_spec_scaffold"
