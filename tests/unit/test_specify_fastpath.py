from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts.speckit_specify_step as specify_step

fastpath = specify_step


def test_extract_terms_filters_generic_words() -> None:
    """Discovery terms should keep signal and skip generic filler words."""
    assert fastpath._extract_terms("Build a playable Tetris game in the app.") == ["tetris"]


def test_run_discovery_uses_semantic_context_lookup(monkeypatch, tmp_path: Path) -> None:
    """Discovery should call the semantic read helper, not a structural content search."""
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run_uv_command(args: list[str], *, env: dict[str, str]):
        calls.append((tuple(args), env))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="file_path: /repo/item.py", stderr="")

    monkeypatch.setattr(fastpath, "_run_uv_command", fake_run_uv_command)

    results = fastpath._run_discovery(["tetris"], {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")})

    assert len(calls) == 1
    assert calls[0][0] == ("python3", "scripts/read_code.py", "context", "tetris")
    assert results[0]["has_matches"] is True


def test_main_bootstraps_then_runs_deterministic_step(monkeypatch, tmp_path: Path, capsys) -> None:
    """The fast path should bootstrap the scaffold and then continue into step mode."""
    calls: list[str] = []

    monkeypatch.setattr(
        specify_step,
        "_build_uv_env",
        lambda: {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")},
    )

    def _create_feature(description: str, short_name: str, env: dict[str, str]) -> dict[str, str]:
        calls.append(f"create:{short_name}:{env['UV_CACHE_DIR']}")
        feature_dir = tmp_path / "specs" / "028-tetris-game"
        feature_dir.mkdir(parents=True, exist_ok=True)
        (feature_dir / "spec.md").write_text(
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
            "SPEC_FILE": str(feature_dir / "spec.md"),
        }

    def _run_step_mode(
        *,
        feature_id: str,
        phase: str,
        correlation_id: str,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(
            "step:"
            f"{feature_id}:{phase}:{correlation_id}:{timeout_seconds}:"
            f"{env['UV_CACHE_DIR']}:{env['FEATURE_DIR']}:{env['FEATURE_SPEC']}"
        )
        assert env["FEATURE_DIR"] == str(tmp_path / "specs" / "028-tetris-game")
        assert env["FEATURE_SPEC"] == str(tmp_path / "specs" / "028-tetris-game" / "spec.md")
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "feature_id": feature_id,
            "correlation_id": correlation_id,
            "next_phase": "plan",
            "generated_artifact": {
                "path": str(tmp_path / "specs" / "028-tetris-game" / "spec.md"),
                "completion_marker": "## Routing Contract",
            },
        }

    monkeypatch.setattr(specify_step, "_create_feature", _create_feature)
    monkeypatch.setattr(specify_step, "_run_step_mode", _run_step_mode)

    exit_code = specify_step.main(["--short-name", "tetris-game", "Build a playable Tetris game in the app."])
    capsys.readouterr()

    assert exit_code == 0
    assert calls[0] == f"create:tetris-game:{tmp_path / '.uv-cache'}"
    assert calls[1].startswith("step:028:specify:")
    assert not (tmp_path / "specs" / "028-tetris-game" / "discovery.md").exists()
    assert '**Input**: User description: "Build a playable Tetris game in the app."' in (
        tmp_path / "specs" / "028-tetris-game" / "spec.md"
    ).read_text(encoding="utf-8")


def test_main_step_mode_retries_after_validation_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    """The deterministic specify loop should hand validation failures back to the runner."""
    feature_dir = tmp_path / "specs" / "032-make-tetris"
    feature_dir.mkdir(parents=True)
    spec_file = feature_dir / "spec.md"
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
    discovery_file = feature_dir / "discovery.md"
    discovery_file.write_text("# Discovery\n", encoding="utf-8")

    monkeypatch.setattr(
        specify_step,
        "_load_feature_paths",
        lambda _env: {
            "FEATURE_DIR": str(feature_dir),
            "FEATURE_SPEC": str(spec_file),
        },
    )

    calls: list[str] = []
    handoff_results = [
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "run-test:speckit.specify",
            "next_phase": "research",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": str(spec_file),
                "completion_marker": "## Routing Contract",
            },
        },
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "run-test:speckit.specify",
            "next_phase": "research",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": str(spec_file),
                "completion_marker": "## Routing Contract",
            },
        },
    ]
    validation_results = [
        {
            "mode": "validate_routing",
            "spec_file": str(spec_file),
            "routing": None,
            "risk": None,
            "reasons": ["missing_routing_contract"],
            "ok": False,
            "process_exit_code": 2,
            "stdout": "{}",
            "stderr": "",
        },
        {
            "mode": "validate_routing",
            "spec_file": str(spec_file),
            "routing": {
                "research_route": "skip",
                "plan_profile": "full",
                "sketch_profile": "core",
                "tasking_route": "required",
                "estimate_route": "required_after_tasking",
                "routing_reason": "good enough",
                "conditional_sketch_sections": [],
            },
            "risk": {
                "requirement_clarity": "low",
                "repo_uncertainty": "low",
                "external_dependency_uncertainty": "low",
                "state_data_migration_risk": "low",
                "runtime_side_effect_risk": "low",
                "human_operator_dependency": "low",
            },
            "reasons": [],
            "ok": True,
            "process_exit_code": 0,
            "stdout": "{}",
            "stderr": "",
        },
    ]

    def _run_handoff_round(**kwargs):  # noqa: ANN001
        calls.append("handoff")
        return handoff_results.pop(0)

    def _validate_spec_routing(_spec_file: Path, _env: dict[str, str]):
        calls.append("validate")
        return validation_results.pop(0)

    monkeypatch.setattr(specify_step, "_run_specify_handoff_round", _run_handoff_round)
    monkeypatch.setattr(specify_step, "_validate_spec_routing", _validate_spec_routing)

    exit_code = specify_step.main(
        [
            "make tetris",
            "--feature-id",
            "032-make-tetris",
            "--phase",
            "specify",
            "--correlation-id",
            "run-test:speckit.specify",
        ]
    )
    payload = json.loads(capsys.readouterr().out.strip())

    assert exit_code == 0
    assert calls == ["handoff", "validate", "handoff", "validate"]
    assert payload["ok"] is True
    assert payload["next_phase"] == "plan"
    assert payload["generated_artifact"]["path"] == str(spec_file)
