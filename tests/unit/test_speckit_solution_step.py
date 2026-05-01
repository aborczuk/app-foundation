"""Unit tests for scripts/speckit_solution_step.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict


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


class CallRecord(TypedDict):
    """Record one Codex action call from the solution orchestrator."""

    phase: str
    task_action: str
    instructions: str
    output_template_path: Path
    resume_session: bool


def test_orchestrate_solution_runs_linear_solution_ladder(tmp_path: Path, monkeypatch) -> None:
    """Solution orchestration should ladder sketch into tasking, then approval."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text("## User Story 1\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("**Total Points**: 21\n", encoding="utf-8")

    calls: list[CallRecord] = []
    events: list[tuple[str, str, dict[str, object] | None]] = []

    monkeypatch.setattr(
        speckit_solution_step,
        "_load_prerequisites",
        lambda _repo_root: {"FEATURE_DIR": str(feature_dir), "AVAILABLE_DOCS": []},
    )

    def fake_run_codex_action(**kwargs):  # noqa: ANN001
        phase = str(kwargs["phase"])
        task_action = str(kwargs["task_action"])
        instructions = str(kwargs["instructions"])
        output_template_path = Path(kwargs["output_template_path"])
        calls.append(
            {
                "phase": phase,
                "task_action": task_action,
                "instructions": instructions,
                "output_template_path": output_template_path,
                "resume_session": bool(kwargs.get("resume_session", False)),
            }
        )
        output_template_path.parent.mkdir(parents=True, exist_ok=True)
        if phase == "sketch":
            output_template_path.write_text(
                "\n".join(
                    [
                        "## Coverage",
                        "## Current -> Target",
                        "## Primary Seam",
                        "## Required Edit / Solution",
                        "## Verification",
                        "## Constraints / Preserve",
                        "## Implementation Directive",
                        "## Design-to-Tasking Contract",
                        "## Sketch Completion Summary",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        elif phase == "tasking":
            output_template_path.write_text("## User Story 1\n", encoding="utf-8")
        return {"ok": True, "phase": phase}

    monkeypatch.setattr(speckit_solution_step, "_run_codex_action", fake_run_codex_action)
    monkeypatch.setattr(
        speckit_solution_step,
        "_run_tasking_stabilization",
        lambda **kwargs: {"ok": True, "rounds": 1},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_run_tasks_gate",
        lambda **kwargs: {"ok": True, "checked": True},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_register_tasks",
        lambda **kwargs: {"newly_registered_task_ids": ["T001"], "next_task_id": "T001"},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_generate_huds",
        lambda **kwargs: {"stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_generate_acceptance_tests",
        lambda **kwargs: {"stdout": "", "stderr": ""},
    )

    def fake_append_pipeline_event(**kwargs):  # noqa: ANN001
        events.append((str(kwargs["phase"]), str(kwargs["event"]), kwargs.get("fields")))
        return {"ok": True}

    monkeypatch.setattr(speckit_solution_step, "_append_pipeline_event", fake_append_pipeline_event)
    monkeypatch.setattr(
        speckit_solution_step,
        "_stage_and_commit",
        lambda repo_root, commit_message: {
            "commit_sha": "abc123",
            "changed_files": [
                "specs/023-deterministic-phase-orchestration/sketch.md",
                "specs/023-deterministic-phase-orchestration/tasks.md",
            ],
        },
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "parse_task_definitions",
        lambda tasks_path: [SimpleNamespace(task_id="T001")],
    )

    result = speckit_solution_step.orchestrate_solution(
        "023",
        "run-test:speckit.solution",
        phase="solution",
    )

    assert result["ok"] is True
    assert result["next_phase"] == "implement"
    assert result["task_count"] == 1
    assert result["story_count"] == 1
    assert result["estimate_points"] == 21
    assert result["commit_sha"] == "abc123"
    assert Path(result["debug_path"]).is_file()
    assert [call["phase"] for call in calls] == ["sketch", "tasking"]
    assert calls[0]["task_action"] == "sketch"
    assert calls[0]["instructions"].startswith("Update FEATURE_DIR/sketch.md")
    assert calls[0]["resume_session"] is False
    assert calls[1]["task_action"] == "decompose_tasks"
    assert calls[1]["instructions"].startswith("Decompose the approved sketch.md")
    assert calls[1]["phase"] == "tasking"
    assert calls[1]["output_template_path"].name == "tasks.md"
    assert calls[1]["resume_session"] is True
    assert events == [
        ("sketch", "sketch_completed", None),
        ("tasking", "tasking_completed", {"task_count": 1, "story_count": 1}),
        (
            "solution",
            "solution_approved",
            {"task_count": 1, "story_count": 1, "estimate_points": 21},
        ),
    ]
