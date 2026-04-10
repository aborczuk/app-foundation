import json
import subprocess
from pathlib import Path


def test_story2_compact_parsing_contract() -> None:
    """US2: exit-code-first parsing with compact status contract."""
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            "python3",
            "scripts/pipeline_driver.py",
            "--feature-id",
            "019",
            "--dry-run",
            "--phase",
            "solution",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["exit_code"] in (0, 1, 2)
    assert "correlation_id" in payload
