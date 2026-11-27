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


def test_main_dispatches_driver_route_to_existing_feature(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """The driver arguments must invoke step mode with its selected feature."""
    observed: dict[str, object] = {}
    monkeypatch.setattr(specify_step, "_build_uv_env", lambda: {"UV_CACHE_DIR": str(tmp_path)})

    def _run_step_mode(**kwargs):  # noqa: ANN001
        observed.update(kwargs)
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": kwargs["correlation_id"],
            "phase": "specify",
            "feature_id": kwargs["feature_id"],
            "next_phase": "clarify",
        }

    monkeypatch.setattr(specify_step, "_run_step_mode", _run_step_mode)

    exit_code = specify_step.main(
        [
            "--feature-id",
            "055-agent-analytics-otel",
            "--phase",
            "specify",
            "--correlation-id",
            "run-055:speckit.specify",
        ]
    )
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert observed == {
        "feature_id": "055-agent-analytics-otel",
        "phase": "specify",
        "correlation_id": "run-055:speckit.specify",
        "env": {"UV_CACHE_DIR": str(tmp_path)},
        "timeout_seconds": 300,
    }
    assert payload["feature_id"] == "055-agent-analytics-otel"
    assert payload["next_phase"] == "clarify"


def test_step_mode_requests_backlog_event_after_success(
    monkeypatch, tmp_path: Path
) -> None:
    """A validated spec.md must pass without any subrunner and request backlog registration."""
    feature_dir = tmp_path / "specs" / "060-consolidate-edit-validation"
    feature_dir.mkdir(parents=True)
    spec_file = feature_dir / "spec.md"
    spec_file.write_text(
        "\n".join(
            [
                "# Feature Specification: Consolidate Edit Validation",
                "",
                "**Feature Branch**: `060-consolidate-edit-validation`",
                "**Created**: 2026-11-27",
                "**Status**: Draft",
                "",
                "## One-Line Purpose *(mandatory)*",
                "",
                "Maintainers run one deterministic validation flow per edit batch.",
                "",
                "## Definition of Done *(mandatory)*",
                "",
                "Shipped when validation runs once per edit batch in production.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        specify_step,
        "_load_feature_paths",
        lambda _env, *, feature_id: {
            "FEATURE_DIR": str(feature_dir),
            "FEATURE_SPEC": str(spec_file),
        },
    )

    result = specify_step._run_step_mode(
        feature_id="060",
        phase="specify",
        correlation_id="run-060:speckit.specify",
        env={},
        timeout_seconds=300,
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["next_phase"] == "plan"
    assert result["pipeline_event_request"] == {
        "event": "backlog_registered",
        "fields": {},
    }


def test_step_mode_blocks_unfilled_template_without_event(
    monkeypatch, tmp_path: Path
) -> None:
    """An unfilled spec template must block validation and emit no backlog event."""
    feature_dir = tmp_path / "specs" / "060-consolidate-edit-validation"
    feature_dir.mkdir(parents=True)
    spec_file = feature_dir / "spec.md"
    spec_file.write_text(
        "\n".join(
            [
                "# Feature Specification: [FEATURE NAME]",
                "",
                "**Feature Branch**: `[###-feature-name]`",
                "**Created**: [DATE]",
                "",
                "## Definition of Done *(mandatory)*",
                "",
                "[Single sentence: observable state in production that means this feature is shipped]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        specify_step,
        "_load_feature_paths",
        lambda _env, *, feature_id: {
            "FEATURE_DIR": str(feature_dir),
            "FEATURE_SPEC": str(spec_file),
        },
    )

    result = specify_step._run_step_mode(
        feature_id="060",
        phase="specify",
        correlation_id="run-060:speckit.specify",
        env={},
        timeout_seconds=300,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["gate"] == "spec_validation"
    assert "spec_has_template_placeholders" in result["reasons"]
    assert result["next_phase"] == "specify"
    assert "pipeline_event_request" not in result


def test_step_mode_blocks_excess_clarifications_without_event(
    monkeypatch, tmp_path: Path
) -> None:
    """More than three clarification markers must block specify completion."""
    feature_dir = tmp_path / "specs" / "060-consolidate-edit-validation"
    feature_dir.mkdir(parents=True)
    spec_file = feature_dir / "spec.md"
    spec_file.write_text(
        "\n".join(
            [
                "# Feature Specification: Consolidate Edit Validation",
                "",
                "- [NEEDS CLARIFICATION: one]",
                "- [NEEDS CLARIFICATION: two]",
                "- [NEEDS CLARIFICATION: three]",
                "- [NEEDS CLARIFICATION: four]",
                "",
                "## Definition of Done *(mandatory)*",
                "",
                "Shipped when validation runs once per edit batch in production.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        specify_step,
        "_load_feature_paths",
        lambda _env, *, feature_id: {
            "FEATURE_DIR": str(feature_dir),
            "FEATURE_SPEC": str(spec_file),
        },
    )

    result = specify_step._run_step_mode(
        feature_id="060",
        phase="specify",
        correlation_id="run-060:speckit.specify",
        env={},
        timeout_seconds=300,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["gate"] == "spec_validation"
    assert "too_many_clarifications" in result["reasons"]
    assert "pipeline_event_request" not in result


def test_explicit_feature_paths_ignore_checkout_environment(monkeypatch, tmp_path: Path) -> None:
    """An explicit driver feature must take precedence over checkout-derived paths."""
    feature_dir = tmp_path / "specs" / "055-agent-analytics-otel"
    feature_dir.mkdir(parents=True)
    spec_file = feature_dir / "spec.md"
    spec_file.write_text("# Agent analytics\n", encoding="utf-8")
    monkeypatch.setattr(specify_step, "_resolve_feature_dir", lambda _feature_id: feature_dir)

    paths = specify_step._load_feature_paths(
        {"FEATURE_DIR": "/wrong-feature", "FEATURE_SPEC": "/wrong-feature/spec.md"},
        feature_id="055",
    )

    assert paths == {"FEATURE_DIR": str(feature_dir), "FEATURE_SPEC": str(spec_file)}


def test_driver_run_step_validates_specify_subprocess_without_subrunner() -> None:
    """pipeline_driver.run_step must execute speckit_specify_step.py live and preserve event request."""
    import sys

    import scripts.pipeline_driver as pipeline_driver

    result = pipeline_driver.run_step(
        [
            sys.executable,
            str(Path(specify_step.__file__).resolve()),
            "--feature-id",
            "049-financial-acceleration-tracker",
            "--phase",
            "specify",
            "--correlation-id",
            "run-049:speckit.specify",
        ],
        timeout_seconds=30,
        correlation_id="run-049:speckit.specify",
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["next_phase"] == "plan"
    assert result["pipeline_event_request"] == {
        "event": "backlog_registered",
        "fields": {},
    }
