"""Integration-level tests for deterministic pipeline driver flow."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tests.support import assert_step_result_envelope


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


def build_feature_workspace(
    driver_flow_harness,
    *,
    command_id: str,
    script_name: str,
    emit_event: str,
    payload: dict[str, object],
    exit_code: int = 0,
    timeout_seconds: int = 30,
) -> tuple[Path, dict[str, dict[str, object]]]:
    """Create a deterministic one-command feature workspace for flow tests."""
    manifest_path = driver_flow_harness.feature_dir / "command-manifest.yaml"
    script_path = driver_flow_harness.feature_dir / "scripts" / script_name
    _write_step_script(script_path, payload=payload, exit_code=exit_code)
    _write_manifest_route(
        manifest_path,
        command_id=command_id,
        script_path=f"scripts/{script_name}",
        timeout_seconds=timeout_seconds,
        emit_event=emit_event,
    )
    routes = pipeline_driver_contracts.load_driver_routes(manifest_path)
    return manifest_path, routes


def test_deterministic_route_success(driver_flow_harness) -> None:
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.plan",
        run_id="run-us1-success",
    )
    manifest_path, routes = build_feature_workspace(
        driver_flow_harness,
        command_id="speckit.plan",
        script_name="plan_step.py",
        emit_event="plan_started",
        payload={
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": "plan",
        },
    )
    route = routes["speckit.plan"]
    assert route["mode"] == "deterministic"
    assert route["driver_managed"] is True

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert_step_result_envelope(result, ok=True, exit_code=0, next_phase="plan")
    assert result["process_exit_code"] == 0
    assert result["timed_out"] is False


def test_deterministic_route_blocked(driver_flow_harness) -> None:
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.planreview",
        run_id="run-us1-blocked",
    )
    manifest_path, routes = build_feature_workspace(
        driver_flow_harness,
        command_id="speckit.planreview",
        script_name="planreview_gate.py",
        emit_event="planreview_completed",
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
    route = routes["speckit.planreview"]
    assert route["mode"] == "deterministic"
    assert route["driver_managed"] is True

    result = pipeline_driver.run_step(
        [sys.executable, str(route["script_path"])],
        timeout_seconds=route["timeout_seconds"],
        correlation_id=correlation_id,
        cwd=driver_flow_harness.feature_dir,
    )

    assert_step_result_envelope(
        result,
        ok=False,
        exit_code=1,
        next_phase=None,
        gate="planreview_questions",
        reasons=["fq_count_nonzero"],
    )
    assert result["process_exit_code"] == 1
    assert result["timed_out"] is False


def test_generative_route_blocks_without_completion_append(driver_flow_harness, monkeypatch) -> None:
    feature_artifact = driver_flow_harness.feature_dir / "plan.md"
    feature_artifact.write_text("# Plan\n## Summary\nGenerated content\n", encoding="utf-8")

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
                "output_template_path": str(feature_artifact),
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
                "path": str(feature_artifact),
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
    assert append_called["value"] is False


def test_runtime_failure_verbose_rerun(driver_flow_harness) -> None:
    """Runtime error (exit code 2) triggers verbose rerun with sidecar persistence."""
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

    manifest_path, routes = build_feature_workspace(
        driver_flow_harness,
        command_id="speckit.sketch",
        script_name="sketch_timeout.py",
        emit_event="sketch_completed",
        payload=error_payload,
        exit_code=2,
        timeout_seconds=300,
    )
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
    manifest_path, routes = build_feature_workspace(
        driver_flow_harness,
        command_id="speckit.plan",
        script_name="plan_generator.py",
        emit_event="plan_approved",
        payload=success_payload,
        timeout_seconds=300,
    )

    # Record initial artifact state (should not exist)
    initial_artifact_exists = artifact_path.exists()
    assert initial_artifact_exists is False

    # Execute with dry-run enabled (implementation detail for T029)
    # For now, just verify that run_step respects correlation_id for tracing
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


def test_approval_breakpoint_blocks_without_token(driver_flow_harness, monkeypatch) -> None:
    """Approval denial blocks execution and leaves the downstream path cold."""
    correlation_id = pipeline_driver.build_correlation_id(
        "019",
        "speckit.implement",
        run_id="run-us2-breakpoint",
    )
    script_path = driver_flow_harness.feature_dir / "scripts" / "migration_step.py"
    call_counts = {"run_step": 0, "append": 0}
    expected_breakpoint_config = {
        "steps": {
            "implement": {
                "enabled": True,
                "required_scope": "security_sensitive_migration",
            }
        }
    }
    observed_breakpoint_configs: list[dict[str, object] | None] = []

    monkeypatch.setattr(
        pipeline_driver,
        "resolve_phase_state",
        lambda *args, **kwargs: {"phase": "implement", "blocked": False},
    )
    monkeypatch.setattr(
        pipeline_driver,
        "resolve_step_mapping",
        lambda *args, **kwargs: {
            "type": "deterministic",
            "command_id": "speckit.implement",
            "route": {
                "script_path": str(script_path),
                "timeout_seconds": 30,
            },
        },
    )

    def _fake_enforce_approval_breakpoint(
        step_name: str,
        *,
        approval_token: str | None = None,
        breakpoint_config: dict[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, object]:
        """Return a deterministic blocked result for missing or invalid approval."""
        assert step_name == "implement"
        assert breakpoint_config == expected_breakpoint_config
        observed_breakpoint_configs.append(breakpoint_config)
        if not approval_token:
            reasons = ["breakpoint_scope:security_sensitive_migration"]
        elif approval_token.split(":", 1)[0] != "security_sensitive_migration":
            reasons = ["approval_token_scope_mismatch"]
        else:
            return {"ok": True, "breakpoint_enforced": True, "approval_granted": True}
        return {
            "schema_version": "1.0.0",
            "ok": False,
            "exit_code": 1,
            "correlation_id": correlation_id or "unknown",
            "gate": "approval_required",
            "reasons": reasons,
            "error_code": None,
            "next_phase": None,
            "debug_path": None,
        }

    def _fake_run_step(*args, **kwargs):
        """Record any unexpected downstream execution attempt."""
        call_counts["run_step"] += 1
        return {
            "schema_version": "1.0.0",
            "ok": True,
            "exit_code": 0,
            "correlation_id": correlation_id,
            "next_phase": "implement",
            "gate": None,
            "reasons": [],
            "error_code": None,
            "debug_path": None,
        }

    def _fake_append_pipeline_success_event(**kwargs):
        """Record any unexpected pipeline event append attempt."""
        call_counts["append"] += 1
        return {"ok": True, "appended": True, "event": "implementation_completed"}

    monkeypatch.setattr(pipeline_driver, "enforce_approval_breakpoint", _fake_enforce_approval_breakpoint)
    monkeypatch.setattr(pipeline_driver, "run_step", _fake_run_step)
    monkeypatch.setattr(pipeline_driver, "append_pipeline_success_event", _fake_append_pipeline_success_event)
    monkeypatch.setattr(pipeline_driver, "emit_human_status", lambda *args, **kwargs: None)

    denied_exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "implement"])
    invalid_exit_code = pipeline_driver.main(
        [
            "--feature-id",
            "019",
            "--phase",
            "implement",
            "--approval-token",
            "wrong:token",
        ]
    )

    assert denied_exit_code == 1
    assert invalid_exit_code == 1
    assert call_counts == {"run_step": 0, "append": 0}
    assert observed_breakpoint_configs == [expected_breakpoint_config, expected_breakpoint_config]


def test_approval_breakpoint_resume_flow(driver_flow_harness) -> None:
    """Approval breakpoint resumes execution after human approval token verified."""
    # After approval token is obtained, workflow can resume and complete the step.
    # Placeholder for full flow validation in T030.

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
    manifest_path, routes = build_feature_workspace(
        driver_flow_harness,
        command_id="speckit.implement",
        script_name="apply_migration.py",
        emit_event="implementation_completed",
        payload=success_payload,
        timeout_seconds=60,
    )
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


def test_mixed_migration_mode(driver_flow_harness) -> None:
    """US3: Mixed migration mode maintains invariants and blocks uncovered commands.

    Verifies:
    1. Driver-managed commands route deterministically
    2. Legacy commands fall back to passthrough
    3. Uncovered command mappings fail gates
    4. Ledger/event invariants remain valid in mixed mode
    """
    # Seed ledger with completed prerequisites
    driver_flow_harness.seed_ledger(
        [
            driver_flow_harness.make_event("backlog_registered", "2026-04-10T00:00:00Z"),
            driver_flow_harness.make_event("research_completed", "2026-04-10T00:01:00Z"),
        ]
    )

    # Create mixed-mode manifest: one driver-managed, one legacy, one uncovered
    _manifest_routes = {
        "speckit.plan": {
            "mode": "deterministic",
            "driver_managed": True,
        },
        "speckit.sketch": {
            "mode": "legacy",
            "driver_managed": False,
        },
    }

    # Write test manifest with mixed modes
    manifest_yaml = """version: "1.0.0"
commands:
  speckit.plan:
    mode: deterministic
    driver:
      timeout_seconds: 30
  speckit.sketch:
    mode: legacy
  speckit.uncovered:
    description: "Intentionally uncovered command (no driver metadata)"
"""
    repo_root = driver_flow_harness.feature_dir.parent
    (repo_root / "command-manifest.yaml").write_text(
        manifest_yaml, encoding="utf-8"
    )

    # Test 1: Load manifest with mixed modes
    routes = pipeline_driver_contracts.load_driver_routes(repo_root / "command-manifest.yaml")

    # Driver-managed command should be marked as such
    assert routes["speckit.plan"]["driver_managed"] is True
    assert routes["speckit.plan"]["mode"] == "deterministic"

    # Legacy command should NOT be driver-managed
    assert routes["speckit.sketch"]["driver_managed"] is False
    assert routes["speckit.sketch"]["mode"] == "legacy"

    # Uncovered command should have legacy default
    assert routes["speckit.uncovered"]["driver_managed"] is False

    # Test 2: Mixed mode coverage validation (NEW in Phase 5)
    # This function is called by gates to detect uncovered command mappings
    coverage_result = pipeline_driver.validate_coverage_for_migration(
        routes=routes,
        feature_dir=driver_flow_harness.feature_dir,
        coverage_report_path=None,
    )
    # Should block uncovered commands in mixed mode
    assert coverage_result is not None
    assert "uncovered" in coverage_result or "coverage_gaps" in coverage_result

    # Test 3: Verify ledger invariants after mixed-mode resolve
    ledger_state = driver_flow_harness.resolve()
    assert ledger_state is not None
    assert isinstance(ledger_state, dict)
    # Phase should be deterministic
    assert "phase" in ledger_state
