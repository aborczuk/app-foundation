"""Unit tests for read-code index freshness checks and targeted refresh behavior."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def _load_module(module_name: str, script_name: str):
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


read_code = _load_module("read_code_index_refresh", "read_code.py")


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
) -> object:
    return read_code._VectorIndexProbe(
        status=status,
        stale_reason=stale_reason,
        stale_reason_class=stale_reason_class,
        stale_drift_paths=stale_drift_paths,
        stale_signal_source=stale_signal_source,
        stale_signal_available=stale_signal_available,
        stale_signal_error=stale_signal_error,
    )


def _vector_match(line_num: int, signature: str, *, confidence: int = 100) -> object:
    """Build a minimal ranked vector match for helper selection tests."""
    return read_code._VectorMatch(
        line_num=line_num,
        raw_score=1.0,
        metadata_score=10.0,
        confidence=confidence,
        exact_symbol_match=True,
        symbol_type="function",
        has_body=True,
        has_docstring=False,
        line_span=1,
        body=f"{signature}\n    pass",
        preview=signature,
        signature=signature,
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

    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    matches = read_code._vector_query_candidates(code_file, "sample", "sample", "code")

    assert matches
    assert matches[0].line_num == 1
    assert "cmd" in captured
    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--file-path" in cmd
    file_flag_index = cmd.index("--file-path")
    assert cmd[file_flag_index + 1] == str(code_file.resolve())


def test_vector_index_status_reports_missing_for_null_payload(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout="null\n"))

    status = read_code.vector_index_status()

    assert status == "missing"


def test_vector_index_probe_parses_stale_payload_with_cause_details(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code.subprocess,
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

    probe = read_code.vector_index_probe()

    assert probe.status == "stale"
    assert probe.stale_reason_class == "git-path-drift"
    assert probe.stale_drift_paths == ("src/sample.py",)
    assert "src/sample.py" in probe.stale_reason


def test_vector_index_status_reports_healthy_when_status_payload_is_fresh(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0, stdout='{"is_stale": false}\n'))

    status = read_code.vector_index_status()

    assert status == "healthy"


def test_vector_refresh_if_needed_fails_fast_for_missing_index(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "vector_index_probe", lambda project_root=None: _vector_probe(status="missing"))
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0, stdout='{"entry_count": 1}')

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    target = tmp_path / "sample.py"
    result = read_code.vector_refresh_if_needed(target)

    assert result is False
    assert called["value"] is False


def test_vector_refresh_if_needed_skips_when_index_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "vector_index_probe", lambda project_root=None: _vector_probe(status="healthy"))
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    result = read_code.vector_refresh_if_needed(tmp_path / "sample.py")

    assert result is True
    assert called["value"] is False


def test_vector_refresh_if_needed_refreshes_stale_index_for_overlap(monkeypatch, tmp_path: Path, capsys) -> None:
    target = tmp_path / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def sample() -> None:\n    pass\n", encoding="utf-8")
    probes = iter(
        [
            _vector_probe(
                status="stale",
                stale_reason="indexable git drift paths: src/sample.py",
                stale_reason_class="git-path-drift",
                stale_drift_paths=("src/sample.py",),
            ),
            _vector_probe(status="healthy"),
        ]
    )
    calls: list[tuple[list[str], dict[str, str]]] = []

    monkeypatch.setattr(read_code, "vector_index_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs.get("env", {})))
        return _completed(0, stdout='{"entry_count": 1}')

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    result = read_code.vector_refresh_if_needed(target)
    captured = capsys.readouterr()

    assert result is True
    assert len(calls) == 1
    assert "cause=git-path-drift" in captured.err
    assert "overlap=yes" in captured.err


def test_vector_refresh_if_needed_background_refreshes_when_scope_is_unaffected(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code,
        "vector_index_probe",
        lambda project_root=None: _vector_probe(
            status="stale",
            stale_reason="indexable git drift paths: docs/guide.md",
            stale_reason_class="git-path-drift",
            stale_drift_paths=("docs/guide.md",),
        ),
    )
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)

    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return object()

    monkeypatch.setattr(read_code.subprocess, "Popen", fake_popen)

    result = read_code.vector_refresh_if_needed(tmp_path / "src" / "sample.py")
    captured = capsys.readouterr()

    assert result is True
    assert calls
    assert "cause=git-path-drift" in captured.err
    assert "overlap=no" in captured.err


def test_vector_refresh_if_needed_proceeds_when_post_refresh_stale_is_out_of_scope(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    probes = iter(
        [
            _vector_probe(
                status="stale",
                stale_reason="indexable git drift paths: src/sample.py",
                stale_reason_class="git-path-drift",
                stale_drift_paths=("src/sample.py",),
            ),
            _vector_probe(
                status="stale",
                stale_reason="indexable git drift paths: docs/guide.md",
                stale_reason_class="git-path-drift",
                stale_drift_paths=("docs/guide.md",),
            ),
        ]
    )
    monkeypatch.setattr(read_code, "vector_index_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0))

    background_calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        background_calls.append(cmd)
        return object()

    monkeypatch.setattr(read_code.subprocess, "Popen", fake_popen)

    result = read_code.vector_refresh_if_needed(tmp_path / "src" / "sample.py")
    captured = capsys.readouterr()

    assert result is True
    assert background_calls
    assert "remains stale after scoped refresh" in captured.err


def test_codegraph_health_status_reports_unavailable_without_uv(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: False)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0, stdout='{"status":"healthy"}')

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    status = read_code.codegraph_health_status()

    assert status == "unavailable"
    assert called["value"] is False


def test_codegraph_health_status_parses_nonhealthy_json_payload(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: _completed(1, stdout='{"status":"stale"}\n', stderr="stale"),
    )

    status = read_code.codegraph_health_status()

    assert status == "stale"


def test_codegraph_health_probe_returns_detail_and_recovery_command(monkeypatch) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: _completed(
            0,
            stdout=(
                '{"status":"locked","detail":"lock marker present at .codegraphcontext/db/kuzudb.lock",'
                '"recovery_hint":{"command":"scripts/cgc_safe_index.sh /tmp/repo"}}\n'
            ),
            stderr="",
        ),
    )

    probe = read_code.codegraph_health_probe()

    assert probe.status == "locked"
    assert "lock marker present" in probe.detail
    assert probe.recovery_command == "scripts/cgc_safe_index.sh /tmp/repo"


def test_codegraph_edit_signature_file_uses_codegraphcontext(tmp_path: Path) -> None:
    marker = read_code.codegraph_edit_signature_file(tmp_path)

    assert marker == tmp_path / ".codegraphcontext" / "last-edit-signature.txt"


def test_codegraph_cached_edit_signature_strips_trailing_newline(tmp_path: Path) -> None:
    marker = tmp_path / ".codegraphcontext" / "last-edit-signature.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(" M src/module.py\n", encoding="utf-8")

    cached = read_code.codegraph_cached_edit_signature(tmp_path)

    assert cached == " M src/module.py"


def test_codegraph_current_edit_signature_ignores_codegraphcontext_on_leading_space_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        read_code.subprocess,
        "run",
        lambda *args, **kwargs: _completed(0, stdout=" M .codegraphcontext/last-edit-signature.txt\n"),
    )

    signature = read_code.codegraph_current_edit_signature(tmp_path)

    assert signature == ""


def test_codegraph_refresh_if_needed_runs_scoped_refresh_for_stale_status(monkeypatch, tmp_path: Path) -> None:
    probes = iter(
        [
            read_code._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command=""),
            read_code._CodegraphHealthProbe(status="healthy", detail="ok", recovery_command=""),
        ]
    )
    monkeypatch.setattr(read_code, "codegraph_health_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    monkeypatch.setattr(read_code, "_scope_needs_codegraph_refresh", lambda scope_path: True)

    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    scope_path = tmp_path / "src"
    result = read_code.codegraph_refresh_if_needed(scope_path)

    assert result is True
    assert calls == [[str(fake_script), str(scope_path)]]


def test_codegraph_refresh_if_needed_retries_locked_then_succeeds(monkeypatch, tmp_path: Path) -> None:
    probes = iter(
        [
            read_code._CodegraphHealthProbe(
                status="locked",
                detail="lock marker present at .codegraphcontext/db/kuzudb.lock",
                recovery_command="scripts/cgc_safe_index.sh /tmp/repo",
            ),
            read_code._CodegraphHealthProbe(status="healthy", detail="ok", recovery_command=""),
        ]
    )
    monkeypatch.setattr(read_code, "codegraph_health_probe", lambda project_root=None: next(probes))
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    monkeypatch.setattr(read_code, "CODEGRAPH_LOCK_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(read_code.time, "sleep", lambda _: None)

    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert result is True
    assert calls == [[str(fake_script), str(tmp_path / "src")]]


def test_codegraph_refresh_if_needed_skips_when_status_is_healthy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        read_code,
        "codegraph_health_probe",
        lambda project_root=None: read_code._CodegraphHealthProbe(status="healthy", detail="ok", recovery_command=""),
    )
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    called = {"value": False}

    def fake_run(*args, **kwargs):
        called["value"] = True
        return _completed(0)

    monkeypatch.setattr(read_code.subprocess, "run", fake_run)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert result is True
    assert called["value"] is False


def test_codegraph_refresh_if_needed_fails_for_unavailable_status(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        read_code,
        "codegraph_health_probe",
        lambda project_root=None: read_code._CodegraphHealthProbe(
            status="unavailable",
            detail="doctor failed",
            recovery_command="scripts/cgc_safe_index.sh /tmp/repo",
        ),
    )
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)
    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")
    captured = capsys.readouterr()

    assert result is False
    assert "status is unavailable" in captured.err
    assert "Remediation:" in captured.err
    assert "doctor suggested:" in captured.err


def test_codegraph_refresh_if_needed_background_refreshes_when_scope_is_unaffected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        read_code,
        "codegraph_health_probe",
        lambda project_root=None: read_code._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command=""),
    )
    monkeypatch.setattr(read_code, "_scope_needs_codegraph_refresh", lambda scope_path: False)
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)

    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        calls.append(cmd)
        return object()

    monkeypatch.setattr(read_code.subprocess, "Popen", fake_popen)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")

    assert result is True
    assert calls == [[str(fake_script), str(tmp_path / "src")]]


def test_codegraph_refresh_if_needed_background_refresh_logs_when_launch_fails(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    monkeypatch.setattr(
        read_code,
        "codegraph_health_probe",
        lambda project_root=None: read_code._CodegraphHealthProbe(status="stale", detail="dirty tree", recovery_command=""),
    )
    monkeypatch.setattr(read_code, "_scope_needs_codegraph_refresh", lambda scope_path: False)
    monkeypatch.setattr(read_code.os, "access", lambda path, mode: True)

    fake_script = tmp_path / "cgc_safe_index.sh"
    fake_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    fake_script.chmod(0o755)
    monkeypatch.setattr(read_code, "SCRIPT_DIR", tmp_path)

    def fake_popen(cmd, **kwargs):
        raise OSError("launch failed")

    monkeypatch.setattr(read_code.subprocess, "Popen", fake_popen)

    result = read_code.codegraph_refresh_if_needed(tmp_path / "src")
    captured = capsys.readouterr()

    assert result is True
    assert "background refresh could not start" in captured.err


def test_scope_needs_codegraph_refresh_detects_overlap(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        read_code,
        "codegraph_current_edit_signature",
        lambda project_root=None: " M src/module.py\n",
    )
    monkeypatch.setattr(
        read_code,
        "codegraph_cached_edit_signature",
        lambda project_root=None: " M AGENTS.md\n",
    )

    assert read_code._scope_needs_codegraph_refresh(tmp_path / "src") is True
    assert read_code._scope_needs_codegraph_refresh(tmp_path / "docs") is False


def test_codegraph_discover_or_fail_skips_refresh_when_preflight_already_done(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    monkeypatch.setattr(
        read_code,
        "codegraph_refresh_if_needed",
        lambda scope_path=None: (_ for _ in ()).throw(AssertionError("refresh should be skipped")),
    )
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0))

    result = read_code.codegraph_discover_or_fail(
        "run_pipeline",
        tmp_path / "src",
        skip_preflight_refresh=True,
    )

    assert result is True


def test_codegraph_discover_or_fail_refreshes_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(read_code, "_command_exists", lambda name: True)
    monkeypatch.setattr(read_code, "init_codegraph_env", lambda: None)
    calls: list[Path | None] = []
    monkeypatch.setattr(
        read_code,
        "codegraph_refresh_if_needed",
        lambda scope_path=None: (calls.append(scope_path), True)[1],
    )
    monkeypatch.setattr(read_code.subprocess, "run", lambda *args, **kwargs: _completed(0))

    scope = tmp_path / "src"
    result = read_code.codegraph_discover_or_fail("run_pipeline", scope)

    assert result is True
    assert calls == [scope]


def test_read_code_context_runs_index_preflight_before_anchor_resolution(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    calls: list[Path] = []
    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda file_path: (calls.append(file_path), True)[1],
    )
    monkeypatch.setattr(
        read_code,
        "_vector_find_line_num",
        lambda *args, **kwargs: read_code._VectorMatch(
            line_num=1,
            raw_score=0.9,
            metadata_score=5.0,
            exact_symbol_match=True,
            symbol_type="function",
            has_body=True,
            has_docstring=False,
            line_span=1,
        ),
    )
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (0, 1))

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])

    assert exit_code == 0
    assert calls == [code_file]


def test_split_context_window_biases_post_anchor_budget() -> None:
    pre_lines, post_lines = read_code._split_context_window(125)
    expected_pre = min(
        max(1, int(125 * read_code.READ_CODE_CONTEXT_PRE_FRACTION)),
        read_code.READ_CODE_CONTEXT_PRE_CAP,
        124,
    )
    assert pre_lines == expected_pre
    assert post_lines == 125 - expected_pre

    pre_lines_small, post_lines_small = read_code._split_context_window(3)
    assert pre_lines_small == 1
    assert post_lines_small == 2


def test_select_vector_candidate_rejects_out_of_range_index() -> None:
    candidates = [_vector_match(10, "def run_pipeline():"), _vector_match(20, "def helper():")]
    selected, error = read_code._select_vector_candidate(candidates, 4)
    assert selected is None
    assert error == "candidate index 4 is out of range (available: 0..1)"


def test_select_vector_candidate_returns_requested_index() -> None:
    candidates = [_vector_match(10, "def run_pipeline():"), _vector_match(20, "def helper():")]
    selected, error = read_code._select_vector_candidate(candidates, 1)
    assert error is None
    assert selected is not None
    assert selected.line_num == 20


def test_read_code_context_applies_asymmetric_window_bounds(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("\n".join(f"value_{idx} = {idx}" for idx in range(1, 231)) + "\n", encoding="utf-8")

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(read_code, "_vector_find_candidates", lambda *args, **kwargs: [])
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (0, 100))
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)

    bounds: dict[str, int] = {}

    def fake_render(file_path: Path, start: int, end: int) -> None:
        bounds["start"] = start
        bounds["end"] = end

    monkeypatch.setattr(read_code, "_render_numbered_window", fake_render)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "125"])

    assert exit_code == 0
    expected_pre = min(
        max(1, int(125 * read_code.READ_CODE_CONTEXT_PRE_FRACTION)),
        read_code.READ_CODE_CONTEXT_PRE_CAP,
        124,
    )
    assert bounds == {"start": 100 - expected_pre, "end": 100 + (125 - expected_pre)}


def test_read_code_context_returns_error_for_out_of_range_candidate_index(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(1, "def run_pipeline():"), _vector_match(5, "def helper():")],
    )

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "--candidate-index", "9"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "candidate index 9 is out of range (available: 0..1)" in captured.err
    assert "--show-shortlist" in captured.err


def test_read_code_context_skips_strict_when_semantic_anchor_is_strong(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(2, "def run_pipeline():", confidence=95)],
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_line_num_strict",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strict should not run")),
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])

    assert exit_code == 0


def test_read_code_context_uses_next_strong_semantic_candidate_before_strict(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [
            _vector_match(1, "def weak():", confidence=42),
            _vector_match(3, "def strong():", confidence=97),
        ],
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_line_num_strict",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strict should not run")),
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "using candidate 1 confidence 97" in captured.err


def test_read_code_context_falls_back_to_strict_when_semantic_candidates_are_weak(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(1, "def weak():", confidence=40)],
    )
    monkeypatch.setattr(read_code, "_resolve_line_num_strict", lambda *args, **kwargs: (0, 4))
    monkeypatch.setattr(read_code, "_render_numbered_window", lambda *args, **kwargs: None)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "below confidence threshold" in captured.err


def test_read_code_window_skips_strict_when_semantic_anchor_is_strong(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("line1\nline2\nline3\nline4\nline5\nline6\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_find_candidates",
        lambda *args, **kwargs: [_vector_match(4, "def run_pipeline():", confidence=95)],
    )
    monkeypatch.setattr(
        read_code,
        "_resolve_line_num_strict",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("strict should not run")),
    )
    monkeypatch.setattr(read_code, "_emit_vector_fallback_notice", lambda **kwargs: None)

    rendered: dict[str, int] = {}

    def fake_render(file_path: Path, start: int, end: int) -> None:
        rendered["start"] = start
        rendered["end"] = end

    monkeypatch.setattr(read_code, "_render_numbered_window", fake_render)

    exit_code = read_code.read_code_window([str(code_file), "1", "3", "run_pipeline"])

    assert exit_code == 0
    assert rendered == {"start": 4, "end": 6}


def test_read_code_context_returns_error_when_preflight_fails(monkeypatch, tmp_path: Path) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: False)

    exit_code = read_code.read_code_context([str(code_file), "run_pipeline", "1"])

    assert exit_code == 1


def test_read_code_symbols_runs_preflight_and_renders_rows(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")

    calls: list[Path] = []
    monkeypatch.setattr(
        read_code,
        "_refresh_indexes_for_read",
        lambda file_path: (calls.append(file_path), True)[1],
    )
    monkeypatch.setattr(
        read_code,
        "_vector_list_code_symbols",
        lambda file_path: [
            {
                "symbol_name": "run_pipeline",
                "symbol_type": "function",
                "line_start": 1,
                "line_end": 2,
                "signature": "def run_pipeline():",
                "qualified_name": "sample.run_pipeline",
                "body": "def run_pipeline():\n    return 1\n",
            }
        ],
    )

    exit_code = read_code.read_code_symbols([str(code_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [code_file]
    assert "symbol_name" in captured.out
    assert "run_pipeline" in captured.out


def test_read_code_symbols_repeat_guard_blocks_unchanged_file(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_list_code_symbols",
        lambda file_path: [
            {
                "symbol_name": "run_pipeline",
                "symbol_type": "function",
                "line_start": 1,
                "line_end": 2,
                "signature": "def run_pipeline():",
                "qualified_name": "sample.run_pipeline",
                "body": "def run_pipeline():\n    return 1\n",
            }
        ],
    )
    monkeypatch.setattr(read_code, "READ_CODE_SYMBOLS_USAGE_FILE", tmp_path / "symbols-usage.json")
    monkeypatch.setattr(read_code, "READ_CODE_SYMBOLS_REPEAT_COOLDOWN_SECONDS", 900)

    first_exit = read_code.read_code_symbols([str(code_file)])
    second_exit = read_code.read_code_symbols([str(code_file)])
    captured = capsys.readouterr()

    assert first_exit == 0
    assert second_exit == 1
    assert "repeat guard" in captured.err
    assert "--allow-repeat" in captured.err


def test_read_code_symbols_repeat_guard_allows_override(monkeypatch, tmp_path: Path, capsys) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(
        read_code,
        "_vector_list_code_symbols",
        lambda file_path: [
            {
                "symbol_name": "run_pipeline",
                "symbol_type": "function",
                "line_start": 1,
                "line_end": 2,
                "signature": "def run_pipeline():",
                "qualified_name": "sample.run_pipeline",
                "body": "def run_pipeline():\n    return 1\n",
            }
        ],
    )
    monkeypatch.setattr(read_code, "READ_CODE_SYMBOLS_USAGE_FILE", tmp_path / "symbols-usage.json")
    monkeypatch.setattr(read_code, "READ_CODE_SYMBOLS_REPEAT_COOLDOWN_SECONDS", 900)

    first_exit = read_code.read_code_symbols([str(code_file)])
    override_exit = read_code.read_code_symbols([str(code_file), "--allow-repeat"])
    captured = capsys.readouterr()

    assert first_exit == 0
    assert override_exit == 0
    assert "repeat guard" not in captured.err


def test_read_code_symbols_returns_error_when_vector_symbols_missing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    code_file = tmp_path / "sample.py"
    code_file.write_text("def run_pipeline():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(read_code, "_refresh_indexes_for_read", lambda file_path: True)
    monkeypatch.setattr(read_code, "_vector_list_code_symbols", lambda file_path: [])

    exit_code = read_code.read_code_symbols([str(code_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "No code symbols found" in captured.err
