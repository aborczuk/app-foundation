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
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(
            [
                "commands:",
                "  speckit.plan:",
                "    description: \"plan\"",
                "    driver:",
                "      mode: deterministic",
                "      script_path: scripts/plan_step.py",
                "      timeout_seconds: 5",
                "    emits:",
                "      - event: plan_started",
                "        required_fields: []",
            ]
        )
        + "\n",
        encoding="utf-8",
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
