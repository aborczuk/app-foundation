from __future__ import annotations

import json
import subprocess
from pathlib import Path

import scripts.speckit_plan_step as plan_step


def _write_feature(tmp_path: Path) -> Path:
    """Create a minimal feature directory for plan-step tests."""
    feature_dir = tmp_path / "specs" / "123-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(
        "# Feature\n\nBuild a playable Tetris game in the app.\n",
        encoding="utf-8",
    )
    return feature_dir


def _write_contract(plan_file: Path, *, duplicate: bool) -> None:
    """Write a combined plan contract into plan.md."""
    plan_file.write_text(
        "\n".join(
            [
                "# Combined Plan",
                "",
                "## Triage",
                "",
                f"- duplicate: {str(duplicate).lower()}",
                "",
                "## Routing Contract",
                "",
                "```json",
                json.dumps(
                    {
                        "triage": {
                            "duplicate": duplicate,
                            "duplicate_reason": "Existing feature covers this." if duplicate else "",
                            "duplicate_matches": ["specs/001-existing/spec.md"] if duplicate else [],
                            "risk_level": "low",
                            "tshirt_size": "xs" if duplicate else "s",
                        },
                        "routing": {
                            "architecture_diagram": False,
                            "external_research": False,
                            "plan_level": "simple",
                            "routing_reason": "Small repo-local change.",
                            "sketch_level": "core",
                        },
                        "risk": {
                            "requirement_clarity": "low",
                            "repo_uncertainty": "low",
                            "external_dependency_uncertainty": "low",
                            "state_data_migration_risk": "low",
                            "runtime_side_effect_risk": "low",
                            "human_operator_dependency": "low",
                        },
                    },
                    sort_keys=True,
                ),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_extract_terms_filters_generic_words() -> None:
    """Discovery terms should keep signal and skip generic filler words."""
    assert plan_step._extract_terms("Build a playable Tetris game in the app.") == ["tetris"]


def test_run_discovery_uses_semantic_context_lookup(monkeypatch, tmp_path: Path) -> None:
    """Discovery should call the semantic read helper, not a structural content search."""
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = []

    def fake_run_uv_command(args: list[str], *, env: dict[str, str]):
        calls.append((tuple(args), env))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="file_path: /repo/item.py", stderr="")

    monkeypatch.setattr(plan_step, "_run_uv_command", fake_run_uv_command)

    results = plan_step._run_discovery(["tetris"], {"UV_CACHE_DIR": str(tmp_path / ".uv-cache")})

    assert len(calls) == 1
    assert calls[0][0][-3:] == ("scripts/read_code.py", "context", "tetris")
    assert results[0]["has_matches"] is True


def test_triage_instructions_require_generative_tshirt_logic() -> None:
    """The prompt should force LOE judgment to be generative, not count-based."""
    prompt = plan_step._build_triage_instructions(
        "# Spec",
        [{"term": "tetris", "has_matches": True, "stdout": "file_path: x.py", "stderr": ""}],
    )

    assert "Do not infer t-shirt size from the number of discovery matches." in prompt
    assert "likely blast radius, risk, and uncertainty" in prompt


def test_orchestrate_plan_marks_duplicate_without_fill(monkeypatch, tmp_path: Path) -> None:
    """A duplicate triage should request duplicate_marked and skip design filling."""
    feature_dir = _write_feature(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(plan_step, "DEFAULT_SCAFFOLD", tmp_path / ".specify/scripts/pipeline-scaffold.py")
    monkeypatch.setattr(plan_step, "bootstrap_session", lambda _: {"bootstrap_ok": True})
    monkeypatch.setattr(plan_step, "_build_uv_env", lambda: {})
    monkeypatch.setattr(
        plan_step,
        "_run_discovery",
        lambda terms, env: [{"term": "tetris", "has_matches": True, "stdout": "file_path: specs/001-existing/spec.md", "stderr": ""}],
    )
    monkeypatch.setattr(plan_step, "_scaffold_manifest_plan", lambda feature_dir: None)

    def fake_codex_action(**kwargs):
        calls.append(kwargs["task_action"])
        _write_contract(feature_dir / "plan.md", duplicate=True)
        return {"ok": True}

    monkeypatch.setattr(plan_step, "_run_codex_action", fake_codex_action)

    result = plan_step.orchestrate_plan("123", "corr", phase="plan")

    assert calls == ["triage_combined_plan"]
    assert result["next_phase"] == "closed"
    assert result["pipeline_event_request"]["event"] == "duplicate_marked"
    assert result["triage"]["duplicate"] is True


def test_orchestrate_plan_fills_nonduplicate_design_slice(monkeypatch, tmp_path: Path) -> None:
    """A non-duplicate triage should scaffold selected sections and request plan approval."""
    feature_dir = _write_feature(tmp_path)
    calls: list[str] = []

    monkeypatch.setattr(plan_step, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(plan_step, "DEFAULT_SCAFFOLD", tmp_path / ".specify/scripts/pipeline-scaffold.py")
    monkeypatch.setattr(plan_step, "bootstrap_session", lambda _: {"bootstrap_ok": True})
    monkeypatch.setattr(plan_step, "_build_uv_env", lambda: {})
    monkeypatch.setattr(
        plan_step,
        "_run_discovery",
        lambda terms, env: [{"term": "tetris", "has_matches": True, "stdout": "file_path: src/game.py", "stderr": ""}],
    )
    monkeypatch.setattr(plan_step, "_scaffold_manifest_plan", lambda feature_dir: None)

    def fake_codex_action(**kwargs):
        calls.append(kwargs["task_action"])
        plan_file = feature_dir / "plan.md"
        if kwargs["task_action"] == "triage_combined_plan":
            _write_contract(plan_file, duplicate=False)
        else:
            text = plan_file.read_text(encoding="utf-8")
            plan_file.write_text(
                text.replace(
                    "[Fill this section from the spec, discovery, and triage contract.]",
                    "Slice PL-01\n\nEstimated LOE: low\n\nImplementation Directive: edit src/game.py.",
                ),
                encoding="utf-8",
            )
        return {"ok": True}

    monkeypatch.setattr(plan_step, "_run_codex_action", fake_codex_action)

    result = plan_step.orchestrate_plan("123", "corr", phase="plan")

    assert calls == ["triage_combined_plan", "fill_combined_plan"]
    assert result["next_phase"] == "solution"
    assert result["pipeline_event_request"]["event"] == "plan_approved"
    assert result["pipeline_event_request"]["fields"]["feasibility_required"] is False
    assert "## Design Slices" in (feature_dir / "plan.md").read_text(encoding="utf-8")
