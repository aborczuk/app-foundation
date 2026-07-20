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
speckit_tasking_step = _load_script_module("speckit_tasking_step", "speckit_tasking_step.py")


def test_tasking_step_defaults_to_tasking_phase(monkeypatch) -> None:
    """The canonical wrapper must request tasking completion, not solution approval."""
    seen: dict[str, object] = {}

    def fake_legacy_main(args: list[str]) -> int:
        seen["args"] = args
        return 0

    monkeypatch.setattr(speckit_tasking_step, "_legacy_main", fake_legacy_main)

    assert speckit_tasking_step.main(["--feature-id", "023", "--correlation-id", "run"]) == 0
    assert seen["args"] == [
        "--feature-id",
        "023",
        "--correlation-id",
        "run",
        "--phase",
        "tasking",
    ]


def test_resolve_feature_dir_accepts_numeric_id(tmp_path: Path) -> None:
    """Numeric feature ids should resolve to the matching specs slug directory."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "029-make-tetris"
    feature_dir.mkdir(parents=True)

    resolved = speckit_solution_step._resolve_feature_dir(repo_root, "029")

    assert resolved == feature_dir


def test_resolve_feature_dir_accepts_full_slug(tmp_path: Path) -> None:
    """Full feature slugs should resolve directly without prefix globbing."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "029-make-tetris"
    feature_dir.mkdir(parents=True)

    resolved = speckit_solution_step._resolve_feature_dir(repo_root, "029-make-tetris")

    assert resolved == feature_dir


def test_resolve_feature_dir_normalizes_trailing_slash(tmp_path: Path) -> None:
    """Feature ids with a trailing slash should resolve after normalization."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "029-make-tetris"
    feature_dir.mkdir(parents=True)

    resolved = speckit_solution_step._resolve_feature_dir(repo_root, "029-make-tetris/")

    assert resolved == feature_dir


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
    (feature_dir / "spec.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(speckit_solution_step, "DEFAULT_TASKS_TEMPLATE", template_path)
    monkeypatch.setattr(
        speckit_solution_step,
        "_resolve_solution_paths",
        lambda feature_id: (repo_root, feature_dir, plan_path),
    )

    result = speckit_solution_step.prepare_tasking("023")

    assert result["ok"] is True
    assert result["spec_artifact"] == str(feature_dir / "spec.json")
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
    (feature_dir / "spec.json").write_text(
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
        "_generate_acceptance_tests",
        lambda **kwargs: {"stdout": "acceptance", "stderr": ""},
    )
    monkeypatch.setattr(
        speckit_solution_step,
        "_run_clickup_sync",
        lambda **kwargs: {"ok": True, "skipped": False, "mode": "bootstrap"},
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
            "spec_json_path": str(feature_dir / "spec.json"),
        },
    }
    assert [stage["stage"] for stage in result["stages"]] == [
        "tasking_chain_validate",
        "tasks_gate",
        "task_registration",
        "acceptance",
        "clickup_sync",
    ]


def test_ledger_feature_id_extracts_numeric_prefix_from_feature_slug(tmp_path: Path) -> None:
    """Task registration receives the numeric id rather than a feature slug."""
    feature_dir = tmp_path / "039-autonomous-spec-pipeline-upgrade"

    assert speckit_solution_step._ledger_feature_id(feature_dir) == "039"


def test_count_stories_uses_task_labels_when_phases_are_not_story_headings(tmp_path: Path) -> None:
    """Phase-oriented task files still report their user-story traceability."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(
        "## Phase 1: Setup\n- [ ] T001 [US4] Add preflight in scripts/preflight.py.\n"
        "## Phase 2: Routing\n- [ ] T002 [US1] Add route in scripts/routes.py.\n",
        encoding="utf-8",
    )

    assert speckit_solution_step._count_stories(tasks_file) == 2


def test_run_tasking_stabilization_uses_validation_only_chain(
    tmp_path: Path, monkeypatch
) -> None:
    """Finalize should validate settled estimates without passing runner commands."""
    repo_root = tmp_path / "repo"
    feature_dir = repo_root / "specs" / "023-deterministic-phase-orchestration"
    feature_dir.mkdir(parents=True)

    captured_command: list[str] = []

    class Completed:
        """Tiny subprocess completion stub."""

        returncode = 0
        stdout = '{"ok": true, "high_point_tasks": [], "command_results": []}'
        stderr = ""

    def fake_run_command(command, *, cwd, input_payload=None):
        captured_command[:] = command
        assert cwd == repo_root
        assert input_payload is None
        return Completed()

    monkeypatch.setattr(speckit_solution_step, "_run_command", fake_run_command)

    payload = speckit_solution_step._run_tasking_stabilization(
        repo_root=repo_root,
        feature_dir=feature_dir,
    )

    assert payload["ok"] is True
    assert "--estimate-command" not in captured_command
    assert "--breakdown-command" not in captured_command
