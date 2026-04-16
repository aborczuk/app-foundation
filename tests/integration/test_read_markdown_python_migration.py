"""Integration tests for read-markdown shell-wrapper/Python migration contract."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "read-markdown.sh"


def _env_without_uv() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    return env


def _env_with_fake_uv(tmp_path: Path, indexer_payload: str) -> dict[str, str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"--version\" ]]; then\n"
        "  echo \"uv 0.0.0\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == \"run\" && \"$2\" == \"--no-sync\" && \"$3\" == \"python\" && \"$4\" == \"-m\" && \"$5\" == \"src.mcp_codebase.indexer\" ]]; then\n"
        "  if [[ -n \"${FAKE_INDEXER_PAYLOAD:-}\" ]]; then\n"
        "    printf '%s\\n' \"$FAKE_INDEXER_PAYLOAD\"\n"
        "    exit 0\n"
        "  fi\n"
        "fi\n"
        "if [[ \"$1\" == \"run\" && \"$2\" == \"--no-sync\" && \"$3\" == \"python\" ]]; then\n"
        "  exec python3 \"${@:4}\"\n"
        "fi\n"
        "echo \"fake uv: unsupported invocation: $*\" >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"
    env["FAKE_INDEXER_PAYLOAD"] = indexer_payload
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


def test_read_markdown_resolves_prefix_section_via_vector_hit(tmp_path: Path) -> None:
    markdown_file = tmp_path / "sample.md"
    lines = [
        "# Doc Title",
        "",
        "Intro",
        "",
        "## Phase 9: Add-to-Backlog - Python Orchestration Migration",
        "line-1",
        "line-2",
        "line-3",
    ]
    markdown_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = json.dumps(
        [
            {
                "file_path": str(markdown_file),
                "line_start": 5,
                "heading": "Phase 9: Add-to-Backlog - Python Orchestration Migration",
                "breadcrumb": ["Specs", "Phase 9: Add-to-Backlog - Python Orchestration Migration"],
                "score": 0.97,
            }
        ]
    )

    result = _run_read_markdown(
        tmp_path,
        str(markdown_file),
        "Phase 9",
        env=_env_with_fake_uv(tmp_path, payload),
    )

    assert result.returncode == 0, result.stderr
    rendered = [line for line in result.stdout.strip().splitlines() if line]
    assert rendered[0] == "5\t## Phase 9: Add-to-Backlog - Python Orchestration Migration"


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
