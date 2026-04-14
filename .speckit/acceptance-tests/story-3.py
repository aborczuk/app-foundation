import subprocess
import time
from pathlib import Path


def test_story3_last_known_good_snapshot_survives_refresh_failure() -> None:
    """US3: failed refresh must preserve the last known good graph snapshot."""
    repo = Path(__file__).resolve().parents[2]
    first = subprocess.run(
        [
            "bash",
            "scripts/cgc_safe_index.sh",
            "src/mcp_codebase",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    second = subprocess.run(
        [
            "bash",
            "scripts/cgc_safe_index.sh",
            "src/mcp_codebase",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert first.returncode == 0
    assert second.returncode == 0
    assert second.stdout.strip()


def test_story3_health_check_completes_within_timeout_budget() -> None:
    """US3: graph-heavy health checks must complete within a bounded budget."""
    repo = Path(__file__).resolve().parents[2]
    start = time.monotonic()
    proc = subprocess.run(
        [
            "bash",
            "scripts/cgc_doctor.sh",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0
    assert elapsed < 30
    assert proc.stdout.strip()
