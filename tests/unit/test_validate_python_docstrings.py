from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validate_python_docstrings_flags_private_helper_without_docstring(tmp_path: Path) -> None:
    """Ensure private helpers without docstrings fail validation."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "validate_python_docstrings.py"
    sample = tmp_path / "sample.py"
    sample.write_text(
        """\
def public_function():
    \"\"\"Public docstring.\"\"\"
    return 1


def _private_helper():
    return 2
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(sample)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "missing_docstring:_private_helper" in result.stdout


def test_validate_python_docstrings_accepts_all_documented_functions(tmp_path: Path) -> None:
    """Ensure documented private and public helpers pass validation."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "scripts" / "validate_python_docstrings.py"
    sample = tmp_path / "sample_ok.py"
    sample.write_text(
        """\
\"\"\"Module docstring.\"\"\"


def public_function():
    \"\"\"Public docstring.\"\"\"
    return 1


def _private_helper():
    \"\"\"Private helper docstring.\"\"\"
    return 2
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(sample)],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
