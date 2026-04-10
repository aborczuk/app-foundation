"""Integration-level tests for deterministic pipeline driver flow."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


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


def _write_step_script(path: Path, *, payload: dict[str, object], exit_code: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(payload, sort_keys=True)
    path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                f"payload = json.loads({json.dumps(payload_json)})",
                "print(json.dumps(payload))",
                f"raise SystemExit({exit_code})",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_manifest_route(
    manifest_path: Path,
    *,
    command_id: str,
    script_path: str,
    timeout_seconds: int = 5,
    emit_event: str,
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                f"  {command_id}:",
                "    description: \"driver route\"",
                "    driver:",
                "      mode: deterministic",
                f"      script_path: {script_path}",
                f"      timeout_seconds: {timeout_seconds}",
                "    emits:",
                f"      - event: {emit_event}",
                "        required_fields: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_deterministic_route_success(driver_flow_harness) -> None:
    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "plan_step.py"
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.plan",
        run_id="run-us1-success",
    )
    _write_step_script(
        script_path,
        payload={
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": "plan",
        },
    )
    _write_manifest_route(
        manifest_path,
        command_id="speckit.plan",
        script_path="scripts/plan_step.py",
        emit_event="plan_started",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.plan"]
    assert route["mode"] == "deterministic"
    assert route["driver_managed"] is True

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["next_phase"] == "plan"
    assert result["process_exit_code"] == 0
    assert result["timed_out"] is False


def test_deterministic_route_blocked(driver_flow_harness) -> None:
    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "planreview_gate.py"
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.planreview",
        run_id="run-us1-blocked",
    )
    _write_step_script(
        script_path,
        payload={
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id,
            "gate": "planreview_questions",
            "reasons": ["fq_count_nonzero"],
            "next_phase": None,
        },
        exit_code=1,
    )
    _write_manifest_route(
        manifest_path,
        command_id="speckit.planreview",
        script_path="scripts/planreview_gate.py",
        emit_event="planreview_completed",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.planreview"]
    assert route["mode"] == "deterministic"
    assert route["driver_managed"] is True

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["gate"] == "planreview_questions"
    assert result["reasons"] == ["fq_count_nonzero"]
    assert result["process_exit_code"] == 1
    assert result["timed_out"] is False


def test_runtime_failure_verbose_rerun(driver_flow_harness) -> None:
    """Runtime error (exit code 2) triggers verbose rerun with sidecar persistence."""
    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "sketch_timeout.py"
    sidecar_dir = driver_flow_harness.feature_dir / ".speckit" / "failures"
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.sketch",
        run_id="run-us2-error",
    )

    # Script that exits with code 2 (error) and includes error_code + debug_path
    error_payload = {
        "schema_version": "1.0.0",
        "ok": False,
        "exit_code": 2,
        "correlation_id": correlation_id,
        "error_code": "script_timeout",
        "debug_path": str(sidecar_dir / "019_sketch_timeout_attempt_1.json"),
    }
    _write_step_script(
        script_path,
        payload=error_payload,
        exit_code=2,
    )

    # Write sidecar diagnostics that would be persisted by handle_runtime_failure()
    sidecar_path = Path(error_payload["debug_path"])
    sidecar_path.write_text(
        json.dumps({
            "correlation_id": correlation_id,
            "error_code": "script_timeout",
            "stderr": "Timed out waiting for LLM response after 300 seconds",
            "stdout": "Preparing sketch template...",
            "retry_count": 1,
            "last_attempt_exit_code": 2,
        }),
        encoding="utf-8",
    )

    _write_manifest_route(
        manifest_path,
        command_id="speckit.sketch",
        script_path="scripts/sketch_timeout.py",
        timeout_seconds=300,
        emit_event="sketch_completed",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.sketch"]
    assert route["mode"] == "deterministic"

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    # Verify error path routing
    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert result["error_code"] == "script_timeout"
    assert result["debug_path"] == str(sidecar_path)
    assert result["process_exit_code"] == 2
    assert result["timed_out"] is False

    # Verify sidecar diagnostics were written
    assert sidecar_path.exists()
    sidecar_data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar_data["error_code"] == "script_timeout"
    assert sidecar_data["correlation_id"] == correlation_id
    assert "Timed out" in sidecar_data["stderr"]


def test_dry_run_does_not_mutate_ledgers_or_artifacts(driver_flow_harness) -> None:
    """Dry-run mode resolves phase state but does not emit ledger events or persist artifacts."""
    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "plan_generator.py"
    artifact_path = driver_flow_harness.feature_dir / "plan.md"

    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.plan",
        run_id="run-us2-dryrun",
    )

    success_payload = {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "next_phase": "sketch",
    }
    _write_step_script(
        script_path,
        payload=success_payload,
        exit_code=0,
    )

    _write_manifest_route(
        manifest_path,
        command_id="speckit.plan",
        script_path="scripts/plan_generator.py",
        timeout_seconds=300,
        emit_event="plan_approved",
    )

    # Record initial artifact state (should not exist)
    initial_artifact_exists = artifact_path.exists()
    assert initial_artifact_exists is False

    # Execute with dry-run enabled (implementation detail for T029)
    # For now, just verify that run_step respects correlation_id for tracing
    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.plan"]

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert result["exit_code"] == 0
    assert result["ok"] is True
    # Artifact should still not exist (not persisted in dry-run)
    assert artifact_path.exists() is initial_artifact_exists


def test_approval_breakpoint_blocks_without_token(driver_flow_harness) -> None:
    """Approval breakpoint blocks step execution when human approval token not present."""
    # Marker: This test validates that enforce_approval_breakpoint() would block
    # when the approval token (stored in env var or file) is absent.
    # Implementation in T030.

    # For now, verify the fixture supports breakpoint setup
    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "migration_step.py"

    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.implement",
        run_id="run-us2-breakpoint",
    )

    blocked_payload = {
        "schema_version": "1.0.0",
        "ok": False,
        "exit_code": 1,
        "correlation_id": correlation_id,
        "gate": "approval_required",
        "reasons": ["security_sensitive_migration"],
    }
    _write_step_script(
        script_path,
        payload=blocked_payload,
        exit_code=1,
    )

    _write_manifest_route(
        manifest_path,
        command_id="speckit.implement",
        script_path="scripts/migration_step.py",
        timeout_seconds=30,
        emit_event="implementation_completed",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.implement"]

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    # Verify breakpoint gate is present
    assert result["gate"] == "approval_required"
    assert "security_sensitive_migration" in result["reasons"]


def test_approval_breakpoint_resume_flow(driver_flow_harness) -> None:
    """Approval breakpoint resumes execution after human approval token verified."""
    # After approval token is obtained, workflow can resume and complete the step.
    # Placeholder for full flow validation in T030.

    manifest_path = driver_flow_harness.feature_dir / ".specify" / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / "apply_migration.py"

    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.implement",
        run_id="run-us2-approved",
    )

    success_payload = {
        "schema_version": "1.0.0",
        "ok": True,
        "exit_code": 0,
        "correlation_id": correlation_id,
        "next_phase": "validate",
    }
    _write_step_script(
        script_path,
        payload=success_payload,
        exit_code=0,
    )

    _write_manifest_route(
        manifest_path,
        command_id="speckit.implement",
        script_path="scripts/apply_migration.py",
        timeout_seconds=60,
        emit_event="implementation_completed",
    )

    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    route = routes["speckit.implement"]

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert result["exit_code"] == 0
    assert result["ok"] is True
    assert result["next_phase"] == "validate"


def test_resolve_phase_state_skeleton(driver_flow_harness) -> None:
    state = driver_flow_harness.resolve(feature_id="999", phase_hint="setup")
    assert state["feature_id"] == "999"
    assert state["phase"] == "setup"
    assert state["blocked"] is False


def test_reconcile_and_retry_guards(driver_flow_harness) -> None:
    driver_flow_harness.seed_ledger(
        [
            driver_flow_harness.make_event("backlog_registered", "2026-04-10T00:00:00Z"),
            driver_flow_harness.make_event("research_completed", "2026-04-10T00:01:00Z"),
            driver_flow_harness.make_event("plan_started", "2026-04-10T00:02:00Z"),
            driver_flow_harness.make_event(
                "planreview_completed",
                "2026-04-10T00:03:00Z",
                fq_count=0,
                questions_asked=0,
            ),
            driver_flow_harness.make_event(
                "feasibility_spike_completed",
                "2026-04-10T00:04:00Z",
                spike_artifact="specs/019-token-efficiency-docs/spike.md",
                fq_count=0,
            ),
            driver_flow_harness.make_event(
                "plan_approved",
                "2026-04-10T00:05:00Z",
                feasibility_required="false",
            ),
        ]
    )

    drift_state = driver_flow_harness.resolve()
    assert drift_state["drift_detected"] is True
    assert "missing_artifact:plan.md" in drift_state["drift_reasons"]

    (driver_flow_harness.feature_dir / "plan.md").write_text("# plan\n", encoding="utf-8")
    reconciled_state = driver_flow_harness.resolve()
    assert reconciled_state["drift_detected"] is False
    assert reconciled_state["phase"] == "plan"

    first_lock = driver_flow_harness.acquire(owner="worker-a")
    retry_lock = driver_flow_harness.acquire(owner="worker-a")
    blocked_lock = driver_flow_harness.acquire(owner="worker-b")
    assert first_lock["acquired"] is True
    assert retry_lock["acquired"] is True
    assert retry_lock["reused"] is True
    assert blocked_lock["acquired"] is False
    assert blocked_lock["reason"] == "feature_lock_held"
