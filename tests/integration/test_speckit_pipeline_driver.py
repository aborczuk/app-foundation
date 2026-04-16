"""Smoke coverage for the migrated SpecKit orchestration entrypoints."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_PLAN = REPO_ROOT / ".specify" / "scripts" / "python" / "setup_plan.py"
CHECK_PREREQUISITES = REPO_ROOT / ".specify" / "scripts" / "python" / "check_prerequisites.py"
PIPELINE_GATE_STATUS = REPO_ROOT / "scripts" / "speckit_gate_status.py"


def _load_script_module(module_name: str, script_path: Path):
    scripts_dir = script_path.parent
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


speckit_gate_status = _load_script_module("speckit_gate_status", PIPELINE_GATE_STATUS)


def _init_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    feature_dir = repo_root / "specs" / "022-codegraph-hardening"
    checklists_dir = feature_dir / "checklists"
    contracts_dir = feature_dir / "contracts"
    templates_dir = repo_root / ".specify" / "templates"
    scripts_dir = repo_root / "scripts"

    checklists_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    templates_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (templates_dir / "plan-template.md").write_text("# Generated Plan\n", encoding="utf-8")
    (checklists_dir / "requirements.md").write_text("- [X] requirements complete\n", encoding="utf-8")
    (checklists_dir / "quality.md").write_text("- [X] quality complete\n", encoding="utf-8")
    (feature_dir / "tasks.md").write_text("- [X] T001 Smoke task\n", encoding="utf-8")
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")
    (feature_dir / "data-model.md").write_text("# Data Model\n", encoding="utf-8")
    (feature_dir / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8")
    (feature_dir / "e2e.md").write_text("# E2E\n", encoding="utf-8")
    (feature_dir / "estimates.md").write_text("# Estimates\n", encoding="utf-8")
    (contracts_dir / "contract.md").write_text("# Contract\n", encoding="utf-8")

    e2e_script = scripts_dir / "e2e_022_codegraph_hardening.sh"
    e2e_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    e2e_script.chmod(0o755)

    return repo_root, feature_dir


def _run_entrypoint(repo_root: Path, script_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {"SPECIFY_FEATURE": "022-codegraph-hardening", "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_python_orchestration_entrypoints(tmp_path: Path) -> None:
    repo_root, feature_dir = _init_repo(tmp_path)

    setup_result = _run_entrypoint(repo_root, SETUP_PLAN, "--json")
    assert setup_result.returncode == 0, setup_result.stderr
    setup_payload = json.loads(setup_result.stdout.splitlines()[-1])
    assert setup_payload["FEATURE_SPEC"] == str(feature_dir / "spec.md")
    assert (feature_dir / "plan.md").read_text(encoding="utf-8") == "# Generated Plan\n"

    paths_only_result = _run_entrypoint(repo_root, CHECK_PREREQUISITES, "--paths-only", "--json")
    assert paths_only_result.returncode == 0, paths_only_result.stderr
    paths_payload = json.loads(paths_only_result.stdout)
    assert paths_payload["FEATURE_DIR"] == str(feature_dir)
    assert paths_payload["TASKS"] == str(feature_dir / "tasks.md")

    prerequisites_result = _run_entrypoint(
        repo_root,
        CHECK_PREREQUISITES,
        "--json",
        "--require-tasks",
        "--include-tasks",
    )
    assert prerequisites_result.returncode == 0, prerequisites_result.stderr
    prerequisites_payload = json.loads(prerequisites_result.stdout)
    assert prerequisites_payload["AVAILABLE_DOCS"] == [
        "research.md",
        "data-model.md",
        "contracts/",
        "quickstart.md",
        "tasks.md",
    ]

    plan_report, plan_exit = speckit_gate_status._plan_report(feature_dir)
    assert plan_exit == 0
    assert plan_report["ok"] is True
    assert plan_report["hard_block_reasons"] == []

    implement_report, implement_exit = speckit_gate_status._implement_report(feature_dir, repo_root)
    assert implement_exit == 0
    assert implement_report["ok"] is True
    assert implement_report["e2e"]["ok"] is True
    assert implement_report["estimates"]["exists"] is True
    assert implement_report["checklists"]["all_complete"] is True
