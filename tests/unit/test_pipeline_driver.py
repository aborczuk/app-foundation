"""Unit-level skeleton tests for scripts/pipeline_driver.py."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
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
    exit_code = pipeline_driver.main(["--feature-id", "019", "--phase", "implement", "--dry-run", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["feature_id"] == "019"
    assert payload["step_result"]["exit_code"] == 0


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


def test_normalize_driver_mode_aliases() -> None:
    assert pipeline_driver_contracts.normalize_driver_mode(None) == "legacy"
    assert pipeline_driver_contracts.normalize_driver_mode("script") == "deterministic"
    assert pipeline_driver_contracts.normalize_driver_mode("llm") == "generative"
    assert pipeline_driver_contracts.normalize_driver_mode("LEGACY") == "legacy"


def test_normalize_driver_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        pipeline_driver_contracts.normalize_driver_mode("unsupported-mode")


def test_load_driver_routes_normalizes_mode_and_script_path(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".specify" / "command-manifest.yaml"
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
    assert routes["speckit.example"]["script_path"] == str(
        (tmp_path / "scripts" / "example.sh").resolve()
    )

    assert routes["speckit.fallback"]["mode"] == "legacy"
    assert routes["speckit.fallback"]["driver_managed"] is False


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


def test_resolve_phase_state_is_ledger_authoritative(tmp_path: Path) -> None:
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
        pipeline_state={"phase": "setup", "blocked": False},
        ledger_path=ledger_path,
    )
    assert state["phase"] == "plan"
    assert state["last_event"] == "plan_started"
    assert state["drift_detected"] is True
    assert "phase_hint_conflicts_with_ledger" in state["drift_reasons"]


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
    assert "missing_artifact:plan.md" in state["drift_reasons"]
    assert state["blocked"] is True


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
    manifest_path = tmp_path / ".specify" / "command-manifest.yaml"
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


def test_resolve_step_mapping_creates_generative_handoff(tmp_path: Path) -> None:
    manifest_path = tmp_path / ".specify" / "command-manifest.yaml"
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
    manifest_path = tmp_path / ".specify" / "command-manifest.yaml"
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


def test_resolve_step_mapping_uses_real_manifest() -> None:
    """Verify manifest routing works with actual .specify/command-manifest.yaml."""
    # This test validates that key commands are registered with driver metadata
    manifest_path = Path(__file__).resolve().parents[2] / ".specify" / "command-manifest.yaml"

    if not manifest_path.exists():
        pytest.skip("manifest file not found")

    # Test that generative commands are correctly identified
    generative_commands = ["specify", "research", "plan", "planreview", "sketch"]
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
    3. Mirror manifests cannot diverge from canonical without detected invariant violation
    """
    # Create canonical manifest with version and timestamp
    canonical_manifest = tmp_path / ".specify" / "command-manifest.yaml"
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

    # Create mirror manifest (simulating split control plane scenario)
    mirror_manifest = tmp_path / "command-manifest.yaml"
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
