from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


def _load_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    module_path = scripts_dir / script_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module {module_name} from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


git_diff_guard = _load_module("git_diff_guard", "git_diff_guard.py")


def _completed(returncode: int, *, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_main_builds_default_stat_command(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _completed(0)

    monkeypatch.setattr(git_diff_guard.subprocess, "run", fake_run)

    exit_code = git_diff_guard.main(["scripts/read_code.py"])

    assert exit_code == 0
    assert calls == [["git", "diff", "--no-color", "--stat", "--", "scripts/read_code.py"]]


def test_main_supports_explicit_patch_output(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _completed(0)

    monkeypatch.setattr(git_diff_guard.subprocess, "run", fake_run)

    exit_code = git_diff_guard.main(["--patch", "scripts/read_code.py"])

    assert exit_code == 0
    assert calls == [["git", "diff", "--no-color", "--unified=3", "--", "scripts/read_code.py"]]


def test_main_uses_cached_stat_flags(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return _completed(0)

    monkeypatch.setattr(git_diff_guard.subprocess, "run", fake_run)

    exit_code = git_diff_guard.main(["--cached", "--stat", "scripts/read_code.py"])

    assert exit_code == 0
    assert calls == [["git", "diff", "--no-color", "--cached", "--stat", "--", "scripts/read_code.py"]]


def test_main_rejects_path_outside_repo(tmp_path: Path, capsys) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("print('x')\n", encoding="utf-8")

    exit_code = git_diff_guard.main([str(outside)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "outside repo root" in captured.err


def test_output_is_truncated_when_over_cap(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        git_diff_guard.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            0,
            stdout="a\nb\nc\nd\n",
            stderr="e\n",
        ),
    )

    exit_code = git_diff_guard.main(["--max-lines", "3", "scripts/read_code.py"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.splitlines() == ["a", "b", "c"]
    assert "output truncated by git_diff_guard" in captured.err
