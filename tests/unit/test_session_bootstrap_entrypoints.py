"""Unit tests for shared session bootstrap call sites."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_script_module(module_name: str, script_path: Path) -> ModuleType:
    """Load a script module from disk for bootstrap-entrypoint tests."""
    scripts_dir = script_path.parent
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_PREREQUISITES = _load_script_module(
    "check_prerequisites_entrypoint",
    REPO_ROOT / ".specify" / "scripts" / "python" / "check_prerequisites.py",
)
SETUP_PLAN = _load_script_module(
    "setup_plan_entrypoint",
    REPO_ROOT / ".specify" / "scripts" / "python" / "setup_plan.py",
)
TASKING_CHAIN = _load_script_module(
    "speckit_tasking_chain_entrypoint",
    REPO_ROOT / "scripts" / "speckit_tasking_chain.py",
)


def test_check_prerequisites_bootstraps_session(monkeypatch) -> None:
    """check_prerequisites should warm the shared bootstrap before validation."""
    calls: list[Path] = []

    monkeypatch.setattr(
        CHECK_PREREQUISITES,
        "bootstrap_session",
        lambda repo_root: calls.append(Path(repo_root)) or {"bootstrap_ok": True},
    )
    monkeypatch.setattr(
        CHECK_PREREQUISITES,
        "_get_feature_paths",
        lambda _script_path: {
            "REPO_ROOT": str(REPO_ROOT),
            "CURRENT_BRANCH": "028-tetris-game",
            "HAS_GIT": "true",
            "FEATURE_DIR": "/tmp/feature",
            "FEATURE_SPEC": "/tmp/feature/spec.md",
            "IMPL_PLAN": "/tmp/feature/plan.md",
            "TASKS": "/tmp/feature/tasks.md",
            "RESEARCH": "/tmp/feature/research.md",
            "DATA_MODEL": "/tmp/feature/data-model.md",
            "QUICKSTART": "/tmp/feature/quickstart.md",
            "CONTRACTS_DIR": "/tmp/feature/contracts",
        },
    )
    monkeypatch.setattr(CHECK_PREREQUISITES, "check_feature_branch", lambda *_args, **_kwargs: None)

    exit_code = CHECK_PREREQUISITES.main(["--paths-only"])

    assert exit_code == 0
    assert calls == [REPO_ROOT]


def test_setup_plan_bootstraps_session(monkeypatch) -> None:
    """setup_plan should warm the shared bootstrap before reading plan paths."""
    calls: list[Path] = []

    monkeypatch.setattr(
        SETUP_PLAN,
        "bootstrap_session",
        lambda repo_root: calls.append(Path(repo_root)) or {"bootstrap_ok": True},
    )
    monkeypatch.setattr(
        SETUP_PLAN,
        "_build_paths",
        lambda _script_path: {
            "REPO_ROOT": str(REPO_ROOT),
            "CURRENT_BRANCH": "028-tetris-game",
            "HAS_GIT": "true",
            "FEATURE_DIR": "/tmp/feature",
            "FEATURE_SPEC": "/tmp/feature/spec.md",
            "IMPL_PLAN": "/tmp/feature/plan.md",
        },
    )
    monkeypatch.setattr(SETUP_PLAN, "check_feature_branch", lambda *_args, **_kwargs: None)

    exit_code = SETUP_PLAN.main(["--json"])

    assert exit_code == 0
    assert calls == [REPO_ROOT]


def test_tasking_chain_bootstraps_session(tmp_path: Path, monkeypatch) -> None:
    """Tasking stabilization should warm the shared bootstrap before subprocess work."""
    feature_dir = tmp_path / "specs" / "028-tetris-game"
    feature_dir.mkdir(parents=True)
    tasks_file = feature_dir / "tasks.md"
    tasks_file.write_text("## User Story 1\n", encoding="utf-8")
    estimates_file = feature_dir / "estimates.md"
    estimates_file.write_text("T001 1 point\n", encoding="utf-8")
    calls: list[Path] = []

    monkeypatch.setattr(
        TASKING_CHAIN,
        "bootstrap_session",
        lambda repo_root: calls.append(Path(repo_root)) or {"bootstrap_ok": True},
    )
    monkeypatch.setattr(
        TASKING_CHAIN,
        "_resolve_paths",
        lambda _args: (feature_dir, tasks_file, estimates_file),
    )
    monkeypatch.setattr(
        TASKING_CHAIN,
        "_run_command",
        lambda command, *, cwd: TASKING_CHAIN.CommandResult(
            command=" ".join(str(part) for part in command),
            exit_code=0,
            stdout="",
            stderr="",
        ),
    )
    monkeypatch.setattr(TASKING_CHAIN, "_clear_tasking_sessions", lambda _feature_dir: [])

    payload = TASKING_CHAIN.run_chain(
        SimpleNamespace(
            feature_dir=str(feature_dir),
            tasks_file=None,
            estimates_file=None,
            estimate_command="echo estimate",
            breakdown_command="",
            max_rounds=4,
            json=True,
        )
    )

    assert payload["ok"] is True
    assert calls == [REPO_ROOT]
