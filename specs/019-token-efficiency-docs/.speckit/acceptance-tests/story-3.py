import json
import subprocess
from pathlib import Path


def test_story3_migration_safety_and_coverage_gate() -> None:
    """US3: uncovered command->script mappings must fail deterministic coverage checks."""
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            "python3",
            "scripts/validate_command_script_coverage.py",
            "--manifest",
            "command-manifest.yaml",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["error_count"] == 0
