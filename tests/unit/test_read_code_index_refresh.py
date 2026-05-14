"""Unit tests for read-code index freshness checks and targeted refresh behavior."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest


def _load_module(module_name: str, script_name: str):
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    script_path = scripts_dir / script_name
    scripts_dir_str = str(scripts_dir)
    if scripts_dir_str not in sys.path:
        sys.path.insert(0, scripts_dir_str)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    if spec.name in sys.modules:
        return sys.modules[spec.name]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


read_code = _load_module("read_code", "read_code.py")
read_code_health = _load_module("read_code_health", "read_code_health.py")


@pytest.fixture(autouse=True)
def _reset_read_code_session_state(monkeypatch, tmp_path: Path) -> Iterator[None]:
    """Isolate session-scoped probe/debounce caches between tests."""
    monkeypatch.setenv("READ_CODE_SESSION_ID", "test-session")
    monkeypatch.setattr(read_code_health, "CODEGRAPH_DB_DIR", tmp_path / "codegraph-db")
    setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_DONE", False)
    setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_AVAILABLE", True)
    setattr(read_code_health, "_CODEGRAPH_PREFLIGHT_LAUNCHED", False)
    setattr(read_code_health, "_VECTOR_RUNTIME_NOTE", None)
    read_code_health._invalidate_vector_probe_cache("test-session")
    yield
    read_code_health._invalidate_vector_probe_cache("test-session")


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _vector_probe(
    *,
    status: str,
    stale_reason: str = "",
    stale_reason_class: str = "none",
    stale_drift_paths: tuple[str, ...] = (),
    stale_signal_source: str = "git",
    stale_signal_available: bool = True,
    stale_signal_error: str = "",
    trust_state: str | None = None,
    escalation_state: str | None = None,
) -> object:
    derived_trust_state = {
        "healthy": "reused",
        "stale": "invalidated",
        "missing": "invalidated",
        "unavailable": "invalidated",
        "probe-failed": "invalidated",
    }.get(status, "unknown")
    derived_escalation_state = {
        "healthy": "none",
        "stale": "refresh",
        "missing": "bootstrap",
        "unavailable": "recover",
        "probe-failed": "recover",
    }.get(status, "unknown")
    return read_code_health._VectorIndexProbe(
        status=status,
        stale_reason=stale_reason,
        stale_reason_class=stale_reason_class,
        stale_drift_paths=stale_drift_paths,
        stale_signal_source=stale_signal_source,
        stale_signal_available=stale_signal_available,
        stale_signal_error=stale_signal_error,
        trust_state=trust_state or derived_trust_state,
        escalation_state=escalation_state or derived_escalation_state,
    )


def _vector_match(line_num: int, signature: str, *, confidence: int = 100) -> object:
    """Build a minimal ranked vector match for helper selection tests."""
    return read_code._VectorMatch(
        unit_id=f"test:{signature}",
        symbol_name=signature,
        qualified_name=signature,
        line_num=line_num,
        line_end=line_num,
        raw_score=1.0,
        cosine_similarity=confidence,
        symbol_type="function",
        has_body=True,
        has_docstring=False,
        body=f"{signature}\n    pass",
        preview=signature,
        signature=signature,
    )


def _vector_match_at_path(path: Path, line_num: int, signature: str, *, confidence: int = 100) -> object:
    """Build a minimal ranked vector match pinned to a specific file path."""
    return read_code._VectorMatch(
        unit_id=f"test:{signature}:{path}",
        symbol_name=signature,
        qualified_name=signature,
        line_num=line_num,
        line_end=line_num,
        raw_score=1.0,
        cosine_similarity=confidence,
        symbol_type="function",
        has_body=True,
        has_docstring=False,
        body=f"{signature}\n    pass",
        preview=signature,
        signature=signature,
        file_path=path,
    )


def test_vector_query_candidates_passes_file_path_to_indexer(monkeypatch, tmp_path: Path) -> None:
    """Semantic query subprocess calls should include the target file-path filter."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def sample() -> int:\n    return 1\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed(
            0,
            stdout=json.dumps(
                [
                    {
                        "file_path": str(code_file.resolve()),
                        "line_start": 1,
                        "line_end": 2,
                        "symbol_name": "sample",
                        "qualified_name": "sample",
                        "symbol_type": "function",
                        "signature": "def sample() -> int:",
                        "preview": "def sample() -> int:",
                        "body": "def sample() -> int:\n    return 1\n",
                        "score": 1.0,
                    }
                ]
            ),
        )

    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    matches = read_code._vector_query_candidates(code_file, "sample", "sample", "code")

    assert matches
    assert matches[0].line_num == 1
    assert "cmd" in captured
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--file-path" in cmd
    file_flag_index = cmd.index("--file-path")
    assert cmd[file_flag_index + 1] == str(code_file.resolve())


def test_vector_index_status_reports_missing_for_null_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health._invalidate_vector_probe_cache("test-session")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout="null\n"))

    status = read_code_health.vector_index_status()

    assert status == "missing"


def test_vector_index_probe_parses_stale_payload_with_cause_details(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health._invalidate_vector_probe_cache("test-session")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            0,
            stdout=(
                '{"is_stale": true, "stale_reason": "indexable git drift paths: src/sample.py", '
                '"stale_reason_class": "git-path-drift", "stale_drift_paths": ["src/sample.py"], '
                '"stale_signal_source": "git", "stale_signal_available": true, "stale_signal_error": ""}\n'
            ),
        ),
    )

    probe = read_code_health.vector_index_probe()

    assert probe.status == "stale"
    assert probe.stale_reason_class == "git-path-drift"
    assert probe.stale_drift_paths == ("src/sample.py",)
    assert "src/sample.py" in probe.stale_reason
    assert probe.trust_state == "invalidated"
    assert probe.escalation_state == "refresh"


def test_vector_index_probe_parses_coverage_gap_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health._invalidate_vector_probe_cache("test-session")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            0,
            stdout=(
                '{"is_stale": true, "stale_reason": "non-empty indexable files missing from snapshot: '
                'src/new_feature.py", "stale_reason_class": "coverage-gap", '
                '"stale_drift_paths": ["src/new_feature.py"], "stale_signal_source": "coverage", '
                '"stale_signal_available": true, "stale_signal_error": ""}\n'
            ),
        ),
    )

    probe = read_code_health.vector_index_probe()

    assert probe.status == "stale"
    assert probe.stale_reason_class == "coverage-gap"
    assert probe.stale_drift_paths == ("src/new_feature.py",)
    assert probe.stale_signal_source == "coverage"
    assert "src/new_feature.py" in probe.stale_reason
    assert probe.trust_state == "invalidated"
    assert probe.escalation_state == "refresh"


@pytest.mark.parametrize(
    ("probe", "expected_trust_state", "expected_escalation_state"),
    [
        (_vector_probe(status="healthy"), "reused", "none"),
        (_vector_probe(status="missing", stale_reason="snapshot missing"), "invalidated", "bootstrap"),
        (_vector_probe(status="unavailable", stale_reason="uv is not available"), "invalidated", "recover"),
    ],
)
def test_vector_index_probe_exposes_explicit_state_labels(
    monkeypatch, probe: object, expected_trust_state: str, expected_escalation_state: str
) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: probe,
    )

    resolved = read_code_health.vector_index_probe()

    assert resolved.trust_state == expected_trust_state
    assert resolved.escalation_state == expected_escalation_state


def test_vector_trust_decision_reports_explicit_escalation_state(monkeypatch, tmp_path: Path) -> None:
    """Scoped stale overlap should produce an explicit invalidation decision."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe(
        "test-session",
        _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: src/sample.py",
            stale_reason_class="git-path-drift",
            stale_drift_paths=("src/sample.py",),
            trust_state="invalidated",
            escalation_state="refresh",
        ),
    )

    decision = read_code_health._vector_trust_decision(scope_path, request_is_scoped=True)

    assert decision.trusted is False
    assert decision.trust_state == "invalidated"
    assert decision.escalation_state == "refresh"
    assert "stale drift overlaps requested scope" in decision.runtime_note


def test_vector_index_probe_uses_short_ttl_cache(monkeypatch, tmp_path: Path) -> None:
    calls = {"count": 0}

    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health._invalidate_vector_probe_cache("test-session")
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "")

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        return _completed(0, stdout='{"is_stale": false}\n')

    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    first = read_code_health.vector_index_probe()
    second = read_code_health.vector_index_probe()

    assert first.status == "healthy"
    assert second.status == "healthy"
    assert calls["count"] == 1


def test_vector_index_probe_uses_cached_vector_edit_signature_before_status_probe(monkeypatch, tmp_path: Path) -> None:
    """Healthy vector signatures should bypass the external status probe on first read."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health.vector_edit_signature_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    read_code_health.vector_edit_signature_file(tmp_path).write_text("M scripts/read_code.py", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "M scripts/read_code.py")
    monkeypatch.setattr(read_code_health, "vector_cached_edit_signature", lambda project_root=None: "M scripts/read_code.py")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health,
        "_run_command_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("status probe should not run")),
    )

    probe = read_code_health.vector_index_probe()

    assert probe.status == "healthy"
    assert probe.trust_state == "reused"
    assert probe.escalation_state == "none"


def test_vector_index_probe_uses_clean_vector_edit_signature_before_status_probe(monkeypatch, tmp_path: Path) -> None:
    """Clean vector baselines should bypass the external status probe too."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health.vector_edit_signature_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    read_code_health.vector_edit_signature_file(tmp_path).write_text("", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health,
        "_run_command_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("status probe should not run")),
    )

    probe = read_code_health.vector_index_probe()

    assert probe.status == "healthy"
    assert probe.trust_state == "reused"
    assert probe.escalation_state == "none"


def test_vector_index_probe_prefers_local_signature_over_stale_session_probe(monkeypatch, tmp_path: Path) -> None:
    """A local clean signature baseline should override any stale cached probe."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    stale_probe = _vector_probe(
        status="stale",
        stale_reason="indexable git drift paths: scripts/read_code_health.py",
        stale_reason_class="git-path-drift",
        stale_drift_paths=("scripts/read_code_health.py",),
    )
    read_code_health._remember_vector_probe("test-session", stale_probe)
    read_code_health.vector_edit_signature_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    read_code_health.vector_edit_signature_file(tmp_path).write_text("", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "")

    probe = read_code_health.vector_index_probe()

    assert probe.status == "healthy"
    assert probe.stale_drift_paths == ()


def test_vector_index_probe_derives_local_stale_drift_from_vector_edit_signature(monkeypatch, tmp_path: Path) -> None:
    """Vector reads should derive local drift paths before shelling out to the status probe."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health.vector_edit_signature_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    read_code_health.vector_edit_signature_file(tmp_path).write_text(" M docs/guide.md", encoding="utf-8")
    monkeypatch.setattr(
        read_code_health,
        "codegraph_current_edit_signature",
        lambda project_root=None: " M scripts/read_code.py\n M docs/guide.md",
    )
    monkeypatch.setattr(
        read_code_health,
        "vector_cached_edit_signature",
        lambda project_root=None: " M docs/guide.md",
    )
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health,
        "_run_command_capture",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("status probe should not run")),
    )

    probe = read_code_health.vector_index_probe()

    assert probe.status == "stale"
    assert probe.stale_reason_class == "git-path-drift"
    assert probe.stale_drift_paths == ("scripts/read_code.py",)


def test_read_code_session_id_fallback_is_stable_when_parent_pid_changes(monkeypatch, tmp_path: Path) -> None:
    """Fallback session ids should stay stable across CLI invocations with different uv parent pids."""
    monkeypatch.delenv("READ_CODE_SESSION_ID", raising=False)
    monkeypatch.delenv("TERM_SESSION_ID", raising=False)
    monkeypatch.delenv("WT_SESSION", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.delenv("STY", raising=False)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)

    monkeypatch.setattr(read_code_health.os, "getppid", lambda: 111)
    first = read_code_health._read_code_session_id()

    monkeypatch.setattr(read_code_health.os, "getppid", lambda: 222)
    second = read_code_health._read_code_session_id()

    assert first == second
    assert first.startswith("repo-")


def test_read_code_main_seeds_session_id_from_stable_helper(monkeypatch) -> None:
    """CLI entrypoint should reuse the stable helper when no session id is preset."""
    monkeypatch.delenv("READ_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(read_code, "_read_code_session_id", lambda: "repo-stable-session")
    monkeypatch.setattr(read_code, "read_code_context", lambda args, *, verbose=False: 0)

    assert read_code.main(["context", "_resolve_pattern_anchor"]) == 0
    assert os.environ["READ_CODE_SESSION_ID"] == "repo-stable-session"


def test_vector_refresh_synchronous_uses_shared_refresh_orchestrator(monkeypatch, tmp_path: Path) -> None:
    """Read-time vector refreshes should route through the shared hook orchestrator."""
    captured: dict[str, object] = {}

    class FakeHook:
        def run_refresh_request(self, payload):
            captured["payload"] = payload
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("unexpected background launch")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())
    target = tmp_path / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    assert read_code_health.vector_refresh_synchronous([target]) is True
    assert captured["payload"] == {
        "tool_input": {
            "paths": [str(target)],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }


def test_codegraph_refresh_background_uses_shared_refresh_orchestrator(monkeypatch, tmp_path: Path) -> None:
    """Read-time codegraph background refreshes should launch the shared hook orchestrator."""
    captured: dict[str, object] = {}

    class FakeHook:
        def run_refresh_request(self, payload):
            raise AssertionError("unexpected sync refresh")

        def launch_refresh_request(self, payload):
            captured["payload"] = payload
            return True

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())
    monkeypatch.setattr(read_code_health, "_should_launch_background_refresh", lambda scope_path, *, channel: True)
    target = tmp_path / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    assert read_code_health.codegraph_refresh_background(target, [target]) is True
    assert captured["payload"] == {
        "tool_input": {
            "paths": [str(target)],
            "refresh_codegraph": True,
            "refresh_vector": False,
        }
    }


def test_vector_index_status_reports_healthy_when_status_payload_is_fresh(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    read_code_health._invalidate_vector_probe_cache("test-session")
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout='{"is_stale": false}\n'))

    status = read_code_health.vector_index_status()

    assert status == "healthy"


@pytest.mark.parametrize(
    ("probe", "request_is_scoped", "expected"),
    [
        (_vector_probe(status="healthy"), True, True),
        (
            _vector_probe(
                status="stale",
                stale_reason="indexable git drift paths: docs/guide.md",
                stale_reason_class="git-path-drift",
                stale_drift_paths=("docs/guide.md",),
            ),
            True,
            True,
        ),
        (
            _vector_probe(
                status="stale",
                stale_reason="indexable git drift paths: src/sample.py",
                stale_reason_class="git-path-drift",
                stale_drift_paths=("src/sample.py",),
            ),
            True,
            False,
        ),
        (_vector_probe(status="missing", stale_reason="snapshot missing"), True, False),
    ],
)
def test_read_request_trusts_vector_cache_for_scoped_reads(
    monkeypatch,
    tmp_path: Path,
    probe: object,
    request_is_scoped: bool,
    expected: bool,
) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe("test-session", probe)

    assert (
        read_code_health._read_request_trusts_vector_cache(
            scope_path,
            request_is_scoped=request_is_scoped,
        )
        is expected
    )


def test_read_request_trusts_vector_cache_for_broad_reads_when_session_is_healthy(
    monkeypatch, tmp_path: Path
) -> None:
    """Healthy broad reads should use the cached vector state immediately."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe("test-session", _vector_probe(status="healthy"))

    assert read_code_health._read_request_trusts_vector_cache(
        scope_path,
        request_is_scoped=False,
    )


@pytest.mark.parametrize(
    ("probe", "request_is_scoped"),
    [
        (_vector_probe(status="missing", stale_reason="snapshot missing"), True),
        (_vector_probe(status="missing", stale_reason="snapshot missing"), False),
        (_vector_probe(status="unavailable", stale_reason="uv is not available"), True),
        (_vector_probe(status="probe-failed", stale_reason="probe failed"), False),
    ],
)
def test_read_request_trusts_vector_cache_rejects_invalidated_states(
    monkeypatch,
    tmp_path: Path,
    probe: object,
    request_is_scoped: bool,
) -> None:
    """Invalidated vector probes should not short-circuit read preflight."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe("test-session", probe)

    assert (
        read_code_health._read_request_trusts_vector_cache(
            scope_path,
            request_is_scoped=request_is_scoped,
        )
        is False
    )


def test_refresh_indexes_for_read_reports_escalation_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    """Read preflight should surface a hard failure when vector refresh cannot recover."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(read_code_health, "_is_repo_local_path", lambda _path: True)
    monkeypatch.setattr(read_code_health, "_ensure_codegraph_session_available", lambda _path: None)
    monkeypatch.setattr(read_code_health, "_read_request_trusts_vector_cache", lambda *args, **kwargs: False)
    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", lambda *args, **kwargs: False)
    monkeypatch.setattr(read_code_health, "_consume_vector_runtime_note", lambda: "stale vector index")

    result = read_code_health._refresh_indexes_for_read(code_file, request_is_scoped=False)
    captured = capsys.readouterr()

    assert result is False
    assert "stale vector index" in captured.err
    assert "healthy vector index" in captured.err


def test_read_code_context_marks_file_local_requests_scoped_for_refresh(monkeypatch, tmp_path: Path) -> None:
    """File-local reads should carry the scoped trust flag into preflight."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda preflight_path, *, verbose=False, request_is_scoped=None: calls.setdefault(
            "request_is_scoped", request_is_scoped
        )
        or True,
    )
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [
            _vector_match_at_path(code_file, 1, "def run_pipeline():", confidence=95),
        ],
    )
    monkeypatch.setattr(
        read_code,
        "_render_compact_match",
        lambda vector_match, **kwargs: calls.setdefault("selected", vector_match),
    )
    monkeypatch.setattr(read_code, "_render_resolution_extras", lambda *args, **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    exit_code = read_code.read_code_context([str(code_file), "how does this work"])

    assert exit_code == 0
    assert calls["request_is_scoped"] is True
    assert cast(Any, calls["selected"]).signature == "def run_pipeline():"


def test_vector_refresh_by_state_returns_early_for_trusted_broad_read(monkeypatch, tmp_path: Path) -> None:
    """Healthy broad reads should skip the slow vector probe path."""
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe("test-session", _vector_probe(status="healthy"))
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: (_ for _ in ()).throw(AssertionError("slow probe should be skipped")),
    )

    assert read_code_health.vector_refresh_by_state(scope_path, request_is_scoped=False) is True


def test_vector_refresh_by_state_keeps_hard_failure_for_probe_failed_status(monkeypatch, tmp_path: Path, capsys) -> None:
    """Probe failures should remain hard failures instead of being trusted."""
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="probe-failed",
            stale_reason="vector probe failed",
            stale_reason_class="probe-failed",
        ),
    )

    result = read_code_health.vector_refresh_by_state(scope_path, request_is_scoped=False)
    captured = capsys.readouterr()

    assert result is False
    assert "status is probe-failed" in captured.err


def test_codegraph_status_payload_reports_stale_when_signatures_drift(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_health_probe",
        lambda project_root=None: read_code_health._CodegraphHealthProbe(
            status="healthy",
            detail="doctor healthy",
            recovery_command="",
        ),
    )
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "current")
    monkeypatch.setattr(read_code_health, "codegraph_cached_edit_signature", lambda project_root=None: "cached")

    payload = read_code_health.codegraph_status_payload(tmp_path)

    assert payload["project_root"] == str(tmp_path.resolve())
    assert payload["codegraph_status"] == "stale"
    assert payload["codegraph_detail"] == "doctor healthy"


def test_run_status_command_emits_json_payload(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_status_payload",
        lambda project_root=None: {
            "project_root": str((project_root or tmp_path).resolve()),
            "codegraph_status": "healthy",
            "codegraph_detail": "",
            "codegraph_recovery_command": "",
        },
    )
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(status="healthy", trust_state="reused", escalation_state="none"),
    )

    exit_code = read_code_health.run_status_command(["--project-root", str(tmp_path), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["project_root"] == str(tmp_path.resolve())
    assert payload["codegraph_status"] == "healthy"
    assert payload["vector_index_status"] == "healthy"
    assert payload["vector_trust_state"] == "reused"
    assert payload["vector_escalation_state"] == "none"


def test_run_status_command_emits_vector_state_in_plain_text(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_status_payload",
        lambda project_root=None: {
            "project_root": str((project_root or tmp_path).resolve()),
            "codegraph_status": "healthy",
            "codegraph_detail": "",
            "codegraph_recovery_command": "",
        },
    )
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(status="stale", trust_state="invalidated", escalation_state="refresh"),
    )

    exit_code = read_code_health.run_status_command(["--project-root", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "vector_index_status=stale" in output
    assert "vector_trust_state=invalidated" in output
    assert "vector_escalation_state=refresh" in output


def test_run_status_command_rejects_missing_project_root_value(capsys) -> None:
    exit_code = read_code_health.run_status_command(["--project-root"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "requires a path" in captured.err


def test_vector_refresh_if_needed_bootstraps_when_snapshot_is_missing(monkeypatch, tmp_path: Path) -> None:
    probes = iter(
        [
            _vector_probe(status="missing", stale_reason="snapshot missing"),
            _vector_probe(status="healthy"),
        ]
    )
    monkeypatch.setattr(read_code_health, "vector_index_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0, stdout='{"entry_count": 1}')

    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    target = tmp_path / "sample.py"
    result = read_code_health.vector_refresh_if_needed(target)

    assert result is True
    assert called["value"] is True


def test_vector_refresh_if_needed_skips_when_index_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "vector_index_probe", lambda project_root=None: _vector_probe(status="healthy"))
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    result = read_code_health.vector_refresh_if_needed(tmp_path / "sample.py")

    assert result is True
    assert called["value"] is False


def test_vector_refresh_by_state_returns_early_for_trusted_scoped_read(monkeypatch, tmp_path: Path) -> None:
    """Trusted scoped reads should bypass the slow vector probe path."""
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    read_code_health._remember_vector_probe("test-session", _vector_probe(status="healthy"))
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: (_ for _ in ()).throw(AssertionError("slow probe should be skipped")),
    )

    assert read_code_health.vector_refresh_by_state(scope_path, request_is_scoped=True) is True


def test_vector_refresh_by_state_keeps_hard_failure_for_unavailable_status(monkeypatch, tmp_path: Path, capsys) -> None:
    """Untrusted unavailable states should still fail through the normal slow path."""
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="unavailable",
            stale_reason="uv is not available",
            stale_reason_class="probe-unavailable",
        ),
    )

    result = read_code_health.vector_refresh_by_state(scope_path, request_is_scoped=True)
    captured = capsys.readouterr()

    assert result is False
    assert "status is unavailable" in captured.err


def test_vector_refresh_if_needed_refreshes_stale_index_for_overlap(monkeypatch, tmp_path: Path, capsys) -> None:
    target = tmp_path / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def sample() -> None:\n    pass\n", encoding="utf-8")
    probe = _vector_probe(
        status="stale",
        stale_reason="indexable git drift paths: src/sample.py",
        stale_reason_class="git-path-drift",
        stale_drift_paths=("src/sample.py",),
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(read_code_health, "vector_index_probe", lambda project_root=None: probe)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("background refresh should not run")))

    class FakeHook:
        def run_refresh_request(self, payload):
            calls.append(payload)
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("background refresh should not run")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    result = read_code_health.vector_refresh_if_needed(target)
    captured = capsys.readouterr()

    assert result is True
    assert len(calls) == 1
    assert calls[0] == {
        "tool_input": {
            "paths": [str(target)],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }
    assert "overlap=yes" in captured.err
    assert "running synchronous stale-scope refresh" in captured.err
    assert "cause=git-path-drift" not in captured.err


def test_vector_refresh_if_needed_verbose_emits_detailed_stale_message(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    target = tmp_path / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def sample() -> None:\n    pass\n", encoding="utf-8")
    probe = _vector_probe(
        status="stale",
        stale_reason="indexable git drift paths: src/sample.py",
        stale_reason_class="git-path-drift",
        stale_drift_paths=("src/sample.py",),
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(read_code_health, "vector_index_probe", lambda project_root=None: probe)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("background refresh should not run")))

    class FakeHook:
        def run_refresh_request(self, payload):
            calls.append(payload)
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("background refresh should not run")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    result = read_code_health.vector_refresh_if_needed(target, verbose=True)
    captured = capsys.readouterr()

    assert result is True
    assert len(calls) == 1
    assert calls[0] == {
        "tool_input": {
            "paths": [str(target)],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }
    assert "cause=git-path-drift" in captured.err
    assert "detail=indexable git drift paths: src/sample.py" in captured.err
    assert "drift_paths=['src/sample.py']" in captured.err
    assert "running synchronous stale-scope refresh" in captured.err


def test_vector_refresh_if_needed_launches_background_refresh_for_unaffected_scope(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: docs/guide.md",
            stale_reason_class="git-path-drift",
            stale_drift_paths=("docs/guide.md",),
        ),
    )
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)

    calls: list[dict[str, object]] = []

    class FakeHook:
        def run_refresh_request(self, payload):
            raise AssertionError("unexpected sync refresh")

        def launch_refresh_request(self, payload):
            calls.append(payload)
            return True

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    result = read_code_health.vector_refresh_if_needed(tmp_path / "src" / "sample.py")
    captured = capsys.readouterr()

    assert result is True
    assert len(calls) == 1
    assert calls[0] == {
        "tool_input": {
            "paths": [str(tmp_path / "docs" / "guide.md")],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }
    assert captured.err == ""
    assert "cause=git-path-drift" not in captured.err


def test_vector_refresh_if_needed_dedupes_sync_refresh_for_overlap(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: src/sample.py",
            stale_reason_class="git-path-drift",
            stale_drift_paths=("src/sample.py",),
        ),
    )
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code_health.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("background refresh should not run")))

    calls: list[dict[str, object]] = []

    class FakeHook:
        def run_refresh_request(self, payload):
            calls.append(payload)
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("background refresh should not run")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    target = tmp_path / "src" / "sample.py"
    assert read_code_health.vector_refresh_if_needed(target) is True
    assert read_code_health.vector_refresh_if_needed(target) is True
    assert len(calls) == 1
    assert calls[0] == {
        "tool_input": {
            "paths": [str(target)],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }


def test_vector_refresh_synchronous_marks_probe_cache_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("READ_CODE_SESSION_ID", "sync-refresh-session")
    stale_probe = _vector_probe(
        status="stale",
        stale_reason="indexable git drift paths: src/sample.py",
        stale_reason_class="git-path-drift",
        stale_drift_paths=("src/sample.py",),
    )
    read_code_health._remember_vector_probe("sync-refresh-session", stale_probe)
    assert read_code_health._load_vector_probe_cache("sync-refresh-session") == stale_probe

    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: " M src/sample.py")

    class FakeHook:
        def run_refresh_request(self, payload):
            read_code_health._remember_healthy_vector_probe()
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("unexpected background launch")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    target = tmp_path / "src" / "sample.py"
    assert read_code_health.vector_refresh_synchronous([target]) is True
    refreshed = read_code_health._load_vector_probe_cache("sync-refresh-session")
    assert refreshed is not None
    assert refreshed.status == "healthy"
    assert refreshed.stale_drift_paths == ()
    assert read_code_health.vector_cached_edit_signature(tmp_path) == " M src/sample.py"


def test_vector_refresh_synchronous_persists_clean_signature_baseline(monkeypatch, tmp_path: Path) -> None:
    """Clean worktrees should still persist an empty vector signature baseline."""
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("READ_CODE_SESSION_ID", "clean-refresh-session")
    monkeypatch.setattr(read_code_health, "codegraph_current_edit_signature", lambda project_root=None: "")

    class FakeHook:
        def run_refresh_request(self, payload):
            read_code_health._remember_healthy_vector_probe()
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("unexpected background launch")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    target = tmp_path / "src" / "sample.py"
    assert read_code_health.vector_refresh_synchronous([target]) is True
    assert read_code_health.vector_edit_signature_file(tmp_path).is_file()
    assert read_code_health.vector_cached_edit_signature(tmp_path) == ""


def test_vector_refresh_if_needed_launches_when_overlap_is_unknown(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code_health,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: unknown",
            stale_reason_class="coverage-gap",
            stale_drift_paths=(),
        ),
    )
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)

    background_calls: list[dict[str, object]] = []

    class FakeHook:
        def run_refresh_request(self, payload):
            raise AssertionError("unexpected sync refresh")

        def launch_refresh_request(self, payload):
            background_calls.append(payload)
            return True

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    result = read_code_health.vector_refresh_if_needed(tmp_path / "src" / "sample.py")
    captured = capsys.readouterr()

    assert result is True
    assert len(background_calls) == 1
    assert background_calls[0] == {
        "tool_input": {
            "paths": [str(tmp_path / "src" / "sample.py")],
            "refresh_codegraph": False,
            "refresh_vector": True,
        }
    }
    assert "overlap=unknown" in captured.err
    assert "launching async stale-scope refresh" in captured.err


def test_codegraph_health_status_reports_unavailable_without_uv(monkeypatch) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: False)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0, stdout='{"status":"healthy"}')

    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    status = read_code_health.codegraph_health_status()

    assert status == "unavailable"
    assert called["value"] is False


def test_codegraph_health_status_parses_nonhealthy_json_payload(monkeypatch) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health.subprocess,
        "run",
        lambda *args, **kwargs: _completed(1, stdout='{"status":"stale"}\n', stderr="stale"),
    )

    status = read_code_health.codegraph_health_status()

    assert status == "stale"


def test_codegraph_health_probe_returns_detail_and_recovery_command(monkeypatch) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code_health.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            0,
            stdout=(
                '{"status":"locked","detail":"lock marker present at .codegraphcontext/db/kuzudb.lock",'
                '"recovery_hint":{"command":"scripts/cgc_safe_index.py /tmp/repo"}}\n'
            ),
            stderr="",
        ),
    )

    probe = read_code_health.codegraph_health_probe()

    assert probe.status == "locked"
    assert "lock marker present" in probe.detail
    assert probe.recovery_command == "scripts/cgc_safe_index.py /tmp/repo"


def test_refresh_indexes_for_read_launches_async_codegraph_preflight_once_per_session(
    monkeypatch, tmp_path: Path
) -> None:
    """Read preflight should launch async codegraph preflight once per session."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    launch_calls = {"count": 0}

    monkeypatch.setattr(read_code_health, "_is_repo_local_path", lambda _path: True)
    monkeypatch.setattr(read_code_health, "codegraph_supports_file", lambda _path: True)
    monkeypatch.setattr(read_code_health, "_load_codegraph_session_probe_cache", lambda _sid: None)
    monkeypatch.setattr(
        read_code_health,
        "_launch_codegraph_preflight_background",
        lambda _path, _sid: launch_calls.__setitem__("count", launch_calls["count"] + 1) or True,
    )
    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", lambda _path, **kwargs: True)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_DONE", False)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_AVAILABLE", True)

    first = read_code_health._refresh_indexes_for_read(code_file)
    second = read_code_health._refresh_indexes_for_read(code_file)

    assert first is True
    assert second is True
    assert launch_calls["count"] == 1


def test_refresh_indexes_for_read_uses_cached_unavailable_without_blocking(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    """Read preflight should continue when cached codegraph availability is false."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    launch_calls = {"count": 0}

    monkeypatch.setattr(read_code_health, "_is_repo_local_path", lambda _path: True)
    monkeypatch.setattr(read_code_health, "codegraph_supports_file", lambda _path: True)
    monkeypatch.setattr(read_code_health, "_load_codegraph_session_probe_cache", lambda _sid: False)
    monkeypatch.setattr(
        read_code_health,
        "_launch_codegraph_preflight_background",
        lambda _path, _sid: launch_calls.__setitem__("count", launch_calls["count"] + 1) or True,
    )
    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", lambda _path, **kwargs: True)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_DONE", False)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_AVAILABLE", True)

    result = read_code_health._refresh_indexes_for_read(code_file)
    stderr = capsys.readouterr().err

    assert result is True
    assert launch_calls["count"] == 1
    assert stderr == ""


def test_refresh_indexes_for_read_uses_persisted_session_probe_cache(monkeypatch, tmp_path: Path) -> None:
    """Read preflight should reuse persisted cache while launching async preflight once."""
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    popen_calls = {"count": 0}

    monkeypatch.setattr(read_code_health, "_is_repo_local_path", lambda _path: True)
    monkeypatch.setattr(read_code_health, "codegraph_supports_file", lambda _path: True)
    monkeypatch.setattr(read_code_health, "_load_codegraph_session_probe_cache", lambda _sid: True)
    monkeypatch.setattr(read_code_health, "_read_code_session_id", lambda: "unit-session")
    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", lambda _path, **kwargs: True)
    monkeypatch.setattr(read_code_health, "_vector_command_env", lambda: {})
    monkeypatch.setattr(
        read_code_health.subprocess,
        "Popen",
        lambda *args, **kwargs: popen_calls.__setitem__("count", popen_calls["count"] + 1) or object(),
    )

    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_DONE", False)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_AVAILABLE", True)
    first = read_code_health._refresh_indexes_for_read(code_file)

    # Simulate a subsequent helper call in a fresh process.
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_DONE", False)
    monkeypatch.setattr(read_code_health, "_CODEGRAPH_SESSION_PROBE_AVAILABLE", True)
    second = read_code_health._refresh_indexes_for_read(code_file)

    assert first is True
    assert second is True
    assert popen_calls["count"] == 1


def test_codegraph_edit_signature_file_uses_codegraphcontext(tmp_path: Path) -> None:
    marker = read_code_health.codegraph_edit_signature_file(tmp_path)

    assert marker == tmp_path / ".codegraphcontext" / "last-edit-signature.txt"


def test_codegraph_cached_edit_signature_strips_trailing_newline(tmp_path: Path) -> None:
    marker = tmp_path / ".codegraphcontext" / "last-edit-signature.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(" M src/module.py\n", encoding="utf-8")

    cached = read_code_health.codegraph_cached_edit_signature(tmp_path)

    assert cached == " M src/module.py"


def test_codegraph_current_edit_signature_ignores_codegraphcontext_on_leading_space_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        read_code_health.subprocess,
        "run",
        lambda *args, **kwargs: _completed(0, stdout=" M .codegraphcontext/last-edit-signature.txt\n"),
    )

    signature = read_code_health.codegraph_current_edit_signature(tmp_path)

    assert signature == ""


def test_codegraph_refresh_if_needed_runs_scoped_refresh_for_stale_status(monkeypatch, tmp_path: Path) -> None:
    probe = read_code_health._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command="")
    monkeypatch.setattr(read_code_health, "codegraph_health_probe", lambda project_root=None: probe)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    monkeypatch.setattr(read_code_health, "_scope_needs_codegraph_refresh", lambda scope_path: True)
    monkeypatch.setattr(read_code_health, "codegraph_scoped_refresh_paths", lambda scope_path, project_root=None: [tmp_path / "src"])
    monkeypatch.setattr(read_code_health, "codegraph_health_status", lambda project_root=None: "healthy")

    calls: list[dict[str, object]] = []

    class FakeHook:
        def run_refresh_request(self, payload):
            calls.append(payload)
            return []

        def launch_refresh_request(self, payload):
            raise AssertionError("background refresh should not run")

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    scope_path = tmp_path / "src"
    scope_path.mkdir(parents=True, exist_ok=True)
    result = read_code.codegraph_refresh_if_needed(scope_path)

    assert result is True
    assert calls == [
        {
            "tool_input": {
                "paths": [str(tmp_path / "src")],
                "refresh_codegraph": True,
                "refresh_vector": False,
            }
        }
    ]


def test_codegraph_refresh_if_needed_retries_locked_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    probes = iter(
        [
            read_code_health._CodegraphHealthProbe(
                status="locked",
                detail="lock marker present at .codegraphcontext/db/kuzudb.lock",
                recovery_command="scripts/cgc_safe_index.py /tmp/repo",
            ),
            read_code_health._CodegraphHealthProbe(status="healthy", detail="ok", recovery_command=""),
        ]
    )
    monkeypatch.setattr(read_code_health, "codegraph_health_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    monkeypatch.setattr(read_code_health, "CODEGRAPH_LOCK_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(read_code_health.time, "sleep", lambda _: None)

    fake_script = tmp_path / "cgc_safe_index.py"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code_health, "_SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert result is True
    assert calls == [[str(fake_script), str(tmp_path / "src")]]


def test_codegraph_refresh_if_needed_skips_when_status_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_health_probe",
        lambda project_root=None: read_code_health._CodegraphHealthProbe(status="healthy", detail="ok", recovery_command=""),
    )
    monkeypatch.setattr(read_code_health, "_SCRIPT_DIR", tmp_path)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code_health.subprocess, "run", fake_run)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert result is True
    assert called["value"] is False


def test_codegraph_refresh_if_needed_fails_for_unavailable_status(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_health_probe",
        lambda project_root=None: read_code_health._CodegraphHealthProbe(
            status="unavailable",
            detail="doctor failed",
            recovery_command="scripts/cgc_safe_index.py /tmp/repo",
        ),
    )
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    fake_script = tmp_path / "cgc_safe_index.py"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code_health, "_SCRIPT_DIR", tmp_path)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")
    captured = capsys.readouterr()

    assert result is False
    assert "status is unavailable" in captured.err
    assert "Remediation:" in captured.err
    assert "doctor suggested:" in captured.err


def test_codegraph_refresh_if_needed_background_refreshes_when_scope_is_unaffected(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_health_probe",
        lambda project_root=None: read_code_health._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command=""),
    )
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_scope_needs_codegraph_refresh", lambda scope_path: False)
    monkeypatch.setattr(read_code_health, "codegraph_scoped_refresh_paths", lambda scope_path, project_root=None: [tmp_path / "src"])
    calls: list[dict[str, object]] = []

    class FakeHook:
        def run_refresh_request(self, payload):
            raise AssertionError("unexpected sync refresh")

        def launch_refresh_request(self, payload):
            calls.append(payload)
            return True

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    scope_path = tmp_path / "src"
    scope_path.mkdir(parents=True, exist_ok=True)
    result = read_code.codegraph_refresh_if_needed(scope_path)
    captured = capsys.readouterr()

    assert result is True
    assert calls == [
        {
            "tool_input": {
                "paths": [str(tmp_path / "src")],
                "refresh_codegraph": True,
                "refresh_vector": False,
            }
        }
    ]
    assert "overlap=no" in captured.err
    assert "launching async stale-scope refresh" in captured.err


def test_codegraph_refresh_if_needed_background_refresh_logs_when_launch_fails(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code_health,
        "codegraph_health_probe",
        lambda project_root=None: read_code_health._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command=""),
    )
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_scope_needs_codegraph_refresh", lambda scope_path: False)
    monkeypatch.setattr(read_code_health, "codegraph_scoped_refresh_paths", lambda scope_path, project_root=None: [tmp_path / "src"])
    class FakeHook:
        def run_refresh_request(self, payload):
            raise AssertionError("unexpected sync refresh")

        def launch_refresh_request(self, payload):
            return False

    monkeypatch.setattr(read_code_health, "_refresh_orchestrator", lambda: FakeHook())

    scope_path = tmp_path / "src"
    scope_path.mkdir(parents=True, exist_ok=True)
    result = read_code.codegraph_refresh_if_needed(scope_path)
    captured = capsys.readouterr()

    assert result is True
    assert "background refresh could not start" in captured.err


def test_codegraph_refresh_if_needed_bootstraps_when_snapshot_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    probes = iter(
        [
            read_code_health._CodegraphHealthProbe(status="missing", detail="snapshot missing", recovery_command=""),
            read_code_health._CodegraphHealthProbe(status="healthy", detail="", recovery_command=""),
        ]
    )
    monkeypatch.setattr(read_code_health, "codegraph_health_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)

    fake_script = tmp_path / "bootstrap_session.py"
    fake_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code_health, "_SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(read_code_health, "_run_command_capture", fake_run)

    scope_path = tmp_path / "src"
    scope_path.mkdir(parents=True, exist_ok=True)
    assert read_code.codegraph_refresh_if_needed(scope_path) is True
    assert calls == [
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            str(fake_script),
            "--scope",
            str(scope_path),
            "--json",
        ]
    ]


def test_scope_needs_codegraph_refresh_detects_overlap(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        read_code_health,
        "codegraph_current_edit_signature",
        lambda project_root=None: " M src/module.py\n",
    )
    monkeypatch.setattr(
        read_code_health,
        "codegraph_cached_edit_signature",
        lambda project_root=None: " M AGENTS.md\n",
    )

    assert read_code_health._scope_needs_codegraph_refresh(tmp_path / "src") is True
    assert read_code_health._scope_needs_codegraph_refresh(tmp_path / "docs") is False


def test_codegraph_discover_or_fail_skips_refresh_when_preflight_already_done(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    monkeypatch.setattr(
        read_code,
        "codegraph_refresh_if_needed",
        lambda scope_path=None: (_ for _ in ()).throw(AssertionError("refresh should be skipped")),
    )
    monkeypatch.setattr(read_code_health.subprocess, "run", lambda *args, **kwargs: _completed(0))

    result = read_code.codegraph_discover_or_fail(
        "run_pipeline",
        tmp_path / "src",
        skip_preflight_refresh=True,
    )

    assert result is True


def test_codegraph_discover_or_fail_refreshes_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code_health, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    calls: list[Path | None] = []
    monkeypatch.setattr(
        read_code,
        "codegraph_refresh_if_needed",
        lambda scope_path=None: (calls.append(scope_path), True)[1],
    )
    monkeypatch.setattr(read_code_health.subprocess, "run", lambda *args, **kwargs: _completed(0))

    scope = tmp_path / "src"
    result = read_code.codegraph_discover_or_fail("run_pipeline", scope)

    assert result is True
    assert calls == [scope]


def test_read_code_context_runs_index_preflight_before_anchor_resolution(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    calls: list[tuple[Path, dict[str, object]]] = []
    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda file_path, **kwargs: (calls.append((file_path, kwargs)), True)[1],
    )
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [
            _vector_match(1, "def run_pipeline():", confidence=95),
        ],
    )

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "0"])

    assert exit_code == 0
    assert calls == [(code_file, {"verbose": False, "request_is_scoped": True})]


def test_refresh_indexes_for_read_skips_vector_refresh_for_trusted_scoped_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_ensure_codegraph_session_available", lambda file_path: True)
    read_code_health._remember_vector_probe(
        "test-session",
        _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: docs/guide.md",
            stale_reason_class="git-path-drift",
            stale_drift_paths=("docs/guide.md",),
        ),
    )
    monkeypatch.setattr(
        read_code_health,
        "vector_refresh_by_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("heavy vector refresh should be skipped")),
    )

    assert read_code_health._refresh_indexes_for_read(scope_path, request_is_scoped=True) is True


def test_refresh_indexes_for_read_forwards_unscoped_request_to_vector_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    scope_path = tmp_path / "src" / "sample.py"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(read_code_health, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code_health, "_ensure_codegraph_session_available", lambda file_path: True)
    read_code_health._remember_vector_probe("test-session", _vector_probe(status="healthy"))

    called = {"value": False}

    def fake_vector_refresh_by_state(
        file_path: Path,
        *,
        verbose: bool = False,
        request_is_scoped: bool | None = None,
    ) -> bool:
        called["value"] = True
        assert request_is_scoped is False
        return True

    monkeypatch.setattr(read_code_health, "vector_refresh_by_state", fake_vector_refresh_by_state)

    assert read_code_health._refresh_indexes_for_read(scope_path, request_is_scoped=False) is True
    assert called["value"] is True


def test_split_context_window_biases_post_anchor_budget() -> None:
    max_lines = read_code.READ_CODE_MAX_LINES
    pre_lines, post_lines = read_code._split_context_window(max_lines)
    expected_pre = min(
        max(1, int(max_lines * read_code.READ_CODE_CONTEXT_PRE_FRACTION)),
        read_code.READ_CODE_CONTEXT_PRE_CAP,
        max_lines - 1,
    )
    assert pre_lines == expected_pre
    assert post_lines == max_lines - expected_pre

    pre_lines_small, post_lines_small = read_code._split_context_window(3)
    assert pre_lines_small == 1
    assert post_lines_small == 2


def test_select_semantic_anchor_candidate_rejects_out_of_range_index() -> None:
    candidates = [_vector_match(10, "def run_pipeline():"), _vector_match(20, "def helper():")]
    selected, error = read_code._select_semantic_anchor_candidate(candidates, 4)
    assert selected is None
    assert error == "candidate index 4 is out of range (available: 0..1)"


def test_select_semantic_anchor_candidate_returns_requested_index() -> None:
    candidates = [_vector_match(10, "def run_pipeline():"), _vector_match(20, "def helper():")]
    selected, error = read_code._select_semantic_anchor_candidate(candidates, 1)
    assert error is None
    assert selected is not None
    assert selected.line_num == 20


def test_parse_context_args_accepts_content_type_filter(tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def sample() -> int:\n    return 1\n", encoding="utf-8")

    parsed = read_code._parse_context_args(["sample", "--path", str(code_file), "--content-type", "tests"])

    assert parsed is not None
    assert parsed.file_path == code_file
    assert parsed.content_type == "tests"


def test_parse_context_args_rejects_invalid_content_type(capsys) -> None:
    parsed = read_code._parse_context_args(["sample", "--content-type", "nonsense"])

    captured = capsys.readouterr()
    assert parsed is None
    assert "--content-type expects one of: code, markdown, tests" in captured.err


def test_query_semantic_anchor_candidate_filters_to_markdown(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "src" / "sample.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text("def sample() -> int:\n    return 1\n", encoding="utf-8")
    markdown_file = tmp_path / "docs" / "guide.md"
    markdown_file.parent.mkdir(parents=True, exist_ok=True)
    markdown_file.write_text("# Guide\n", encoding="utf-8")

    code_match = _vector_match_at_path(code_file, 3, "def sample():", confidence=80)
    markdown_match = _vector_match_at_path(markdown_file, 1, "# Guide", confidence=90)

    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda file_path, query, normalized, scope, **kwargs: [code_match] if scope == "code" else [markdown_match],
    )

    candidates, selected, ok = read_code._query_semantic_anchor_candidate(
        None,
        "Guide",
        "Guide",
        candidate_index=0,
        show_shortlist_hint=False,
        content_type="markdown",
    )

    assert ok is True
    assert candidates == [markdown_match]
    assert selected == markdown_match


def test_query_semantic_anchor_candidate_filters_to_tests(monkeypatch, tmp_path: Path) -> None:
    prod_file = tmp_path / "src" / "sample.py"
    prod_file.parent.mkdir(parents=True, exist_ok=True)
    prod_file.write_text("def sample() -> int:\n    return 1\n", encoding="utf-8")
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("def test_sample() -> None:\n    pass\n", encoding="utf-8")

    prod_match = _vector_match_at_path(prod_file, 3, "def sample():", confidence=80)
    test_match = _vector_match_at_path(test_file, 1, "def test_sample():", confidence=90)

    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda file_path, query, normalized, scope, **kwargs: [prod_match, test_match] if scope == "code" else [],
    )

    candidates, selected, ok = read_code._query_semantic_anchor_candidate(
        None,
        "sample",
        "sample",
        candidate_index=0,
        show_shortlist_hint=False,
        content_type="tests",
    )

    assert ok is True
    assert candidates == [test_match]
    assert selected == test_match


def test_read_code_context_applies_asymmetric_window_bounds(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("\n".join(f"value_{idx} = {idx}" for idx in range(1, 231)) + "\n", encoding="utf-8")

    monkeypatch.setattr(read_code_health, "_refresh_indexes_for_read", lambda file_path, **kwargs: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(100, "def run_pipeline():")],
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)

    bounds: dict[str, int] = {}

    def fake_render(file_path: Path, start: int, end: int) -> None:
        bounds["start"] = start
        bounds["end"] = end

    monkeypatch.setattr(read_code, "_render_numbered_window", fake_render)

    max_lines = read_code.READ_CODE_MAX_LINES
    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", str(max_lines), "--inline-body"])

    assert exit_code == 0
    expected_pre = min(
        max(1, int(max_lines * read_code.READ_CODE_CONTEXT_PRE_FRACTION)),
        read_code.READ_CODE_CONTEXT_PRE_CAP,
        max_lines - 1,
    )
    assert bounds == {
        "start": 100 - expected_pre,
        "end": 100 + (max_lines - expected_pre),
    }


def test_read_code_context_returns_error_for_out_of_range_candidate_index(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(read_code_health, "_refresh_indexes_for_read", lambda file_path, **kwargs: True)
    def fake_find(file_path, query, normalized, scope, **kwargs):
        if scope == "code":
            return [_vector_match(1, "def run_pipeline():"), _vector_match(5, "def helper():")]
        return []

    monkeypatch.setattr(read_code, "_vector_find_candidates", fake_find)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "--candidate-index", "9"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "candidate index 9 is out of range (available: 0..1)" in captured.err
    assert "--show-shortlist" in captured.err


def test_read_code_context_skips_strict_when_semantic_anchor_is_strong(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "_refresh_indexes_for_read", lambda file_path, **kwargs: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(2, "def run_pipeline():", confidence=95)],
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "0"])

    assert exit_code == 0

def test_read_code_window_reports_disabled_mode(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\n", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "_refresh_indexes_for_read", lambda file_path, **kwargs: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(4, "def run_pipeline():", confidence=95)],
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)

    exit_code = read_code.read_code_window([str(code_file), "2", "3", "run_pipeline"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "window mode is disabled" in captured.err


def test_read_code_context_returns_error_when_preflight_fails(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(read_code_health, "_refresh_indexes_for_read", lambda file_path, **kwargs: False)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "0"])

    assert exit_code == 1


def test_read_code_main_rejects_symbols_mode(capsys) -> None:
    exit_code = read_code.main(["symbols", "pattern"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unknown mode 'symbols'" in captured.err


def test_read_code_main_forwards_verbose_flag_to_window_mode(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_window(argv: list[str], *, verbose: bool = False) -> int:
        captured["argv"] = argv
        captured["verbose"] = verbose
        return 0

    monkeypatch.setattr(read_code, "read_code_window", fake_window)

    exit_code = read_code.main(["--verbose", "window", "scripts/read_code.py", "1", "1"])

    assert exit_code == 0
    assert captured["verbose"] is True
    assert captured["argv"] == ["scripts/read_code.py", "1", "1"]
