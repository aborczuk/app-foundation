"""Tool dependency parity contracts for migrated SpecKit entrypoints."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURE_NAME = "022-codegraph-hardening"
FEATURE_DIR = Path("specs") / FEATURE_NAME


def _copy_tree(src: Path, dest: Path) -> None:
    shutil.copytree(src, dest)


def _bootstrap_workspace(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", FEATURE_NAME], cwd=repo_root, check=True, capture_output=True, text=True)

    (repo_root / ".specify").mkdir(parents=True, exist_ok=True)
    _copy_tree(REPO_ROOT / ".specify" / "scripts", repo_root / ".specify" / "scripts")
    _copy_tree(REPO_ROOT / ".specify" / "templates", repo_root / ".specify" / "templates")
    _copy_tree(REPO_ROOT / "scripts", repo_root / "scripts")

    feature_dir = repo_root / FEATURE_DIR
    (feature_dir / "contracts").mkdir(parents=True, exist_ok=True)
    (feature_dir / "plan.md").write_text(
        """# Plan

**Language/Version**: Python 3.12
**Primary Dependencies**: pytest
**Storage**: sqlite
**Project Type**: cli
""",
        encoding="utf-8",
    )
    (feature_dir / "tasks.md").write_text("- [ ] T001 Smoke task\n", encoding="utf-8")
    (feature_dir / "research.md").write_text("# Research\n", encoding="utf-8")
    (feature_dir / "data-model.md").write_text("# Data Model\n", encoding="utf-8")
    (feature_dir / "quickstart.md").write_text("# Quickstart\n", encoding="utf-8")
    (feature_dir / "contracts" / "contract.md").write_text("# Contract\n", encoding="utf-8")
    (repo_root / ".specify" / "templates" / "plan-template.md").write_text("# Generated Plan\n", encoding="utf-8")

    return repo_root


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def _normalize(text: str, repo_root: Path) -> str:
    return text.replace(str(repo_root), "<REPO_ROOT>")


def _run_shell(repo_root: Path, script_path: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(script_path), *args],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_python(repo_root: Path, script_path: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_parity(
    shell_result: subprocess.CompletedProcess[str],
    shell_repo: Path,
    python_result: subprocess.CompletedProcess[str],
    python_repo: Path,
) -> None:
    assert shell_result.returncode == python_result.returncode, (
        f"exit mismatch\nshell={shell_result.returncode}\npython={python_result.returncode}\n"
        f"shell stderr={shell_result.stderr}\npython stderr={python_result.stderr}"
    )
    assert _normalize(shell_result.stdout, shell_repo) == _normalize(python_result.stdout, python_repo), (
        f"stdout mismatch\nshell={shell_result.stdout}\npython={python_result.stdout}"
    )
    assert _normalize(shell_result.stderr, shell_repo) == _normalize(python_result.stderr, python_repo), (
        f"stderr mismatch\nshell={shell_result.stderr}\npython={python_result.stderr}"
    )


def test_setup_plan_with_uv_missing_uses_python3(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")
    fake_bin = _fake_bin(tmp_path / "shell")
    _write_executable(fake_bin / "git", "#!/usr/bin/env bash\nexit 127\n")
    python3_shim = fake_bin / "python3"
    _write_executable(
        python3_shim,
        f"""#!/usr/bin/env bash
exec {sys.executable} "$@"
""",
    )

    shell_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}
    python_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "setup-plan.sh",
        shell_env,
        "--json",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "setup_plan.py",
        python_env,
        "--json",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0


def test_update_agent_context_with_python3_missing_uses_uv(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")
    fake_bin = _fake_bin(tmp_path / "shell")
    _write_executable(fake_bin / "git", "#!/usr/bin/env bash\nexit 127\n")
    uv_shim = fake_bin / "uv"
    _write_executable(
        uv_shim,
        f"""#!/usr/bin/env bash
if [[ "$1" == "run" ]]; then
  shift
fi
if [[ "$1" == "--no-sync" ]]; then
  shift
fi
if [[ "$1" == "python" ]]; then
  shift
fi
exec {sys.executable} "$@"
""",
    )

    shell_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}
    python_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "update-agent-context.sh",
        shell_env,
        "claude",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "update_agent_context.py",
        python_env,
        "claude",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0


def test_check_prerequisites_with_git_missing_matches_python(tmp_path: Path) -> None:
    shell_repo = _bootstrap_workspace(tmp_path / "shell")
    python_repo = _bootstrap_workspace(tmp_path / "python")
    fake_bin = _fake_bin(tmp_path / "shell")
    _write_executable(fake_bin / "git", "#!/usr/bin/env bash\nexit 127\n")
    python3_shim = fake_bin / "python3"
    _write_executable(
        python3_shim,
        f"""#!/usr/bin/env bash
exec {sys.executable} "$@"
""",
    )

    shell_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}
    python_env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}

    shell_result = _run_shell(
        shell_repo,
        shell_repo / ".specify" / "scripts" / "bash" / "check-prerequisites.sh",
        shell_env,
        "--json",
        "--paths-only",
    )
    python_result = _run_python(
        python_repo,
        python_repo / ".specify" / "scripts" / "python" / "check_prerequisites.py",
        python_env,
        "--json",
        "--paths-only",
    )

    _assert_parity(shell_result, shell_repo, python_result, python_repo)
    assert shell_result.returncode == 0
    assert "Warning: Git repository not detected" in shell_result.stderr
