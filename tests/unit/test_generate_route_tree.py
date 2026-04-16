from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_generate_route_tree_creates_route_doc(tmp_path: Path) -> None:
    """Ensure the generator emits a route tree for a symbolized script helper."""
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / ".specify" / "scripts" / "python" / "generate_route_tree.py"
    output = tmp_path / "route-tree.md"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            "scripts/read_code.py",
            "--kind",
            "script",
            "--symbol",
            "read_code_context",
            "--output",
            str(output),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "Route Tree: read_code.read_code_context (script)" in text
    assert "scripts/read_code.py" in text
    assert "scripts/read-code.sh" in text
    assert "scripts/read_code.py" in text
    assert "Progressive Load" in text
