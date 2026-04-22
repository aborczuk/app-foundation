"""Integration tests for read-code shell-wrapper/Python migration contract."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "read-code.sh"


def _env_without_uv() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/bin:/bin"
    return env


def _env_with_fake_uv(tmp_path: Path, indexer_payload: str = "[]") -> dict[str, str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "if [[ \"$1\" == \"--version\" ]]; then\n"
        "  echo \"uv 0.0-test\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1\" == \"run\" && \"$2\" == \"--no-sync\" && \"$3\" == \"python\" ]]; then\n"
        "  shift 3\n"
        "  if [[ \"$1\" == \"-m\" && \"$2\" == \"src.mcp_codebase.indexer\" ]]; then\n"
        "    printf '%s\\n' \"${FAKE_INDEXER_PAYLOAD:-[]}\"\n"
        "    exit 0\n"
        "  fi\n"
        "  if [[ \"$1\" == \"-m\" && \"$2\" == \"src.mcp_codebase.doctor\" ]]; then\n"
        "    echo '{\"status\":\"healthy\"}'\n"
        "    exit 0\n"
        "  fi\n"
        "  exec python3 \"$@\"\n"
        "fi\n"
        "if [[ \"$1\" == \"run\" && \"$2\" == \"--no-sync\" && \"$3\" == \"cgc\" && \"$4\" == \"find\" ]]; then\n"
        "  exit 0\n"
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


def _run_read_code(
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


def test_read_code_cli_usage_requires_mode_and_arguments(tmp_path: Path) -> None:
    result = _run_read_code(tmp_path, env=_env_without_uv())

    assert result.returncode == 1
    assert "Usage:" in result.stdout
    assert "read_code_context" in result.stdout
    assert "read_code_window" in result.stdout
    assert "read_code_symbols" in result.stdout


def test_read_code_context_renders_numbered_context_window(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text(
        "\n".join(
            [
                "def helper():",
                "    return 1",
                "",
                "def run_pipeline():",
                "    step = 1",
                "    return step",
                "",
                "def after():",
                "    return 2",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "run_pipeline",
        "2",
        "--hud-symbol",
        env=_env_without_uv(),
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert any(line.endswith("\tdef run_pipeline():") for line in lines)
    assert any(line.endswith("\t    step = 1") for line in lines)
    assert any(line.endswith("\t    return step") for line in lines)


def test_read_code_context_accepts_125_line_window_cap(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "run_pipeline",
        "125",
        "--hud-symbol",
        env=_env_without_uv(),
    )

    assert result.returncode == 0, result.stderr
    assert any(line.endswith("\tdef run_pipeline():") for line in result.stdout.splitlines())


def test_read_code_context_uses_local_exact_symbol_without_uv(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text(
        "def run_pipeline():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "run_pipeline",
        "2",
        env=_env_without_uv(),
    )

    assert result.returncode == 0, result.stderr
    assert any(line.endswith("\tdef run_pipeline():") for line in result.stdout.splitlines())
    assert "WARN: Vector semantic anchor unavailable (uv is not available)" in result.stderr
    assert "using strict/local anchor" in result.stderr


def test_read_code_context_requires_uv_only_when_no_local_anchor_exists(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text(
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "missing_pipeline",
        "2",
        env=_env_without_uv(),
    )

    assert result.returncode == 1
    assert "ERROR: uv is required for codegraph discovery" in result.stderr


def test_read_code_context_uses_uv_branch_without_hud_fast_path(tmp_path: Path) -> None:
    code_file = tmp_path / "uv_sample.py"
    code_file.write_text(
        "\n".join(
            [
                "def before():",
                "    return 0",
                "",
                "def run_pipeline():",
                "    return 1",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "run_pipeline",
        "2",
        env=_env_with_fake_uv(tmp_path),
    )

    assert result.returncode == 0, result.stderr
    assert any(line.endswith("\tdef run_pipeline():") for line in result.stdout.splitlines())
    assert "WARN: Vector semantic anchor not found" in result.stderr
    assert "using strict/local anchor" in result.stderr


def test_read_code_context_renders_shortlist_and_confident_body(tmp_path: Path) -> None:
    code_file = tmp_path / "uv_sample.py"
    code_file.write_text(
        "\n".join(
            [
                "def helper():",
                "    return 0",
                "",
                "def run_pipeline():",
                "    return 1",
                "",
                "def after():",
                "    return 2",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        [
            {
                "file_path": str(code_file),
                "line_start": 4,
                "line_end": 5,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "run_pipeline",
                "qualified_name": "sample.run_pipeline",
                "signature": "def run_pipeline():",
                "docstring": "Run the pipeline.",
                "body": "def run_pipeline():\n    return 1",
                "preview": "def run_pipeline():",
                "symbol_type": "function",
                "score": 1.0,
                "distance": 0.0,
            },
            {
                "file_path": str(code_file),
                "line_start": 1,
                "line_end": 2,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "helper",
                "qualified_name": "sample.helper",
                "signature": "def helper():",
                "docstring": "Helper.",
                "body": "def helper():\n    return 0",
                "preview": "def helper():",
                "symbol_type": "function",
                "score": 0.6,
                "distance": 0.4,
            },
        ]
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "run_pipeline",
        "2",
        env=_env_with_fake_uv(tmp_path, indexer_payload=payload),
    )

    assert result.returncode == 0, result.stderr
    assert "# shortlist for: run_pipeline" in result.stdout
    assert "# body" in result.stdout
    assert any(line.endswith("\tdef run_pipeline():") for line in result.stdout.splitlines())
    assert any(line.endswith("\t    return 1") for line in result.stdout.splitlines())


def test_read_code_context_prefers_exact_symbol_vector_hit_over_header_block(tmp_path: Path) -> None:
    code_file = tmp_path / "wrapper.sh"
    code_file.write_text(
        "\n".join(
            [
                "# read-code.sh: helper documentation mentioning read_code_window",
                "# usage line",
                "",
                "read_code_window() {",
                "    echo \"real function\"",
                "}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        [
            {
                "file_path": str(code_file),
                "line_start": 1,
                "line_end": 2,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "block_1",
                "qualified_name": "wrapper.sh::block_1",
                "signature": "set -e",
                "docstring": "read-code.sh helper docs mentioning read_code_window",
                "body": "# read-code.sh: helper documentation mentioning read_code_window",
                "preview": "# read-code.sh: helper documentation mentioning read_code_window",
                "symbol_type": "script_block",
                "score": 0.99,
            },
            {
                "file_path": str(code_file),
                "line_start": 4,
                "line_end": 6,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "read_code_window",
                "qualified_name": "wrapper.sh::read_code_window",
                "signature": "read_code_window() {",
                "docstring": "Render a bounded code window.",
                "body": "read_code_window() {\n    echo \"real function\"\n}",
                "preview": "read_code_window() {",
                "symbol_type": "function",
                "score": 0.88,
            },
        ]
    )

    result = _run_read_code(
        tmp_path,
        "context",
        str(code_file),
        "read_code_window",
        "1",
        "--hud-symbol",
        env=_env_with_fake_uv(tmp_path, payload),
    )

    assert result.returncode == 0, result.stderr
    assert any(line.endswith("\tread_code_window() {") for line in result.stdout.splitlines())
    assert not any(line.endswith("\t# read-code.sh: helper documentation mentioning read_code_window") for line in result.stdout.splitlines())


def test_read_code_window_requires_symbol_for_large_files_without_hud(tmp_path: Path) -> None:
    code_file = tmp_path / "large.py"
    code_file.write_text(
        "\n".join([f"line_{idx} = {idx}" for idx in range(1, 231)]) + "\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "window",
        str(code_file),
        "10",
        "5",
        env=_env_without_uv(),
    )

    assert result.returncode == 1
    assert "symbol_or_pattern is required for files >200 lines" in result.stderr


def test_read_code_window_allows_large_file_read_with_hud_symbol(tmp_path: Path) -> None:
    code_file = tmp_path / "large.py"
    code_file.write_text(
        "\n".join([f"line_{idx} = {idx}" for idx in range(1, 231)]) + "\n",
        encoding="utf-8",
    )

    result = _run_read_code(
        tmp_path,
        "window",
        str(code_file),
        "10",
        "3",
        "--hud-symbol",
        env=_env_without_uv(),
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].endswith("\tline_10 = 10")
    assert lines[-1].endswith("\tline_12 = 12")


def test_read_code_source_wrapper_exposes_functions(tmp_path: Path) -> None:
    code_file = tmp_path / "source_sample.py"
    code_file.write_text(
        "def target():\n"
        "    return 1\n"
        "def other():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    env = _env_without_uv()

    result = subprocess.run(
        [
            "bash",
            "-lc",
            f"source '{SCRIPT_PATH}' && read_code_context '{code_file}' 'target' 1",
        ],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert any(line.endswith("\tdef target():") for line in result.stdout.splitlines())


def test_read_code_symbols_lists_vector_backed_file_symbols(tmp_path: Path) -> None:
    code_file = tmp_path / "source_sample.py"
    code_file.write_text(
        "def target():\n"
        "    return 1\n"
        "def other():\n"
        "    return 2\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        [
            {
                "file_path": str(code_file),
                "line_start": 1,
                "line_end": 2,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "target",
                "qualified_name": "source_sample.target",
                "signature": "def target():",
                "docstring": "",
                "body": "def target():\n    return 1\n",
                "preview": "def target():",
                "symbol_type": "function",
            },
            {
                "file_path": str(code_file),
                "line_start": 3,
                "line_end": 4,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "other",
                "qualified_name": "source_sample.other",
                "signature": "def other():",
                "docstring": "",
                "body": "def other():\n    return 2\n",
                "preview": "def other():",
                "symbol_type": "function",
            },
        ]
    )

    result = _run_read_code(
        tmp_path,
        "symbols",
        str(code_file),
        env=_env_with_fake_uv(tmp_path, payload),
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("# line_start")
    assert any("\ttarget\tdef target():" in line for line in lines[1:])
    assert any("\tother\tdef other():" in line for line in lines[1:])


def test_read_code_yaml_symbols_and_context_flow(tmp_path: Path) -> None:
    yaml_file = tmp_path / "command-manifest.yaml"
    yaml_file.write_text(
        "\n".join(
            [
                "version: 1",
                "commands:",
                "  read-code:",
                "    script: scripts/read-code.sh",
                "domains:",
                "  - security",
                "  - observability",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        [
            {
                "file_path": str(yaml_file),
                "line_start": 2,
                "line_end": 4,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "commands",
                "qualified_name": "command-manifest.yaml::commands",
                "signature": "commands:",
                "docstring": "commands:",
                "body": "commands:\n  read-code:\n    script: scripts/read-code.sh",
                "preview": "commands:",
                "symbol_type": "yaml_section",
            },
            {
                "file_path": str(yaml_file),
                "line_start": 5,
                "line_end": 7,
                "scope": "code",
                "record_type": "code",
                "symbol_name": "domains",
                "qualified_name": "command-manifest.yaml::domains",
                "signature": "domains:",
                "docstring": "domains:",
                "body": "domains:\n  - security\n  - observability",
                "preview": "domains:",
                "symbol_type": "yaml_section",
            },
        ]
    )

    symbols_result = _run_read_code(
        tmp_path,
        "symbols",
        str(yaml_file),
        env=_env_with_fake_uv(tmp_path, payload),
    )
    assert symbols_result.returncode == 0, symbols_result.stderr
    assert "yaml_section" in symbols_result.stdout
    assert "commands" in symbols_result.stdout

    context_result = _run_read_code(
        tmp_path,
        "context",
        str(yaml_file),
        "commands",
        "2",
        "--hud-symbol",
        env=_env_with_fake_uv(tmp_path, payload),
    )
    assert context_result.returncode == 0, context_result.stderr
    assert any(line.endswith("\tcommands:") for line in context_result.stdout.splitlines())
