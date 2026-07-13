"""Unit tests for the mcp_clickup CLI entrypoint."""

from __future__ import annotations

import json

from src.mcp_clickup import __main__ as clickup_main


def test_main_emits_bootstrap_json_result(monkeypatch, capsys) -> None:
    """CLI JSON mode should emit the structured bootstrap result payload."""
    monkeypatch.setattr(
        clickup_main,
        "run_bootstrap_result",
        lambda: {
            "mode": "bootstrap",
            "ok": True,
            "exit_code": 0,
            "space_id": "space-1",
            "error_code": None,
            "message": None,
        },
    )

    exit_code = clickup_main.main(["--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "mode": "bootstrap",
        "ok": True,
        "exit_code": 0,
        "space_id": "space-1",
        "error_code": None,
        "message": None,
    }


def test_main_emits_status_json_result(monkeypatch, capsys) -> None:
    """CLI JSON mode should emit the structured status result payload."""
    monkeypatch.setattr(
        clickup_main,
        "run_status_result",
        lambda: {
            "mode": "status",
            "ok": False,
            "exit_code": 1,
            "space_id": "space-1",
            "error_code": "manifest_missing",
            "message": "Manifest file does not exist",
        },
    )

    exit_code = clickup_main.main(["--status", "--json"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "mode": "status",
        "ok": False,
        "exit_code": 1,
        "space_id": "space-1",
        "error_code": "manifest_missing",
        "message": "Manifest file does not exist",
    }
