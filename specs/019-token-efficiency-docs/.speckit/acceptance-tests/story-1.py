import subprocess
from pathlib import Path


def test_story1_deterministic_step_routing_contract() -> None:
    """US1: deterministic mapped routes and explicit handoff contract."""
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            "python3",
            "scripts/pipeline_driver.py",
            "--feature-id",
            "019",
            "--dry-run",
            "--phase",
            "plan",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    # RED by default until implementation exists; turns GREEN in /speckit.implement.
    assert proc.returncode == 0
    assert "Done:" in proc.stdout
    assert "Next:" in proc.stdout
    assert "Blocked:" not in proc.stdout
