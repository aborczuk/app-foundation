"""Contract-level tests for step-result envelopes and manifest routing."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _load_script_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


contracts = _load_script_module("pipeline_driver_contracts", "pipeline_driver_contracts.py")


def test_parse_step_result_accepts_minimal_envelope() -> None:
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "019:setup:test",
            "next_phase": "plan",
        }
    )
    assert parsed["schema_version"] == "1.0.0"
    assert parsed["exit_code"] == 0
    assert parsed["next_phase"] == "plan"


def test_parse_step_result_rejects_missing_schema_version() -> None:
    with pytest.raises(ValueError):
        contracts.parse_step_result(
            {
                "ok": True,
                "exit_code": 0,
                "correlation_id": "019:setup:test",
            }
        )


def test_render_status_lines_strict_three_line_contract() -> None:
    lines = contracts.render_status_lines(
        done="plan gate passed",
        next_step="run speckit.solution",
        blocked="none",
    )
    assert lines == [
        "Done: plan gate passed",
        "Next: run speckit.solution",
        "Blocked: none",
    ]
    assert tuple(contracts.STATUS_KEYS) == ("done", "next", "blocked")


def test_render_status_lines_normalizes_empty_values() -> None:
    lines = contracts.render_status_lines(done="", next_step=None, blocked="   ")
    assert lines == [
        "Done: none",
        "Next: none",
        "Blocked: none",
    ]


def test_step_result_schema_success_requires_next_phase() -> None:
    """Exit code 0 (success) requires next_phase field."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "019:plan:T001",
            "next_phase": "sketch",
        }
    )
    assert parsed["exit_code"] == 0
    assert parsed["ok"] is True
    assert parsed["next_phase"] == "sketch"


def test_step_result_schema_blocked_requires_gate_and_reasons() -> None:
    """Exit code 1 (blocked) requires gate and reasons fields."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": "019:plan:T001",
            "gate": "artifact_validation",
            "reasons": ["artifact_empty_or_minimal"],
        }
    )
    assert parsed["exit_code"] == 1
    assert parsed["ok"] is False
    assert parsed["gate"] == "artifact_validation"
    assert parsed["reasons"] == ["artifact_empty_or_minimal"]


def test_normalize_driver_mode_aliases() -> None:
    """Route-mode aliases normalize to canonical driver labels."""
    assert contracts.normalize_driver_mode(None) == "legacy"
    assert contracts.normalize_driver_mode("script") == "deterministic"
    assert contracts.normalize_driver_mode("template") == "generative"
    assert contracts.normalize_driver_mode("passthrough") == "legacy"


def test_load_driver_routes_normalizes_mode_and_emit_contracts(tmp_path: Path) -> None:
    """Manifest routes preserve normalized mode and trimmed emit contracts."""
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    driver:",
                "      mode: template",
                "      script_path: scripts/example.sh",
                "      timeout_seconds: 30",
                "    emits:",
                "      - event: example_event",
                "        required_fields:",
                "          - \" commit_sha \"",
                "          - \"qa_run_id\"",
                "  speckit.fallback:",
                "    description: \"fallback\"",
                "    emits: []",
            ]
        ),
        encoding="utf-8",
    )

    routes = contracts.load_driver_routes(manifest_path)
    assert routes["speckit.example"]["mode"] == "generative"
    assert routes["speckit.example"]["driver_managed"] is True
    assert routes["speckit.example"]["timeout_seconds"] == 30
    assert routes["speckit.example"]["emits"] == ["example_event"]
    assert routes["speckit.example"]["emit_contracts"] == [
        {"event": "example_event", "required_fields": ["commit_sha", "qa_run_id"]}
    ]
    assert routes["speckit.example"]["script_path"] == str(
        (tmp_path / "scripts" / "example.sh").resolve()
    )
    assert routes["speckit.fallback"]["mode"] == "legacy"
    assert routes["speckit.fallback"]["driver_managed"] is False


def test_load_driver_routes_rejects_unknown_driver_mode(tmp_path: Path) -> None:
    """Unknown driver modes should fail fast instead of silently falling back."""
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    driver:",
                "      mode: unsupported-mode",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        contracts.load_driver_routes(manifest_path)
    assert "unsupported driver mode" in str(exc_info.value)


@pytest.mark.parametrize(
    ("exit_code", "ok_value", "expected_message"),
    [
        (0, False, "exit_code=0 (success) requires ok=True"),
        (1, True, "exit_code=1 (blocked) requires ok=False"),
        (2, True, "exit_code=2 (error) requires ok=False"),
    ],
)
def test_step_result_schema_rejects_mismatched_ok_and_exit_code(
    exit_code: int, ok_value: bool, expected_message: str
) -> None:
    """Malformed step envelopes should fail when ok and exit_code disagree."""
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "ok": ok_value,
        "exit_code": exit_code,
        "correlation_id": "019:plan:T001",
    }
    if exit_code == 0:
        payload["next_phase"] = "sketch"
    elif exit_code == 1:
        payload["gate"] = "artifact_validation"
        payload["reasons"] = ["artifact_empty_or_minimal"]
    else:
        payload["error_code"] = "script_timeout"
        payload["debug_path"] = ".speckit/failures/019_T005_attempt_1.json"

    with pytest.raises(ValueError) as exc_info:
        contracts.parse_step_result(payload)
    assert expected_message in str(exc_info.value)


def test_step_result_schema_error_requires_error_code_and_debug_path() -> None:
    """Exit code 2 (error) requires error_code and debug_path fields."""
    parsed = contracts.parse_step_result(
        {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 2,
            "correlation_id": "019:sketch:T005",
            "error_code": "script_timeout",
            "debug_path": ".speckit/failures/019_T005_attempt_1.json",
        }
    )
    assert parsed["exit_code"] == 2
    assert parsed["ok"] is False
    assert parsed["error_code"] == "script_timeout"
    assert parsed["debug_path"] == ".speckit/failures/019_T005_attempt_1.json"


def test_step_result_schema_version_routing() -> None:
    """Schema version must match a supported version."""
    with pytest.raises(ValueError) as exc_info:
        contracts.parse_step_result(
            {
                "schema_version": "2.0.0",
                "ok": True,
                "exit_code": 0,
                "correlation_id": "019:plan:T001",
            }
        )
    assert "unsupported schema_version" in str(exc_info.value)


def test_step_result_exit_code_only_accepts_0_1_2() -> None:
    """Exit code must be exactly 0, 1, or 2."""
    for invalid_code in [-1, 3, 127, "0", None]:
        with pytest.raises(ValueError) as exc_info:
            contracts.parse_step_result(
                {
                    "schema_version": "1.0.0",
                    "ok": True,
                    "exit_code": invalid_code,
                    "correlation_id": "019:plan:T001",
                }
            )
        assert "exit_code must be one of: 0, 1, 2" in str(exc_info.value)
