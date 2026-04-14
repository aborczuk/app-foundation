import json
import subprocess
from pathlib import Path


def test_story2_agent_and_operator_outputs_match() -> None:
    """US2: CLI and MCP health surfaces must agree on next action."""
    repo = Path(__file__).resolve().parents[2]
    doctor = subprocess.run(
        [
            "bash",
            "scripts/cgc_doctor.sh",
            "--json",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    assert doctor.returncode == 0
    doctor_payload = json.loads(doctor.stdout)
    assert "status" in doctor_payload
    assert "recovery_hint" in doctor_payload
    assert doctor_payload["status"] in {"healthy", "stale", "locked", "unavailable"}
    assert doctor_payload["recovery_hint"]
    assert doctor_payload["recovery_hint"]["id"]
