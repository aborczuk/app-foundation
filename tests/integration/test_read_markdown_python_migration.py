"""Integration tests for read-markdown shell-wrapper/Python migration contract."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "read-markdown.sh"


def _env_without_uv() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    return env


def _run_read_markdown(
    cwd: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), *args],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_read_markdown_requires_two_arguments(tmp_path: Path) -> None:
    result = _run_read_markdown(tmp_path, env=_env_without_uv())

    assert result.returncode == 1
    assert (
        "ERROR: read_markdown_section requires two arguments: <file> <section_heading>"
        in result.stderr
    )


def test_read_markdown_resolves_section_and_prints_50_line_window(tmp_path: Path) -> None:
    markdown_file = tmp_path / "sample.md"
    lines = [
        "# Doc Title",
        "",
        "Intro",
        "",
        "## Target Section",
    ]
    lines.extend([f"line-{i}" for i in range(1, 61)])
    markdown_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _run_read_markdown(
        tmp_path,
        str(markdown_file),
        "Target Section",
        env=_env_without_uv(),
    )

    assert result.returncode == 0, result.stderr
    rendered = [line for line in result.stdout.strip().splitlines() if line]
    assert len(rendered) == 50
    assert rendered[0] == "5\t## Target Section"
    assert rendered[-1] == "54\tline-49"


def test_read_markdown_reports_missing_section(tmp_path: Path) -> None:
    markdown_file = tmp_path / "sample.md"
    markdown_file.write_text("# Title\n\n## Existing\nContent\n", encoding="utf-8")

    result = _run_read_markdown(
        tmp_path,
        str(markdown_file),
        "Missing",
        env=_env_without_uv(),
    )

    assert result.returncode == 1
    assert f"ERROR: Section '## Missing' not found in {markdown_file}" in result.stderr


def test_read_markdown_source_wrapper_still_exposes_function(tmp_path: Path) -> None:
    markdown_file = tmp_path / "sample.md"
    markdown_file.write_text("# Title\n\n## Existing\nBody\n", encoding="utf-8")
    env = _env_without_uv()

    result = subprocess.run(
        [
            "bash",
            "-lc",
            f"source '{SCRIPT_PATH}' && read_markdown_section '{markdown_file}' 'Existing'",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].startswith("3\t## Existing")
