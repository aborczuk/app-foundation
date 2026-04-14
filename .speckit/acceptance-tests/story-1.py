import subprocess
from pathlib import Path


def test_story1_health_check_distinguishes_states(tmp_path: Path) -> None:
    """US1: deterministic healthy/stale/locked/unavailable health reporting."""
    repo = Path(__file__).resolve().parents[2]
    healthy = subprocess.run(
        [
            "bash",
            "scripts/cgc_doctor.sh",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert healthy.returncode == 0
    assert "healthy" in healthy.stdout.lower()
    assert "recovery" in healthy.stdout.lower()

    unhealthy = subprocess.run(
        [
            "bash",
            "scripts/cgc_doctor.sh",
            "--json",
            "--project-root",
            str(tmp_path),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert unhealthy.returncode != 0
    assert "stale" in unhealthy.stdout.lower() or "locked" in unhealthy.stdout.lower()
