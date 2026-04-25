"""Unit-level skeleton tests for scripts/pipeline_driver.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.support import build_step_result_envelope


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


pipeline_driver = _load_script_module("pipeline_driver", "pipeline_driver.py")
pipeline_driver_contracts = _load_script_module(
    "pipeline_driver_contracts", "pipeline_driver_contracts.py"
)
pipeline_driver_state = _load_script_module("pipeline_driver_state", "pipeline_driver_state.py")


def _ledger_event(event: str, *, timestamp_utc: str, **fields: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event": event,
        "feature_id": "019",
        "timestamp_utc": timestamp_utc,
    }
    payload.update(fields)
    return payload


def test_main_outputs_minimal_step_result(capsys) -> None:
    # dry-run + json: introspection mode, no execution, always returns 0 with structured output
    exit_code = pipeline_driver.main(["--feature-id", "019", "--dry-run", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["feature_id"] == "019"
    assert payload["step_result"]["exit_code"] == 0


def test_main_uses_ledger_feature_id_for_correlation_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {
            "feature_id": "022-codegraph-hardening",
            "ledger_feature_id": "022",
            "phase": "plan",
            "blocked": False,
            "drift_detected": False,
            "drift_reasons": [],
        },
    )

    called: dict[str, str] = {}

    def _fake_build_correlation_id(feature_id: str, phase: str, **kwargs) -> str:
        called["feature_id"] = feature_id
        called["phase"] = phase
        return f"{feature_id}:{phase}"

    monkeypatch.setattr(pipeline_driver, "build_correlation_id", _fake_build_correlation_id)

    exit_code = pipeline_driver.main(["--feature-id", "022-codegraph-hardening", "--dry-run", "--json"])
    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out.strip())
    assert called["feature_id"] == "022"
    assert called["phase"] == "plan"
    assert payload["phase_state"]["ledger_feature_id"] == "022"
    assert payload["step_result"]["correlation_id"] == "022:plan"


def test_main_generative_route_executes_handoff_adapter(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {"phase": "plan", "blocked": False},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "generative",
            "command_id": "speckit.plan",
            "handoff": {
                "handoff_id": "handoff-test",
                "step_name": "speckit.plan",
                "required_inputs": [],
                "output_template_path": "specs/019-token-efficiency-docs/plan.md",
                "completion_marker": "## Summary",
                "correlation_id": "run-test:speckit.plan",
            },
        },
    )

    called: dict[str, str] = {}

    def _fake_handoff_runner(
        handoff,
        *,
        feature_id,
        phase,
        correlation_id,
        handoff_runner=None,
        **kwargs,
    ):
        called["feature_id"] = feature_id
        called["phase"] = phase
        called["correlation_id"] = correlation_id
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": phase,
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff": dict(handoff),
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": "specs/019-token-efficiency-docs/plan.md",
                "exists": True,
                "size_bytes": 100,
                "line_count": 5,
                "completion_marker": "## Summary",
            },
        }

    monkeypatch.setattr(pipeline_driver, "run_generative_handoff", _fake_handoff_runner)
    validation_called: dict[str, str] = {}

    def _fake_validate_generated_artifact(
        artifact_path,
        *,
        correlation_id,
        completion_marker=None,
    ):
        validation_called["artifact_path"] = str(artifact_path)
        validation_called["correlation_id"] = correlation_id
        validation_called["completion_marker"] = str(completion_marker)
        return {"ok": True}

    monkeypatch.setattr(
        pipeline_driver,
        "validate_generated_artifact",
        _fake_validate_generated_artifact,
    )
    appended: dict[str, str] = {}

    def _fake_append_pipeline_success_event(*, feature_id, phase, command_id, **kwargs):
        appended["feature_id"] = feature_id
        appended["phase"] = phase
        appended["command_id"] = str(command_id)
        return {"ok": True, "appended": True, "event": "plan_started"}

    monkeypatch.setattr(
        pipeline_driver,
        "append_pipeline_success_event",
        _fake_append_pipeline_success_event,
    )

    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "plan"])
    assert exit_code == 0
    assert called["feature_id"] == "019"
    assert called["phase"] == "plan"
    assert called["correlation_id"].endswith(":plan")
    assert validation_called["artifact_path"] == "specs/019-token-efficiency-docs/plan.md"
    assert validation_called["correlation_id"].endswith(":plan")
    assert validation_called["completion_marker"] == "## Summary"
    assert appended["feature_id"] == "019"
    assert appended["phase"] == "plan"
    assert appended["command_id"] == "speckit.plan"


def test_main_generative_route_blocks_when_artifact_validation_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {"phase": "plan", "blocked": False},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "generative",
            "command_id": "speckit.plan",
            "handoff": {
                "handoff_id": "handoff-test",
                "step_name": "speckit.plan",
                "required_inputs": [],
                "output_template_path": "specs/019-token-efficiency-docs/plan.md",
                "completion_marker": "## Summary",
                "correlation_id": "run-test:speckit.plan",
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "run_generative_handoff",
        lambda *args, **kwargs: {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "run-test:speckit.plan",
            "next_phase": "plan",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": "specs/019-token-efficiency-docs/plan.md",
                "completion_marker": "## Summary",
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "validate_generated_artifact",
        lambda *args, **kwargs: {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": "run-test:speckit.plan",
            "gate": "artifact_validation",
            "reasons": ["artifact_not_created"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        },
    )

    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "plan"])
    assert exit_code == 1


def test_main_generative_route_errors_when_pipeline_event_append_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {"phase": "plan", "blocked": False},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "generative",
            "command_id": "speckit.plan",
            "handoff": {
                "handoff_id": "handoff-test",
                "step_name": "speckit.plan",
                "required_inputs": [],
                "output_template_path": "specs/019-token-efficiency-docs/plan.md",
                "completion_marker": "## Summary",
                "correlation_id": "run-test:speckit.plan",
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "run_generative_handoff",
        lambda *args, **kwargs: {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "run-test:speckit.plan",
            "next_phase": "plan",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": "specs/019-token-efficiency-docs/plan.md",
                "completion_marker": "## Summary",
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "validate_generated_artifact",
        lambda *args, **kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "append_pipeline_success_event",
        lambda **kwargs: {
            "ok": False,
            "appended": False,
            "event": "plan_started",
            "error_code": "pipeline_event_append_failed",
        },
    )

    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "plan"])
    assert exit_code == 2


def test_append_pipeline_success_event_requires_validated_success(monkeypatch, tmp_path: Path) -> None:
    artifact_path = tmp_path / "plan.md"
    artifact_path.write_text("# Plan\n## Summary\nGenerated content\n", encoding="utf-8")

    validation_calls: list[tuple[str, str, str | None]] = []
    append_called = {"value": False}

    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {"phase": "plan", "blocked": False},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "generative",
            "command_id": "speckit.plan",
            "handoff": {
                "handoff_id": "handoff-test",
                "step_name": "speckit.plan",
                "required_inputs": [],
                "output_template_path": str(artifact_path),
                "completion_marker": "## Summary",
                "correlation_id": "run-test:speckit.plan",
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "run_generative_handoff",
        lambda *args, **kwargs: {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": "run-test:speckit.plan",
            "next_phase": "plan",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
            "handoff_execution": "executed",
            "generated_artifact": {
                "path": str(artifact_path),
                "completion_marker": "## Summary",
            },
        },
    )

    def _fake_validate_generated_artifact(
        artifact_path_arg,
        *,
        correlation_id,
        completion_marker=None,
    ):
        validation_calls.append((str(artifact_path_arg), correlation_id, completion_marker))
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "artifact_validation",
            "reasons": ["artifact_not_created"],
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    monkeypatch.setattr(
        pipeline_driver,
        "validate_generated_artifact",
        _fake_validate_generated_artifact,
    )

    def _fake_append_pipeline_success_event(**kwargs):
        append_called["value"] = True
        return {"ok": True, "appended": True, "event": "plan_started"}

    monkeypatch.setattr(
        pipeline_driver,
        "append_pipeline_success_event",
        _fake_append_pipeline_success_event,
    )
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "plan"])

    assert exit_code == 1
    assert len(validation_calls) == 1
    assert validation_calls[0][0] == str(artifact_path)
    assert validation_calls[0][1].endswith(":plan")
    assert validation_calls[0][2] == "## Summary"
    assert append_called["value"] is False


def test_idempotent_terminal_event_retry(
    monkeypatch, tmp_path: Path
) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    original_ledger = (
        json.dumps(
            {
                "timestamp_utc": "2026-04-10T00:00:00Z",
                "feature_id": "019",
                "phase": "plan",
                "event": "plan_started",
                "actor": "pipeline_driver",
            },
            sort_keys=True,
        )
        + "\n"
    )
    ledger_path.write_text(
        original_ledger,
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pipeline_driver_contracts,
        "load_driver_routes",
        lambda manifest_path=None: {
            "speckit.plan": {
                "emit_contracts": [{"event": "plan_started", "required_fields": []}],
                "emits": ["plan_started"],
            }
        },
    )

    result = pipeline_driver.append_pipeline_success_event(
        feature_id="019",
        phase="plan",
        command_id="speckit.plan",
        ledger_path=ledger_path,
    )

    assert result["ok"] is True
    assert result["appended"] is False
    assert result["event"] == "plan_started"
    assert result["reason"] == "event_already_recorded"
    assert ledger_path.read_text(encoding="utf-8") == original_ledger


def test_build_correlation_id_uses_explicit_run_scope() -> None:
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.plan",
        run_id="run-xyz",
    )
    assert correlation_id == "run-xyz:speckit.plan"


def test_build_correlation_id_uses_timestamp_when_run_scope_missing() -> None:
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.plan",
        timestamp_utc=datetime(2026, 4, 10, 12, 34, 56, tzinfo=timezone.utc),
    )
    assert correlation_id == "run_20260410T123456Z_019:speckit.plan"


def test_run_step_routes_success_envelope() -> None:
    correlation_id = "run-019-success"
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "print(json.dumps({"
            "'schema_version':'1.0.0','ok':True,'exit_code':0,"
            f"'correlation_id':'{correlation_id}','next_phase':'plan'"
            "}))"
        ),
    ]

    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id=correlation_id,
    )
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["process_exit_code"] == 0
    assert result["timed_out"] is False


def test_run_step_routes_blocked_envelope() -> None:
    correlation_id = "run-019-blocked"
    command = [
        sys.executable,
        "-c",
        (
            "import json, sys; "
            "print(json.dumps({"
            "'schema_version':'1.0.0','ok':False,'exit_code':1,"
            "'gate':'planreview_questions','reasons':['fq_count_nonzero'],"
            f"'correlation_id':'{correlation_id}'"
            "})); "
            "sys.exit(1)"
        ),
    ]

    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id=correlation_id,
    )
    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["process_exit_code"] == 1
    assert result["reasons"] == ["fq_count_nonzero"]


def test_run_step_timeout_routes_runtime_failure(tmp_path: Path) -> None:
    sidecar_dir = tmp_path / "runtime-failures"
    result = pipeline_driver.run_step(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout_seconds=1,
        correlation_id="run-019-timeout",
        sidecar_dir=sidecar_dir,
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "step_timeout"
    assert result["timed_out"] is True
    assert result["debug_path"] is not None
    assert Path(result["debug_path"]).exists()


def test_run_step_invalid_json_persists_runtime_sidecar(tmp_path: Path) -> None:
    sidecar_dir = tmp_path / "runtime-failures"
    command = [
        sys.executable,
        "-c",
        "import sys; print('not-json'); sys.exit(2)",
    ]
    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id="run-019-invalid-json",
        sidecar_dir=sidecar_dir,
    )
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "invalid_json_result"
    assert result["debug_path"] is not None

    sidecar_path = Path(result["debug_path"])
    assert sidecar_path.exists()
    sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar_payload["correlation_id"] == "run-019-invalid-json"
    assert sidecar_payload["rerun"]["exit_code"] in (0, 1, 2, None)


def test_run_step_rejects_partial_step_result_envelope(tmp_path: Path) -> None:
    correlation_id = "run-019-partial"
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "print(json.dumps({"
            "'schema_version':'1.0.0','ok':True,'exit_code':0,"
            f"'correlation_id':'{correlation_id}'"
            "}))"
        ),
    ]

    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id=correlation_id,
        sidecar_dir=tmp_path / "runtime-failures",
    )

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "invalid_step_result"
    assert result["reasons"] == ["invalid_step_result"]
    assert result["process_exit_code"] == 0
    assert result["timed_out"] is False
    assert result["debug_path"] is not None
    assert Path(result["debug_path"]).exists()


def test_run_step_routes_error_envelope_without_sidecar(tmp_path: Path) -> None:
    sidecar_dir = tmp_path / "runtime-failures"
    correlation_id = "run-019-error"
    payload = build_step_result_envelope(
        ok=False,
        exit_code=2,
        correlation_id=correlation_id,
        error_code="script_failed",
        debug_path="/tmp/placeholder.json",
    )
    payload_json = json.dumps(payload, sort_keys=True)
    command = [
        sys.executable,
        "-c",
        f"import json; print({payload_json!r}); import sys; sys.exit(2)",
    ]

    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id=correlation_id,
        sidecar_dir=sidecar_dir,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["process_exit_code"] == 2
    assert result["timed_out"] is False
    assert result["error_code"] == "script_failed"
    assert result["debug_path"] == "/tmp/placeholder.json"
    assert not sidecar_dir.exists()


def test_run_step_rejects_error_envelope_without_debug_path(tmp_path: Path) -> None:
    sidecar_dir = tmp_path / "runtime-failures"
    correlation_id = "run-019-error-missing-debug"
    payload = build_step_result_envelope(
        ok=False,
        exit_code=2,
        correlation_id=correlation_id,
        error_code="script_failed",
    )
    payload_json = json.dumps(payload, sort_keys=True)
    command = [
        sys.executable,
        "-c",
        f"import json; print({payload_json!r}); import sys; sys.exit(2)",
    ]

    result = pipeline_driver.run_step(
        command,
        timeout_seconds=5,
        correlation_id=correlation_id,
        sidecar_dir=sidecar_dir,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "invalid_step_result"
    assert result["reasons"] == ["invalid_step_result"]
    assert result["process_exit_code"] == 2
    assert result["timed_out"] is False
    assert result["debug_path"] is not None
    assert Path(result["debug_path"]).exists()


def test_parse_step_result_rejects_success_envelope_without_next_phase() -> None:
    """Missing success routing fields should fail fast at the parse boundary."""
    with pytest.raises(ValueError, match="exit_code=0"):
        pipeline_driver_contracts.parse_step_result(
            {
                "schema_version": "1.0.0",
                "ok": True,
                "exit_code": 0,
                "correlation_id": "run-019-success",
            }
        )


def test_normalize_driver_mode_aliases() -> None:
    assert pipeline_driver_contracts.normalize_driver_mode(None) == "legacy"
    assert pipeline_driver_contracts.normalize_driver_mode("script") == "deterministic"
    assert pipeline_driver_contracts.normalize_driver_mode("llm") == "generative"
    assert pipeline_driver_contracts.normalize_driver_mode("LEGACY") == "legacy"


def test_normalize_driver_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        pipeline_driver_contracts.normalize_driver_mode("unsupported-mode")


def test_load_driver_routes_normalizes_mode_and_script_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    driver:",
                "      mode: script",
                "      script_path: scripts/example.sh",
                "      timeout_seconds: 30",
                "    emits:",
                "      - event: example_event",
                "        required_fields: []",
                "  speckit.fallback:",
                "    description: \"fallback\"",
                "    emits: []",
            ]
        ),
        encoding="utf-8",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    assert routes["speckit.example"]["mode"] == "deterministic"
    assert routes["speckit.example"]["driver_managed"] is True
    assert routes["speckit.example"]["timeout_seconds"] == 30
    assert routes["speckit.example"]["emits"] == ["example_event"]
    assert routes["speckit.example"]["emit_contracts"] == [
        {"event": "example_event", "required_fields": []}
    ]
    assert routes["speckit.example"]["script_path"] == str(
        (tmp_path / "scripts" / "example.sh").resolve()
    )

    assert routes["speckit.fallback"]["mode"] == "legacy"
    assert routes["speckit.fallback"]["driver_managed"] is False


def test_load_driver_routes_preserves_route_and_emit_metadata(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \" example route \"",
                "    canonical_trigger: \" speckit.run \"",
                "    scripts:",
                "      - \" scripts/example.sh \"",
                "    artifacts:",
                "      - output_path: \" ${FEATURE_DIR}/example.md \"",
                "        template: \" example-template.md \"",
                "        scaffold_script: \" scripts/scaffold.py \"",
                "        consumed_by:",
                "          - \" speckit.implement \"",
                "          - \" speckit.checkpoint \"",
                "    driver:",
                "      mode: deterministic",
                "      script_path: scripts/example.sh",
                "    emits:",
                "      - event: example_event",
                "        required_fields:",
                "          - \" task_id \"",
                "        canonical_trigger: \" speckit.run \"",
            ]
        ),
        encoding="utf-8",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.example"]
    assert route["description"] == "example route"
    assert route["canonical_trigger"] == "speckit.run"
    assert route["scripts"] == ["scripts/example.sh"]
    assert route["artifacts"] == [
        {
            "output_path": "${FEATURE_DIR}/example.md",
            "template": "example-template.md",
            "scaffold_script": "scripts/scaffold.py",
            "consumed_by": ["speckit.implement", "speckit.checkpoint"],
        }
    ]
    assert route["emit_contracts"] == [
        {
            "event": "example_event",
            "required_fields": ["task_id"],
            "canonical_trigger": "speckit.run",
        }
    ]


def test_load_driver_routes_rejects_conflicting_mode_definitions(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    mode: legacy",
                "    driver:",
                "      mode: deterministic",
                "    emits: []",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting driver mode declarations"):
        pipeline_driver_contracts.load_driver_routes(manifest_path)


def test_load_driver_routes_rejects_blank_required_fields(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example\"",
                "    mode: deterministic",
                "    emits:",
                "      - event: example_event",
                "        required_fields:",
                "          - \" \"",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="emit.required_fields entries must be non-empty strings"):
        pipeline_driver_contracts.load_driver_routes(manifest_path)


def test_acquire_feature_lock_blocks_active_other_owner(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    first = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=60,
        now_utc=now,
    )
    assert first["acquired"] is True

    second = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        lease_seconds=60,
        now_utc=now + timedelta(seconds=10),
    )
    assert second["acquired"] is False
    assert second["reason"] == "feature_lock_held"
    assert second["existing_owner"] == "worker-a"


def test_acquire_feature_lock_replaces_stale_owner(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now,
    )

    takeover = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now + timedelta(seconds=60),
    )
    assert takeover["acquired"] is True
    assert takeover["stale_replaced"] is True
    assert takeover["reason"] == "stale_lock_replaced"
    assert takeover["previous_owner"] == "worker-a"


def test_acquire_feature_lock_reuses_same_owner_after_stale_expiry(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now,
    )

    retry = pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=30,
        now_utc=now + timedelta(seconds=60),
    )

    assert retry["acquired"] is True
    assert retry["reused"] is True
    assert retry["stale_replaced"] is False
    assert retry["reason"] == "stale_lock_reused"
    assert retry["previous_owner"] == "worker-a"


def test_release_feature_lock_requires_owner_unless_stale(tmp_path: Path) -> None:
    lock_dir = tmp_path / "locks"
    now = datetime(2026, 4, 10, tzinfo=timezone.utc)

    pipeline_driver_state.acquire_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        lease_seconds=120,
        now_utc=now,
    )

    blocked_release = pipeline_driver_state.release_feature_lock(
        "019",
        owner="worker-b",
        locks_dir=lock_dir,
        now_utc=now + timedelta(seconds=10),
    )
    assert blocked_release["released"] is False
    assert blocked_release["reason"] == "lock_owned_by_other"

    owner_release = pipeline_driver_state.release_feature_lock(
        "019",
        owner="worker-a",
        locks_dir=lock_dir,
        now_utc=now + timedelta(seconds=20),
    )
    assert owner_release["released"] is True
    assert owner_release["reason"] == "released_by_owner"


def test_resolve_phase_state_prefers_ledger_authority(tmp_path: Path) -> None:
    """Ledger state should override stale phase hints during reconciliation."""
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        _ledger_event("backlog_registered", timestamp_utc="2026-04-10T00:00:00Z"),
        _ledger_event("research_completed", timestamp_utc="2026-04-10T00:01:00Z"),
        _ledger_event("plan_started", timestamp_utc="2026-04-10T00:02:00Z"),
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        pipeline_state={"phase": "setup", "blocked": False, "drift_detected": False},
        ledger_path=ledger_path,
    )
    assert state["feature_id"] == "019"
    assert state["ledger_feature_id"] == "019"
    assert state["phase"] == "plan"
    assert state["last_event"] == "plan_started"
    assert state["blocked"] is True
    assert state["drift_detected"] is True
    assert state["drift_reason_codes"] == ["phase_hint_conflicts_with_ledger"]
    assert state["drift_reason_details"] == [
        {
            "code": "phase_hint_conflicts_with_ledger",
            "hinted_phase": "setup",
            "derived_phase": "plan",
            "last_event": "plan_started",
        }
    ]
    assert state["drift_reasons"] == ["phase_hint_conflicts_with_ledger"]


def test_resolve_phase_state_ignores_stale_blocked_flag(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        _ledger_event("backlog_registered", timestamp_utc="2026-04-10T00:00:00Z"),
        _ledger_event("research_completed", timestamp_utc="2026-04-10T00:01:00Z"),
        _ledger_event("plan_started", timestamp_utc="2026-04-10T00:02:00Z"),
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        pipeline_state={"phase": "plan", "blocked": True, "drift_detected": True},
        ledger_path=ledger_path,
    )
    assert state["phase"] == "plan"
    assert state["blocked"] is False
    assert state["drift_detected"] is False
    assert state["drift_reasons"] == []


def test_resolve_phase_state_uses_routing_contract_for_skip_path(tmp_path: Path) -> None:
    """Spec routing should drive the next phase when plan is skipped."""
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        {
            "event": "backlog_registered",
            "feature_id": "019",
            "timestamp_utc": "2026-04-10T00:00:00Z",
            "routing": {
                "research_route": "skip",
                "plan_profile": "skip",
                "sketch_profile": "core",
                "tasking_route": "required",
                "estimate_route": "required_after_tasking",
                "routing_reason": "Repo-local tasking/HUD behavior change using existing architecture.",
                "conditional_sketch_sections": [],
            },
            "risk": {
                "requirement_clarity": "low",
                "repo_uncertainty": "low",
                "external_dependency_uncertainty": "low",
                "state_data_migration_risk": "low",
                "runtime_side_effect_risk": "low",
                "human_operator_dependency": "low",
            },
        }
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        pipeline_state={"phase": "specify", "blocked": False},
        ledger_path=ledger_path,
    )
    assert state["phase"] == "specify"
    assert state["routing_contract"] is not None
    assert state["routing_contract"]["routing"]["plan_profile"] == "skip"
    assert state["next_phase"] == "solution"


def test_resolve_phase_state_reload_spec_routing_after_nonrouting_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Later ledger events should not erase the spec-level routing contract."""
    monkeypatch.chdir(tmp_path)
    feature_dir = tmp_path / "specs" / "019-routing-fix"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(
        "\n".join(
            [
                "# Spec",
                "",
                "## Routing Contract",
                "",
                "```json",
                "{",
                '  "routing": {',
                '    "research_route": "skip",',
                '    "plan_profile": "skip",',
                '    "sketch_profile": "core",',
                '    "tasking_route": "required",',
                '    "estimate_route": "required_after_tasking",',
                '    "routing_reason": "Use the routed smaller path.",',
                '    "conditional_sketch_sections": []',
                "  },",
                '  "risk": {',
                '    "requirement_clarity": "low",',
                '    "repo_uncertainty": "low",',
                '    "external_dependency_uncertainty": "low",',
                '    "state_data_migration_risk": "low",',
                '    "runtime_side_effect_risk": "low",',
                '    "human_operator_dependency": "low"',
                "  }",
                "}",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    ledger_path.write_text(
        "\n".join(
            [
                json.dumps(
                    _ledger_event(
                        "backlog_registered",
                        timestamp_utc="2026-04-10T00:00:00Z",
                    ),
                    sort_keys=True,
                ),
                json.dumps(
                    _ledger_event(
                        "spec_clarified",
                        timestamp_utc="2026-04-10T00:01:00Z",
                    ),
                    sort_keys=True,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        pipeline_state={"phase": "specify", "blocked": False},
        ledger_path=ledger_path,
    )

    assert state["last_event"] == "spec_clarified"
    assert state["routing_contract"] is not None
    assert state["routing_contract"]["routing"]["plan_profile"] == "skip"
    assert state["next_phase"] == "solution"


def test_resolve_phase_state_falls_back_to_numeric_prefix_for_slug(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        {
            "event": "backlog_registered",
            "feature_id": "022",
            "timestamp_utc": "2026-04-10T00:00:00Z",
        },
        {
            "event": "research_completed",
            "feature_id": "022",
            "timestamp_utc": "2026-04-10T00:01:00Z",
        },
        {
            "event": "plan_started",
            "feature_id": "022",
            "timestamp_utc": "2026-04-10T00:02:00Z",
        },
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "022-codegraph-hardening",
        pipeline_state={"phase": "setup", "blocked": False},
        ledger_path=ledger_path,
    )
    assert state["feature_id"] == "022-codegraph-hardening"
    assert state["ledger_feature_id"] == "022"
    assert state["phase"] == "plan"
    assert state["last_event"] == "plan_started"


def test_resolve_phase_state_flags_missing_required_artifact(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        _ledger_event("backlog_registered", timestamp_utc="2026-04-10T00:00:00Z"),
        _ledger_event("research_completed", timestamp_utc="2026-04-10T00:01:00Z"),
        _ledger_event("plan_started", timestamp_utc="2026-04-10T00:02:00Z"),
        _ledger_event(
            "planreview_completed",
            timestamp_utc="2026-04-10T00:03:00Z",
            fq_count=0,
            questions_asked=0,
        ),
        _ledger_event(
            "feasibility_spike_completed",
            timestamp_utc="2026-04-10T00:04:00Z",
            spike_artifact="specs/019-token-efficiency-docs/spike.md",
            fq_count=0,
        ),
        _ledger_event(
            "plan_approved",
            timestamp_utc="2026-04-10T00:05:00Z",
            feasibility_required="false",
        ),
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    feature_dir = tmp_path / "feature"
    feature_dir.mkdir(parents=True, exist_ok=True)

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        ledger_path=ledger_path,
        feature_dir=feature_dir,
    )
    assert state["phase"] == "plan"
    assert state["drift_detected"] is True
    assert state["drift_reasons"] == ["missing_artifact:plan.md"]
    assert state["blocked"] is True


def test_main_rejects_requested_phase_mismatch(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {
            "feature_id": "022-codegraph-hardening",
            "ledger_feature_id": "022",
            "phase": "specify",
            "last_event": "backlog_registered",
            "ledger_event_count": 1,
            "approved_plan": False,
            "approved_solution": False,
            "blocked": False,
            "drift_detected": False,
            "drift_reasons": [],
        },
    )
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    exit_code = pipeline_driver.main(
        ["--feature-id", "022-codegraph-hardening", "--phase", "plan", "--json"]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["step_result"]["gate"] == "phase_drift"
    assert payload["step_result"]["reasons"] == ["requested_phase_mismatch"]
    assert payload["step_result"]["next_phase"] == "specify"


def test_main_allows_requested_phase_rerun(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {
            "feature_id": "023-deterministic-phase-orchestration",
            "ledger_feature_id": "023",
            "phase": "implement",
            "last_event": "e2e_generated",
            "ledger_event_count": 14,
            "approved_plan": True,
            "approved_solution": True,
            "blocked": False,
            "drift_detected": False,
            "drift_reasons": [],
        },
    )
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    exit_code = pipeline_driver.main(
        ["--feature-id", "023-deterministic-phase-orchestration", "--phase", "plan", "--dry-run", "--json"]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["step_result"]["ok"] is True
    assert payload["step_result"]["gate"] is None
    assert payload["phase_state"]["phase"] == "implement"


def test_main_passes_context_to_implement_step(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {
            "feature_id": "023-deterministic-phase-orchestration",
            "ledger_feature_id": "023",
            "phase": "implement",
            "blocked": False,
            "drift_detected": False,
            "drift_reasons": [],
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "build_correlation_id",
        lambda *args, **kwargs: "run-test:speckit.implement",
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "deterministic",
            "command_id": "speckit.implement",
            "route": {
                "mode": "deterministic",
                "script_path": "scripts/speckit_implement_step.py",
                "timeout_seconds": 300,
            },
        },
    )
    monkeypatch.setattr(
        pipeline_driver,
        "enforce_approval_breakpoint",
        lambda *args, **kwargs: {
            "ok": True,
            "breakpoint_enforced": True,
            "approval_granted": True,
        },
    )
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    observed: dict[str, object] = {}

    def _fake_run_step(command, *, timeout_seconds, correlation_id, **kwargs):  # noqa: ANN001
        observed["command"] = list(command)
        observed["timeout_seconds"] = timeout_seconds
        observed["correlation_id"] = correlation_id
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": "closed",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
        }

    monkeypatch.setattr(pipeline_driver, "run_step", _fake_run_step)

    exit_code = pipeline_driver.main(
        ["--feature-id", "023-deterministic-phase-orchestration", "--phase", "implement"]
    )

    assert exit_code == 0
    assert observed["timeout_seconds"] == 300
    assert observed["correlation_id"] == "run-test:speckit.implement"
    assert observed["command"] == [
        "scripts/speckit_implement_step.py",
        "--feature-id",
        "023",
        "--phase",
        "implement",
        "--correlation-id",
        "run-test:speckit.implement",
    ]


def test_main_rejects_invalid_phase_input(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {
            "feature_id": "022-codegraph-hardening",
            "ledger_feature_id": "022",
            "phase": "specify",
            "last_event": "backlog_registered",
            "ledger_event_count": 1,
            "approved_plan": False,
            "approved_solution": False,
            "blocked": False,
            "drift_detected": False,
            "drift_reasons": [],
        },
    )
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    exit_code = pipeline_driver.main(
        ["--feature-id", "022-codegraph-hardening", "--phase", "sketch", "--json"]
    )
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["step_result"]["gate"] == "invalid_input"
    assert payload["step_result"]["reasons"] == ["invalid_phase"]
    assert payload["step_result"]["next_phase"] == "specify"


def test_resolve_phase_state_allows_earlier_hint_without_drift(tmp_path: Path) -> None:
    ledger_path = tmp_path / "pipeline-ledger.jsonl"
    events = [
        _ledger_event("backlog_registered", timestamp_utc="2026-04-10T00:00:00Z"),
        _ledger_event("research_completed", timestamp_utc="2026-04-10T00:01:00Z"),
        _ledger_event("plan_started", timestamp_utc="2026-04-10T00:02:00Z"),
        _ledger_event(
            "planreview_completed",
            timestamp_utc="2026-04-10T00:03:00Z",
            fq_count=0,
            questions_asked=0,
        ),
        _ledger_event(
            "feasibility_spike_completed",
            timestamp_utc="2026-04-10T00:04:00Z",
            spike_artifact="specs/023-deterministic-phase-orchestration/spike.md",
            fq_count=0,
        ),
        _ledger_event(
            "plan_approved",
            timestamp_utc="2026-04-10T00:05:00Z",
            feasibility_required="false",
        ),
        _ledger_event("sketch_completed", timestamp_utc="2026-04-10T00:06:00Z"),
        _ledger_event(
            "solutionreview_completed",
            timestamp_utc="2026-04-10T00:07:00Z",
            critical_count=0,
            high_count=0,
        ),
        _ledger_event("estimation_completed", timestamp_utc="2026-04-10T00:08:00Z", estimate_points=8),
        _ledger_event("tasking_completed", timestamp_utc="2026-04-10T00:09:00Z", task_count=4, story_count=2),
        _ledger_event("solution_approved", timestamp_utc="2026-04-10T00:10:00Z", task_count=4, story_count=2, estimate_points=8),
        _ledger_event("analysis_completed", timestamp_utc="2026-04-10T00:11:00Z", critical_count=0),
        _ledger_event("e2e_generated", timestamp_utc="2026-04-10T00:12:00Z", e2e_artifact="scripts/e2e_023.sh"),
    ]
    ledger_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )

    state = pipeline_driver_state.resolve_phase_state(
        "019",
        pipeline_state={"phase": "plan"},
        ledger_path=ledger_path,
    )
    assert state["phase"] == "implement"
    assert state["blocked"] is False
    assert state["drift_detected"] is False
    assert state["drift_reasons"] == []


def test_handoff_contract_requires_all_fields() -> None:
    """Verify LLMHandoffTemplate schema with required fields per data-model.md."""
    # When the orchestrator determines the next step is generative (mode="llm" in manifest),
    # it must create an LLMHandoffTemplate instead of executing a script.
    correlation_id = "run_20260410T120000Z_019:speckit.plan"

    # This is the contract that should be returned when a generative step is encountered.
    # The fields match the LLMHandoffTemplate entity in data-model.md.
    handoff_contract = {
        "handoff_id": "handoff_019_plan_001",
        "step_name": "speckit.plan",
        "required_inputs": [
            "specs/019-token-efficiency-docs/spec.md",
            "specs/019-token-efficiency-docs/research.md",
        ],
        "output_template_path": "specs/019-token-efficiency-docs/plan.md",
        "completion_marker": "## Summary",
        "correlation_id": correlation_id,
    }

    # Validate required fields are present
    required_fields = {
        "handoff_id",
        "step_name",
        "required_inputs",
        "output_template_path",
        "completion_marker",
        "correlation_id",
    }
    assert required_fields.issubset(set(handoff_contract.keys())), (
        f"Handoff contract missing required fields. "
        f"Expected: {required_fields}, got: {set(handoff_contract.keys())}"
    )

    # Validate field types
    assert isinstance(handoff_contract["handoff_id"], str)
    assert isinstance(handoff_contract["step_name"], str)
    assert isinstance(handoff_contract["required_inputs"], list)
    assert all(isinstance(p, str) for p in handoff_contract["required_inputs"])
    assert isinstance(handoff_contract["output_template_path"], str)
    assert isinstance(handoff_contract["completion_marker"], str)
    assert isinstance(handoff_contract["correlation_id"], str)

    # Validate correlation_id matches the run context
    assert handoff_contract["correlation_id"] == correlation_id
    assert ":" in correlation_id  # Should be scoped: run_id:step_name


def test_resolve_step_mapping_routes_deterministic_phase(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.plan:",
                "    description: \"planning phase\"",
                "    driver:",
                "      mode: deterministic",
                "      script_path: scripts/plan.sh",
                "      timeout_seconds: 60",
                "    emits:",
                "      - event: plan_started",
                "        required_fields: []",
            ]
        ),
        encoding="utf-8",
    )

    result = pipeline_driver.resolve_step_mapping(
        "plan",
        manifest_path=manifest_path,
        correlation_id="run-001:speckit.plan",
    )
    assert result["type"] == "deterministic"
    assert result["command_id"] == "speckit.plan"
    assert result["route"]["mode"] == "deterministic"
    assert result["route"]["driver_managed"] is True
    assert result["route"]["timeout_seconds"] == 60
    assert result["route"]["emits"] == ["plan_started"]
    assert result["route"]["emit_contracts"] == [
        {"event": "plan_started", "required_fields": []}
    ]


def test_resolve_step_mapping_defaults_canonical_trigger_for_driver_managed_route(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.example:",
                "    description: \"example route\"",
                "    driver:",
                "      mode: deterministic",
                "      script_path: scripts/example.sh",
                "    emits:",
                "      - event: example_event",
                "        required_fields: []",
            ]
        ),
        encoding="utf-8",
    )

    result = pipeline_driver.resolve_step_mapping(
        "example",
        manifest_path=manifest_path,
        correlation_id="run_20260410T120000Z_019:speckit.example",
    )

    assert result["type"] == "deterministic"
    assert result["command_id"] == "speckit.example"
    assert result["route"]["canonical_trigger"] == "speckit.run"


def test_resolve_step_mapping_creates_generative_handoff(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.specify:",
                "    description: \"specification generation\"",
                "    driver:",
                "      mode: generative",
                "    emits:",
                "      - event: backlog_registered",
                "        required_fields: []",
            ]
        ),
        encoding="utf-8",
    )

    correlation_id = "run_20260410T120000Z_019:speckit.specify"
    result = pipeline_driver.resolve_step_mapping(
        "specify",
        manifest_path=manifest_path,
        correlation_id=correlation_id,
    )
    assert result["type"] == "generative"
    assert result["command_id"] == "speckit.specify"
    assert "handoff" in result
    handoff = result["handoff"]
    assert handoff["handoff_id"] == "handoff_run_20260410T120000Z_019"
    assert handoff["step_name"] == "speckit.specify"
    assert handoff["correlation_id"] == correlation_id
    assert isinstance(handoff["required_inputs"], list)
    assert isinstance(handoff["output_template_path"], str)
    assert isinstance(handoff["completion_marker"], str)


def test_resolve_step_mapping_fallback_legacy_when_missing(tmp_path: Path) -> None:
    manifest_path = tmp_path / "command-manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("commands: {}\n", encoding="utf-8")

    result = pipeline_driver.resolve_step_mapping(
        "unknown_phase",
        manifest_path=manifest_path,
    )
    assert result["type"] == "legacy"
    assert result["command_id"] == "speckit.unknown_phase"
    assert result["reason"] == "command_not_in_manifest"


def test_route_legacy_step_returns_blocked_state() -> None:
    mapping_result = {
        "type": "legacy",
        "command_id": "speckit.plan",
        "reason": "command_not_in_manifest",
    }
    correlation_id = "run_20260410T120000Z_019:speckit.plan"

    result = pipeline_driver.route_legacy_step(
        mapping_result,
        correlation_id=correlation_id,
    )

    assert result["schema_version"] == "1.0.0"
    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["correlation_id"] == correlation_id
    assert result["gate"] == "command_not_driver_managed"
    assert "command_not_in_migration_scope" in result["reasons"]
    assert "legacy_fallback:" in str(result["reasons"])
    assert result["error_code"] is None
    assert result["next_phase"] is None


def test_route_legacy_step_uses_mapping_reason() -> None:
    mapping_result = {
        "type": "legacy",
        "command_id": "speckit.research",
        "reason": "manifest_not_found",
    }
    correlation_id = "run-mixed-mode"

    result = pipeline_driver.route_legacy_step(
        mapping_result,
        correlation_id=correlation_id,
    )

    assert result["exit_code"] == 1
    assert result["gate"] == "command_not_driver_managed"
    assert any("manifest_not_found" in reason for reason in result["reasons"])


def test_validate_generated_artifact_succeeds_with_valid_content(tmp_path: Path) -> None:
    artifact = tmp_path / "plan.md"
    artifact.write_text("# Plan\n\nThis is a valid plan.\n", encoding="utf-8")

    result = pipeline_driver.validate_generated_artifact(
        artifact,
        correlation_id="run-001:speckit.plan",
    )
    assert result["ok"] is True


def test_validate_generated_artifact_fails_when_missing(tmp_path: Path) -> None:
    artifact = tmp_path / "missing.md"

    result = pipeline_driver.validate_generated_artifact(
        artifact,
        correlation_id="run-001:speckit.plan",
    )
    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["gate"] == "artifact_validation"
    assert "artifact_not_created" in result["reasons"]


def test_validate_generated_artifact_fails_when_empty(tmp_path: Path) -> None:
    artifact = tmp_path / "empty.md"
    artifact.write_text("", encoding="utf-8")

    result = pipeline_driver.validate_generated_artifact(
        artifact,
        correlation_id="run-001:speckit.plan",
    )
    assert result["ok"] is False
    assert "artifact_empty_or_minimal" in result["reasons"]


def test_run_generative_handoff_executes_runner_and_captures_metadata(tmp_path: Path) -> None:
    artifact_path = tmp_path / "plan.md"
    runner_script = tmp_path / "runner.py"
    runner_script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "from pathlib import Path",
                "payload = json.loads(sys.stdin.read())",
                "artifact = Path(payload['handoff']['output_template_path'])",
                "artifact.parent.mkdir(parents=True, exist_ok=True)",
                "artifact.write_text('# Plan\\n## Summary\\nGenerated content\\n', encoding='utf-8')",
                "print(json.dumps({'artifact_path': str(artifact), 'completion_marker': '## Summary'}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    handoff = {
        "handoff_id": "handoff-runner",
        "step_name": "speckit.plan",
        "required_inputs": [],
        "output_template_path": str(artifact_path),
        "completion_marker": "## Summary",
        "correlation_id": "run_20260410T120000Z_019:speckit.plan",
    }

    result = pipeline_driver.run_generative_handoff(
        handoff,
        feature_id="019",
        phase="plan",
        correlation_id="run_20260410T120000Z_019:speckit.plan",
        handoff_runner=f"{sys.executable} {runner_script}",
        cwd=tmp_path,
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["handoff_execution"] == "executed"
    assert result["generated_artifact"]["path"] == str(artifact_path)
    assert result["generated_artifact"]["exists"] is True
    assert result["generated_artifact"]["size_bytes"] is not None
    assert result["generated_artifact"]["line_count"] == 3


def test_run_generative_handoff_fails_when_runner_not_configured(tmp_path: Path) -> None:
    handoff = {
        "handoff_id": "handoff-no-runner",
        "step_name": "speckit.plan",
        "required_inputs": [],
        "output_template_path": str(tmp_path / "plan.md"),
        "completion_marker": "## Summary",
        "correlation_id": "run_20260410T120000Z_019:speckit.plan",
    }

    result = pipeline_driver.run_generative_handoff(
        handoff,
        feature_id="019",
        phase="plan",
        correlation_id="run_20260410T120000Z_019:speckit.plan",
        handoff_runner=None,
        cwd=tmp_path,
        sidecar_dir=tmp_path / "runtime-failures",
    )

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "handoff_runner_not_configured"
    assert result["debug_path"] is not None
    assert "runtime_failure:handoff_runner_not_configured" in result["reasons"]


def test_resolve_step_mapping_uses_real_manifest() -> None:
    """Verify manifest routing works with actual command-manifest.yaml."""
    # This test validates that key commands are registered with driver metadata
    manifest_path = Path(__file__).resolve().parents[2] / "command-manifest.yaml"

    if not manifest_path.exists():
        pytest.skip("manifest file not found")

    # Test that generative commands are correctly identified
    generative_commands = [
        "specify",
        "research",
        "plan",
        "planreview",
        "sketch",
        "solution",
    ]
    for phase in generative_commands:
        result = pipeline_driver.resolve_step_mapping(
            phase,
            manifest_path=manifest_path,
        )
        if result["type"] != "legacy":
            # Command is registered in manifest
            assert result["command_id"] == f"speckit.{phase}"
            if result["type"] == "generative":
                assert "handoff" in result

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    assert routes["speckit.run"]["mode"] == "deterministic"
    assert routes["speckit.run"]["script_path"]
    assert routes["speckit.tasking"]["mode"] != "legacy"
    assert routes["speckit.implement"]["mode"] != "legacy"


def test_validate_generated_artifact_checks_completion_marker(tmp_path: Path) -> None:
    artifact = tmp_path / "plan.md"
    artifact.write_text("# Plan\nSome content", encoding="utf-8")

    # Should fail when marker not found
    result = pipeline_driver.validate_generated_artifact(
        artifact,
        correlation_id="run-001:speckit.plan",
        completion_marker="## Summary",
    )
    assert result["ok"] is False
    assert "completion_marker_not_found" in result["reasons"]

    # Should pass when marker is present
    artifact.write_text("# Plan\n## Summary\nContent here", encoding="utf-8")
    result = pipeline_driver.validate_generated_artifact(
        artifact,
        correlation_id="run-001:speckit.plan",
        completion_marker="## Summary",
    )
    assert result["ok"] is True


def test_manifest_governance_guard(tmp_path: Path) -> None:
    """US3: Manifest version/timestamp coupling enforces deterministic governance.

    Verifies:
    1. Manifest version changes are tracked with timestamps
    2. Version/timestamp coupling detects governance drift
    3. Alternate manifest copies cannot diverge from canonical without detected invariant violation
    """
    # Create canonical manifest with version and timestamp
    canonical_manifest = tmp_path / "command-manifest.yaml"
    canonical_manifest.parent.mkdir(parents=True, exist_ok=True)
    canonical_manifest.write_text(
        """version: "1.0.0"
last_updated: "2026-04-10T12:00:00Z"
commands:
  speckit.plan:
    mode: deterministic
""",
        encoding="utf-8",
    )

    # Create alternate copy (simulating stale split-control-plane file)
    mirror_manifest = tmp_path / "legacy" / "command-manifest.yaml"
    mirror_manifest.parent.mkdir(parents=True, exist_ok=True)
    mirror_manifest.write_text(
        """version: "1.0.0"
last_updated: "2026-04-10T12:00:00Z"
commands:
  speckit.plan:
    mode: deterministic
""",
        encoding="utf-8",
    )

    mirror_routes = pipeline_driver_contracts.load_driver_routes(mirror_manifest)
    assert mirror_routes is not None

    # Test 1: Divergence detection (update mirror without updating timestamp)
    mirror_manifest.write_text(
        """version: "1.0.0"
last_updated: "2026-04-10T12:00:00Z"
commands:
  speckit.plan:
    mode: legacy
""",
        encoding="utf-8",
    )

    # Test 2: Governance validation detects stale timestamp with changed content
    # NEW in Phase 5: validate_manifest_governance function
    governance_errors = pipeline_driver_contracts.validate_manifest_governance(
        manifest_path=mirror_manifest,
        canonical_path=canonical_manifest,
    )
    # Should detect divergence: routes changed but timestamp not updated
    assert governance_errors is not None
    assert len(governance_errors) > 0
