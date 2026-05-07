"""Unit tests for scripts/speckit_solution_step.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    """Load a script module from the repo's scripts directory."""
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


speckit_solution_step = _load_script_module("speckit_solution_step", "speckit_solution_step.py")


def test_prepare_tasking_scaffolds_tasks_from_plan(tmp_path: Path, monkeypatch) -> None:
    """The scaffold helper should validate plan slices and seed tasks.md from the template."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    plan_path = feature_dir / "plan.md"
    plan_path.write_text(
        "\n".join(
            [
                "# Plan",
                "",
                "## Design Slices",
                "",
                "### PL-01 Runtime Surface",
                "",
                "Implementation Directive: Add runtime route.",
                "",
                "### PL-02 Browser Shell",
                "",
                "Implementation Directive: Build browser UI seam.",
            ]
        ),
        encoding="utf-8",
    )
    template_path = repo_root / ".specify" / "templates" / "tasks-template.md"
    template_path.parent.mkdir(parents=True)
    template_path.write_text(
        "# Tasks: [FEATURE NAME]\n\n**Input**: Design documents from `/specs/[###-feature-name]/`\n",
        encoding="utf-8",
    )
    (feature_dir / "routing.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(speckit_solution_step, "DEFAULT_TASKS_TEMPLATE", template_path)
    monkeypatch.setattr(
        speckit_solution_step,
        "_resolve_solution_paths",
        lambda feature_id: (repo_root, feature_dir, plan_path),
    )

    result = speckit_solution_step.prepare_tasking("023")

    assert result["ok"] is True
    assert result["routing_artifact"] == str(feature_dir / "routing.json")
    tasks_text = (feature_dir / "tasks.md").read_text(encoding="utf-8")
    assert "# Tasks: deterministic phase orchestration" in tasks_text
    assert "/specs/023-deterministic-phase-orchestration/" in tasks_text
    assert "## Plan Design Slice Index" in tasks_text
    assert "- PL-01 Runtime Surface" in tasks_text
    assert "- PL-02 Browser Shell" in tasks_text


def test_finalize_solution_runs_stabilization_and_emits_event_request(
    tmp_path: Path, monkeypatch
) -> None:
    """Finalize should run deterministic post-processing and return one driver event request."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    plan_path = feature_dir / "plan.md"
    plan_path.write_text(
        "\n".join(
            [
                "# Plan",
                "",
                "## Design Slices",
                "",
                "### PL-01 Runtime Surface",
                "",
                "Implementation Directive: Add runtime route.",
            ]
        ),
        encoding="utf-8",
    )
    tasks_path = feature_dir / "tasks.md"
    tasks_path.write_text(
        "\n".join(
            [
                "# Tasks",
                "",
                "## User Story 1",
                "",
                "- [ ] T001 Build runtime route in src/app.py",
                "- [ ] T002 Add browser page in src/ui.py",
            ]
        ),
        encoding="utf-8",
    )
    (feature_dir / "estimates.md").write_text("**Total Points**: 13\n", encoding="utf-8")
    (feature_dir / "routing.json").write_text(
        '{"routing":{"plan_level":"simple"},"triage":{"tshirt_size":"s"},"risk":{"overall":"low"},"domains":{"relevant":["testing"],"reasoning":{}},"strategy":{"architecture_strategy":false},"design_slices":[]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        speckit_solution_step,
        "bootstrap_session",
        lambda _repo_root: {"bootstrap_ok": True},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_resolve_solution_paths",
        lambda feature_id: (repo_root, feature_dir, plan_path),
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_runtime_result_path",
        lambda phase, correlation_id: repo_root / ".speckit" / "runtime" / phase / f"{correlation_id}.json",
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_run_tasking_stabilization",
        lambda **kwargs: {"ok": True, "stabilized": True},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_run_tasks_gate",
        lambda **kwargs: {"ok": True, "gate": "passed"},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_register_tasks",
        lambda **kwargs: {"ok": True, "registered": 2},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_validate_huds",
        lambda **kwargs: {"ok": True, "error_count": 0, "errors": []},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_generate_acceptance_tests",
        lambda **kwargs: {"stdout": "acceptance", "stderr": ""},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "parse_task_definitions",
        lambda path: [{"id": "T001"}, {"id": "T002"}],
    )

    result = speckit_solution_step.finalize_solution(
        "023",
        "run-test:speckit.solution",
        phase="solution",
    )

    assert result["ok"] is True
    assert result["next_phase"] == "implement"
    assert result["task_count"] == 2
    assert result["story_count"] == 1
    assert result["estimate_points"] == 13
    assert result["pipeline_event_request"] == {
        "event": "solution_approved",
        "fields": {
            "task_count": 2,
            "story_count": 1,
            "estimate_points": 13,
            "routing": {"plan_level": "simple"},
            "triage": {"tshirt_size": "s"},
            "risk": {"overall": "low"},
            "domains": {"relevant": ["testing"], "reasoning": {}},
            "strategy": {"architecture_strategy": False},
            "design_slices": [],
            "routing_json_path": str(feature_dir / "routing.json"),
        },
    }
    assert [stage["stage"] for stage in result["stages"]] == [
        "tasking_chain",
        "tasks_gate",
        "huds_validate",
        "task_registration",
        "acceptance",
    ]
