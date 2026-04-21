#!/usr/bin/env python3
"""Python entrypoint for vector-first, symbol-checked code reads."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve()
SCRIPT_DIR = SOURCE_PATH.parent
REPO_ROOT = SCRIPT_DIR.parent
CODEGRAPH_CONTEXT_DIR = REPO_ROOT / ".codegraphcontext"
CODEGRAPH_DB_DIR = CODEGRAPH_CONTEXT_DIR / "db"
VECTOR_DB_DIR = CODEGRAPH_CONTEXT_DIR / "global" / "db" / "vector-index"
VECTOR_BOOTSTRAP_COMMAND = "uv run --no-sync python -m src.mcp_codebase.indexer --repo-root . bootstrap"

CODE_FILE_LINE_THRESHOLD = 200
READ_CODE_DEFAULT_CONTEXT_LINES = 60
READ_CODE_DEFAULT_WINDOW_LINES = 60
READ_CODE_MAX_LINES = int(os.environ.get("SPECKIT_READ_CODE_MAX_LINES", "110") or "110")
IGNORE_DIRS_DEFAULT = (
    "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,"
    "__pycache__,.uv-cache,logs,shadow-runs"
)
LAST_EDIT_SIGNATURE_FILE = CODEGRAPH_CONTEXT_DIR / "last-edit-signature.txt"


@dataclass(frozen=True)
class _VectorMatch:
    """Candidate vector hit plus ranking features used for anchoring."""

    line_num: int
    raw_score: float
    metadata_score: float
    exact_symbol_match: bool
    symbol_type: str
    has_body: bool
    has_docstring: bool
    line_span: int


_VECTOR_RUNTIME_NOTE: str | None = None


def _set_vector_runtime_note(note: str) -> None:
    """Track why vector lookup could not be used for the current resolution attempt."""
    global _VECTOR_RUNTIME_NOTE
    if not _VECTOR_RUNTIME_NOTE:
        _VECTOR_RUNTIME_NOTE = note


def _clear_vector_runtime_note() -> None:
    """Reset per-attempt vector runtime diagnostics."""
    global _VECTOR_RUNTIME_NOTE
    _VECTOR_RUNTIME_NOTE = None


def _consume_vector_runtime_note() -> str | None:
    """Return and clear the current vector runtime diagnostic note."""
    global _VECTOR_RUNTIME_NOTE
    note = _VECTOR_RUNTIME_NOTE
    _VECTOR_RUNTIME_NOTE = None
    return note


def _emit_vector_fallback_notice(
    *,
    file_path: Path,
    pattern: str,
    vector_match: _VectorMatch | None,
    resolved_line: int | None,
) -> None:
    """Emit explicit fallback messaging when semantic anchor selection is not used."""
    if not pattern or vector_match is not None:
        _consume_vector_runtime_note()
        return

    runtime_note = _consume_vector_runtime_note()
    if resolved_line is not None:
        if runtime_note:
            print(
                f"WARN: Vector semantic anchor unavailable ({runtime_note}); using strict/local anchor for '{pattern}' in {file_path}.",
                file=sys.stderr,
            )
        else:
            print(
                f"WARN: Vector semantic anchor not found for '{pattern}' in {file_path}; using strict/local anchor.",
                file=sys.stderr,
            )
        return

    if runtime_note:
        print(
            f"WARN: Vector semantic anchor unavailable ({runtime_note}) for '{pattern}' in {file_path}.",
            file=sys.stderr,
        )


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def _is_repo_local_path(file_path: Path) -> bool:
    """Return whether a target file resides under the repository root."""
    try:
        file_path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def _coerce_line(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    return None


def init_codegraph_env() -> None:
    """Set deterministic codegraph runtime paths for this repo."""
    repo_uv_cache = Path(os.environ.get("CGC_UV_CACHE_DIR", str(CODEGRAPH_CONTEXT_DIR / ".uv-cache")))
    CODEGRAPH_DB_DIR.mkdir(parents=True, exist_ok=True)
    repo_uv_cache.mkdir(parents=True, exist_ok=True)

    os.environ["UV_CACHE_DIR"] = str(repo_uv_cache)
    os.environ.setdefault("DEFAULT_DATABASE", "kuzudb")
    os.environ.setdefault("FALKORDB_PATH", str(CODEGRAPH_DB_DIR / "falkordb"))
    os.environ.setdefault("FALKORDB_SOCKET_PATH", str(CODEGRAPH_DB_DIR / "falkordb.sock"))
    os.environ.setdefault("KUZUDB_PATH", str(CODEGRAPH_DB_DIR / "kuzudb"))
    os.environ.setdefault("IGNORE_DIRS", IGNORE_DIRS_DEFAULT)


def codegraph_edit_signature_file(project_root: Path | None = None) -> Path:
    """Return the cached edit-signature marker path."""
    root = project_root or REPO_ROOT
    return root / LAST_EDIT_SIGNATURE_FILE.name


def codegraph_cached_edit_signature(project_root: Path | None = None) -> str:
    """Read the cached edit signature if it exists."""
    marker_file = codegraph_edit_signature_file(project_root)
    if not marker_file.is_file():
        return ""
    try:
        return marker_file.read_text(encoding="utf-8")
    except OSError:
        return ""


def codegraph_current_edit_signature(project_root: Path | None = None) -> str:
    """Return the current non-ignored git status signature."""
    root = project_root or REPO_ROOT
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""

    ignored_prefixes = (
        ".codegraphcontext/",
        ".speckit/",
        ".uv-cache/",
        "logs/",
        "shadow-runs/",
    )
    lines: list[str] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            candidates = [part.strip() for part in path.split(" -> ")]
        else:
            candidates = [path.strip()]
        if any(candidate.startswith(ignored_prefixes) for candidate in candidates if candidate):
            continue
        lines.append(line)

    return "\n".join(sorted(dict.fromkeys(lines)))


def codegraph_health_status(project_root: Path | None = None) -> str:
    """Return codegraph health status string or probe-failed."""
    root = project_root or REPO_ROOT
    if not _command_exists("uv"):
        print("WARN: codegraph health probe skipped because uv is not available", file=sys.stderr)
        return "unavailable"
    proc = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "src.mcp_codebase.doctor",
            "--json",
            "--project-root",
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = (proc.stdout or "").strip()
    status = ""
    if payload:
        try:
            status = str(json.loads(payload).get("status", ""))
        except json.JSONDecodeError:
            print("WARN: codegraph health probe returned non-JSON output", file=sys.stderr)
            status = ""

    if not status:
        doctor_err = (proc.stderr or "").strip()
        if doctor_err:
            print(f"WARN: codegraph health probe failed: {doctor_err}", file=sys.stderr)
        return "probe-failed"

    if status == "healthy":
        current_signature = codegraph_current_edit_signature(root)
        cached_signature = codegraph_cached_edit_signature(root)
        if current_signature != cached_signature:
            print(
                f"WARN: local working-tree edits changed since the last graph refresh; marking codegraph stale for {root}",
                file=sys.stderr,
            )
            return "stale"
    return status or "probe-failed"


def codegraph_refresh_if_needed(scope_path: Path | None = None) -> bool:
    """Refresh scoped codegraph index when stale; fail only for unavailable probe states."""
    path = scope_path or REPO_ROOT
    health_status = codegraph_health_status(REPO_ROOT)
    if health_status == "healthy":
        return True
    if health_status != "stale":
        print(f"ERROR: codegraph preflight failed: status is {health_status}", file=sys.stderr)
        return False

    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    if not (safe_index.is_file() and os.access(safe_index, os.X_OK)):
        print(f"ERROR: codegraph preflight failed: missing safe index script at {safe_index}", file=sys.stderr)
        return False
    print(
        f"WARN: codegraph is stale; refreshing scoped index for {path}",
        file=sys.stderr,
    )
    proc = subprocess.run([str(safe_index), str(path)], check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            print(f"ERROR: codegraph refresh failed: {stderr.splitlines()[-1]}", file=sys.stderr)
        else:
            print(f"ERROR: codegraph refresh failed with exit code {proc.returncode}", file=sys.stderr)
        return False

    refreshed_status = codegraph_health_status(REPO_ROOT)
    if refreshed_status in {"unavailable", "probe-failed", "locked"}:
        print(f"ERROR: codegraph preflight failed after refresh: status is {refreshed_status}", file=sys.stderr)
        return False
    if refreshed_status == "stale":
        print("ERROR: codegraph preflight failed after refresh: status is stale", file=sys.stderr)
        return False
    return refreshed_status == "healthy"


def vector_index_status(project_root: Path | None = None) -> str:
    """Return vector index freshness state: healthy, stale, missing, unavailable, or probe-failed."""
    root = project_root or REPO_ROOT
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return "unavailable"

    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(root),
        "status",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"index status probe failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"index status probe failed with exit code {proc.returncode}")
        return "probe-failed"

    payload = (proc.stdout or "").strip()
    if payload in {"", "null"}:
        return "missing"

    try:
        status_payload = json.loads(payload)
    except json.JSONDecodeError:
        _set_vector_runtime_note("index status probe returned non-JSON output")
        return "probe-failed"
    if not isinstance(status_payload, dict):
        _set_vector_runtime_note("index status probe returned unexpected payload shape")
        return "probe-failed"
    if bool(status_payload.get("is_stale", False)):
        return "stale"
    return "healthy"


def vector_refresh_if_needed(scope_path: Path | None = None) -> bool:
    """Require a healthy vector index and refresh stale snapshots in-place."""
    path = scope_path or REPO_ROOT
    status = vector_index_status(REPO_ROOT)
    if status == "healthy":
        return True
    if status in {"missing", "unavailable", "probe-failed"}:
        if status == "missing":
            _set_vector_runtime_note(
                f"index snapshot missing at {VECTOR_DB_DIR}; run `{VECTOR_BOOTSTRAP_COMMAND}`"
            )
        print(f"ERROR: vector preflight failed: status is {status}", file=sys.stderr)
        return False
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        print("ERROR: vector preflight failed: uv is not available", file=sys.stderr)
        return False

    print(f"WARN: vector index is stale; refreshing targeted index for {path}", file=sys.stderr)
    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(REPO_ROOT),
        "refresh",
        str(path),
    ]
    env = os.environ.copy()
    env.setdefault("HF_HUB_OFFLINE", "1")
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"index refresh failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"index refresh failed with exit code {proc.returncode}")
        print("ERROR: vector preflight failed: targeted refresh did not complete", file=sys.stderr)
        return False

    refreshed_status = vector_index_status(REPO_ROOT)
    if refreshed_status != "healthy":
        _set_vector_runtime_note(f"index status after refresh is {refreshed_status}")
        print(f"ERROR: vector preflight failed after refresh: status is {refreshed_status}", file=sys.stderr)
        return False
    return True


def _refresh_indexes_for_read(file_path: Path) -> bool:
    """Run read preflight checks and require both codegraph/vector indexes to be healthy."""
    if not _is_repo_local_path(file_path):
        return True
    if codegraph_supports_file(file_path) and not codegraph_refresh_if_needed(file_path.parent):
        return False
    if not vector_refresh_if_needed(file_path):
        runtime_note = _consume_vector_runtime_note()
        if runtime_note:
            print(f"ERROR: {runtime_note}", file=sys.stderr)
        print(
            "ERROR: read-code preflight requires a healthy vector index; run "
            f"`{VECTOR_BOOTSTRAP_COMMAND}`",
            file=sys.stderr,
        )
        return False
    return True


def codegraph_supports_file(file_path: Path) -> bool:
    """Return whether codegraph discovery should run for this extension."""
    supported_extensions = {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".go",
        ".ts",
        ".tsx",
        ".cpp",
        ".h",
        ".hpp",
        ".hh",
        ".rs",
        ".c",
        ".java",
        ".rb",
        ".cs",
        ".php",
        ".kt",
        ".scala",
        ".sc",
        ".swift",
        ".hs",
        ".dart",
        ".pl",
        ".pm",
        ".ex",
        ".exs",
    }
    if file_path.suffix in supported_extensions:
        return True
    print(f"WARN: unsupported file type for codegraph discovery: {file_path}", file=sys.stderr)
    return False


def _tail_lines(text: str, count: int = 20) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-count:]


def codegraph_discover_or_fail(pattern: str, scope_path: Path | None = None) -> bool:
    """Run bounded codegraph discovery and self-heal index fragility once."""
    if not pattern:
        print("ERROR: codegraph discovery requires a non-empty symbol_or_pattern", file=sys.stderr)
        return False

    if not _command_exists("uv"):
        print("ERROR: uv is required for codegraph discovery (uv run cgc ...)", file=sys.stderr)
        return False

    path = scope_path or REPO_ROOT
    init_codegraph_env()
    codegraph_refresh_if_needed(path)

    cmd = ["uv", "run", "--no-sync", "cgc", "find", "pattern", "--", pattern]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode == 0:
        return True

    output = (proc.stdout or "") + (proc.stderr or "")
    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    has_self_heal_pattern = "Database Connection Error" in output or "No index metadata" in output
    if has_self_heal_pattern and safe_index.is_file() and os.access(safe_index, os.X_OK):
        subprocess.run([str(safe_index), str(path)], check=False, capture_output=True, text=True)
        second = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if second.returncode == 0:
            return True
        output = (second.stdout or "") + (second.stderr or "")

    print(f"ERROR: codegraph discovery failed for pattern: {pattern}", file=sys.stderr)
    print("Hint: run scripts/cgc_safe_index.sh <scoped-path> and retry.", file=sys.stderr)
    for line in _tail_lines(output, count=20):
        print(line, file=sys.stderr)
    return False


def normalize_symbol_pattern(raw: str) -> str:
    """Normalize common declaration prefixes and suffix delimiters."""
    normalized = raw.strip()
    for prefix in ("async def ", "def ", "class "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    normalized = normalized.split("(", 1)[0]
    normalized = normalized.split(":", 1)[0]
    normalized = normalized.split(maxsplit=1)[0] if normalized else normalized
    return normalized


def _resolve_candidate_file(item: dict[str, object]) -> str | None:
    candidate = item.get("file_path")
    if isinstance(candidate, str) and candidate:
        return candidate
    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("file_path")
        if isinstance(nested, str) and nested:
            return nested
    return None


def _resolve_candidate_line(item: dict[str, object]) -> int | None:
    line = _coerce_line(item.get("line_start"))
    if line is not None:
        return line
    content = item.get("content")
    if isinstance(content, dict):
        return _coerce_line(content.get("line_start"))
    return None


def _candidate_text(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get(key)
        if isinstance(nested, str):
            return nested
    return ""


def _candidate_int(item: dict[str, object], key: str) -> int | None:
    value = item.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get(key)
        if isinstance(nested, int):
            return nested
        if isinstance(nested, str) and nested.isdigit():
            return int(nested, 10)
    return None


def _candidate_string_list(item: dict[str, object], key: str) -> list[str]:
    value = item.get(key)
    if isinstance(value, list):
        return [str(part) for part in value if str(part)]
    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get(key)
        if isinstance(nested, list):
            return [str(part) for part in nested if str(part)]
    return []


def _candidate_raw_score(item: dict[str, object]) -> float:
    value = item.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("score")
        if isinstance(nested, (int, float)):
            return float(nested)

    distance = item.get("distance")
    if isinstance(distance, (int, float)):
        return max(0.0, 1.0 - float(distance))
    if isinstance(content, dict):
        nested = content.get("distance")
        if isinstance(nested, (int, float)):
            return max(0.0, 1.0 - float(nested))
    return 0.0


def _candidate_metadata_score(item: dict[str, object], query: str, normalized_query: str) -> tuple[float, bool]:
    symbol_name = _candidate_text(item, "symbol_name")
    qualified_name = _candidate_text(item, "qualified_name")
    signature = _candidate_text(item, "signature")
    docstring = _candidate_text(item, "docstring")
    body = _candidate_text(item, "body")
    preview = _candidate_text(item, "preview")
    heading = _candidate_text(item, "heading")
    symbol_type = _candidate_text(item, "symbol_type")
    record_type = _candidate_text(item, "record_type")
    breadcrumb = _candidate_string_list(item, "breadcrumb")
    line_start = _candidate_int(item, "line_start") or 0
    line_end = _candidate_int(item, "line_end") or 0

    exact_symbol_match = False
    for token in (query, normalized_query):
        if not token:
            continue
        lowered = token.lower()
        if lowered == symbol_name.lower() or lowered == heading.lower():
            exact_symbol_match = True
            break
        if qualified_name.lower().endswith(f".{lowered}") or qualified_name.lower().endswith(f"::{lowered}"):
            exact_symbol_match = True
            break

    score = 0.0
    if record_type == "code":
        score += 1.0
    if symbol_type in {"function", "method", "class"}:
        score += 5.0
    if symbol_name:
        score += 1.0
    if qualified_name:
        score += 1.0
    if signature:
        score += 3.5
        signature_lower = signature.lstrip().lower()
        if signature_lower.startswith(("def ", "async def ", "class ", "function ")):
            score += 2.0
        elif symbol_name and signature_lower.startswith(
            (f"{symbol_name.lower()}(", f"{symbol_name.lower()} ()", f"{symbol_name.lower()}()")
        ):
            score += 1.5
    if docstring:
        score += 4.0
    if body:
        score += 4.0
        if len(body) > 200:
            score += 1.0
    if preview:
        score += 1.0
    if heading:
        score += 0.5
    if breadcrumb:
        score += 0.5
    if line_end > line_start:
        score += 1.0

    if query:
        query_lower = query.lower()
        if query_lower == symbol_name.lower() or query_lower == heading.lower():
            score += 5.0
        elif query_lower in qualified_name.lower():
            score += 4.0
        elif query_lower in signature.lower():
            score += 3.0
        elif query_lower in docstring.lower():
            score += 2.0
        elif query_lower in body.lower() or query_lower in preview.lower():
            score += 1.5

    if normalized_query and normalized_query != query:
        normalized_lower = normalized_query.lower()
        if normalized_lower == symbol_name.lower() or normalized_lower == heading.lower():
            score += 4.0
            exact_symbol_match = True
        elif normalized_lower in qualified_name.lower():
            score += 2.5
            exact_symbol_match = True

    return score, exact_symbol_match


def _vector_anchor_rank(match: _VectorMatch) -> tuple[int, int, int, int, float, float, int, int]:
    return (
        1 if match.exact_symbol_match else 0,
        1 if match.symbol_type in {"function", "method", "class"} else 0,
        1 if match.has_body else 0,
        1 if match.has_docstring else 0,
        match.metadata_score,
        match.raw_score,
        match.line_span,
        -match.line_num,
    )


def _vector_match_for_item(item: dict[str, object], query: str, normalized_query: str) -> _VectorMatch | None:
    line_num = _resolve_candidate_line(item)
    if line_num is None:
        return None

    raw_score = _candidate_raw_score(item)
    metadata_score, exact_symbol_match = _candidate_metadata_score(item, query, normalized_query)
    return _VectorMatch(
        line_num=line_num,
        raw_score=raw_score,
        metadata_score=metadata_score,
        exact_symbol_match=exact_symbol_match,
        symbol_type=_candidate_text(item, "symbol_type"),
        has_body=bool(_candidate_text(item, "body")),
        has_docstring=bool(_candidate_text(item, "docstring")),
        line_span=max(0, (_candidate_int(item, "line_end") or 0) - line_num),
    )


def _vector_query_line_num(file_path: Path, query: str, normalized_query: str, scope: str) -> _VectorMatch | None:
    if not query or not scope:
        return None
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return None

    cmd = [
        "uv",
        "run",
        "--no-sync",
        "python",
        "-m",
        "src.mcp_codebase.indexer",
        "--repo-root",
        str(REPO_ROOT),
        "query",
        query,
        "--scope",
        scope,
        "--top-k",
        "5",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"indexer query failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"indexer query failed with exit code {proc.returncode}")
        return None

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        _set_vector_runtime_note("indexer query returned invalid JSON")
        return None
    if not isinstance(payload, list):
        _set_vector_runtime_note("indexer query returned unexpected payload shape")
        return None

    target = file_path.resolve()
    best_match: _VectorMatch | None = None
    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate = _resolve_candidate_file(item)
        if not candidate:
            continue
        try:
            if Path(candidate).expanduser().resolve() != target:
                continue
        except Exception:
            continue
        match = _vector_match_for_item(item, query, normalized_query)
        if match is None:
            continue

        if best_match is None:
            best_match = match
            continue

        best_tuple = _vector_anchor_rank(best_match)
        candidate_tuple = _vector_anchor_rank(match)
        if candidate_tuple > best_tuple:
            best_match = match

    return best_match


def _vector_find_line_num(
    file_path: Path,
    raw_pattern: str,
    normalized_pattern: str,
    scope: str,
) -> _VectorMatch | None:
    _clear_vector_runtime_note()
    match = None
    if raw_pattern:
        match = _vector_query_line_num(file_path, raw_pattern, normalized_pattern, scope)
    if (
        match is None
        and normalized_pattern
        and normalized_pattern != raw_pattern
    ):
        match = _vector_query_line_num(file_path, normalized_pattern, normalized_pattern, scope)
    return match


def _find_first_literal_line(file_path: Path, literal: str) -> int | None:
    if not literal:
        return None
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if literal in line:
                return idx
    return None


def _find_line_num(file_path: Path, raw_pattern: str, normalized_pattern: str) -> int | None:
    line_num = _find_first_literal_line(file_path, raw_pattern) if raw_pattern else None
    if line_num is None and normalized_pattern and normalized_pattern != raw_pattern:
        line_num = _find_first_literal_line(file_path, normalized_pattern)
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"def {normalized_pattern}")
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"async def {normalized_pattern}")
    if line_num is None and normalized_pattern:
        line_num = _find_first_literal_line(file_path, f"class {normalized_pattern}")
    return line_num


def _collect_literal_hits(file_path: Path, literal: str) -> list[int]:
    if not literal:
        return []
    hits: list[int] = []
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if literal in line:
                hits.append(idx)
    return hits


def _resolve_line_num_strict(file_path: Path, raw_pattern: str, normalized_pattern: str) -> tuple[int, int | None]:
    if normalized_pattern:
        strict_hits: set[int] = set()
        for literal in [
            f"def {normalized_pattern}(",
            f"async def {normalized_pattern}(",
            f"class {normalized_pattern}",
            f"function {normalized_pattern}",
            f"{normalized_pattern}() {{",
            f"{normalized_pattern} () {{",
            f"{normalized_pattern} =",
        ]:
            strict_hits.update(_collect_literal_hits(file_path, literal))
        ordered = sorted(strict_hits)
        if len(ordered) == 1:
            return 0, ordered[0]
        if len(ordered) > 1:
            print(
                f"ERROR: Strict symbol match is ambiguous for '{normalized_pattern}' in {file_path}.",
                file=sys.stderr,
            )
            return 2, None

    raw_hits = sorted(set(_collect_literal_hits(file_path, raw_pattern)))
    if len(raw_hits) == 1:
        return 0, raw_hits[0]
    if len(raw_hits) > 1:
        print(
            f"ERROR: Strict symbol match is ambiguous for '{raw_pattern}' in {file_path}.",
            file=sys.stderr,
        )
        return 2, None

    return 1, None


def is_large_code_file(file_path: Path) -> bool:
    """Return True when file length exceeds mandatory symbol guard threshold."""
    with file_path.open(encoding="utf-8") as handle:
        line_count = sum(1 for _ in handle)
    return line_count > CODE_FILE_LINE_THRESHOLD


def _render_numbered_window(file_path: Path, start: int, end: int) -> None:
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if idx < start:
                continue
            if idx > end:
                break
            print(f"{idx:6}\t{line.rstrip()}")


def read_code_context(argv: list[str]) -> int:
    """Resolve an anchor from symbol/pattern and print bounded numbered context."""
    if len(argv) < 2:
        print(
            "ERROR: read_code_context requires: <file_path> <symbol_or_pattern> [context_lines]",
            file=sys.stderr,
        )
        return 1

    file_arg = argv[0]
    pattern = argv[1]
    extra = argv[2:]

    context = READ_CODE_DEFAULT_CONTEXT_LINES
    context_set = False
    allow_fallback = False

    for token in extra:
        if token == "--hud-symbol":
            continue
        elif token == "--allow-fallback":
            allow_fallback = True
        elif token.isdigit() and not context_set:
            context = int(token, 10)
            context_set = True
        else:
            print(f"ERROR: Unexpected argument for context mode: {token}", file=sys.stderr)
            return 1

    file_path = Path(file_arg)
    if not file_path.is_file():
        print(f"ERROR: File not found: {file_arg}", file=sys.stderr)
        return 1

    if context <= 0:
        print(f"ERROR: context_lines must be a positive integer: {context}", file=sys.stderr)
        return 1
    if context > READ_CODE_MAX_LINES:
        print(f"ERROR: context_lines exceeds max ({READ_CODE_MAX_LINES}): {context}", file=sys.stderr)
        return 1

    if not _refresh_indexes_for_read(file_path):
        return 1
    normalized_pattern = normalize_symbol_pattern(pattern)
    vector_match = _vector_find_line_num(file_path, pattern, normalized_pattern, "code")

    strict_status, strict_line_num = _resolve_line_num_strict(file_path, pattern, normalized_pattern)
    line_num: int | None = None
    if vector_match is not None:
        line_num = vector_match.line_num
    elif strict_status == 0:
        line_num = strict_line_num
    elif allow_fallback:
        line_num = _find_line_num(file_path, pattern, normalized_pattern)

    if line_num is None and strict_status != 0:
        if codegraph_supports_file(file_path):
            discover_pattern = (
                normalized_pattern
                if normalized_pattern and normalized_pattern != pattern
                else pattern
            )
            if not codegraph_discover_or_fail(discover_pattern, file_path.parent):
                return 1
            vector_match = _vector_find_line_num(file_path, pattern, normalized_pattern, "code")
            if vector_match is not None:
                line_num = vector_match.line_num
        else:
            vector_match = _vector_find_line_num(file_path, pattern, normalized_pattern, "code")
            if vector_match is not None:
                line_num = vector_match.line_num

        if line_num is None and strict_status == 0:
            line_num = strict_line_num
        elif line_num is None and allow_fallback:
            line_num = _find_line_num(file_path, pattern, normalized_pattern)

    _emit_vector_fallback_notice(
        file_path=file_path,
        pattern=pattern,
        vector_match=vector_match,
        resolved_line=line_num,
    )

    if line_num is None:
        if strict_status == 2:
            print(
                "ERROR: Symbol resolution ambiguous; re-run with --allow-fallback to allow bounded file-local fallback.",
                file=sys.stderr,
            )
        else:
            print(
                f"ERROR: Strict symbol resolution failed for '{pattern}'. Re-run with --allow-fallback to allow bounded file-local fallback.",
                file=sys.stderr,
            )
        return 1

    if line_num is None:
        print(f"ERROR: Pattern not found after one bounded fallback: {pattern} in {file_arg}", file=sys.stderr)
        return 1

    start = max(1, line_num - context)
    end = line_num + context
    _render_numbered_window(file_path, start, end)
    return 0


def read_code_window(argv: list[str]) -> int:
    """Print a numbered bounded window, optionally anchored by symbol/pattern."""
    if len(argv) < 2:
        print(
            "ERROR: read_code_window requires: <file_path> <start_line> [line_count]",
            file=sys.stderr,
        )
        return 1

    file_arg = argv[0]
    start_line_raw = argv[1]
    extra = argv[2:]

    line_count = READ_CODE_DEFAULT_WINDOW_LINES
    line_count_set = False
    pattern = ""
    hud_flag = False
    allow_fallback = False

    for token in extra:
        if token == "--hud-symbol":
            hud_flag = True
        elif token == "--allow-fallback":
            allow_fallback = True
        elif token.isdigit() and not line_count_set:
            line_count = int(token, 10)
            line_count_set = True
        elif not pattern:
            pattern = token
        else:
            print(f"ERROR: Unexpected argument for window mode: {token}", file=sys.stderr)
            return 1

    file_path = Path(file_arg)
    if not file_path.is_file():
        print(f"ERROR: File not found: {file_arg}", file=sys.stderr)
        return 1

    if not start_line_raw.isdigit() or int(start_line_raw, 10) <= 0:
        print(f"ERROR: start_line must be a positive integer: {start_line_raw}", file=sys.stderr)
        return 1
    start_line = int(start_line_raw, 10)

    if line_count <= 0:
        print(f"ERROR: line_count must be a positive integer: {line_count}", file=sys.stderr)
        return 1
    if line_count > READ_CODE_MAX_LINES:
        print(f"ERROR: line_count exceeds max ({READ_CODE_MAX_LINES}): {line_count}", file=sys.stderr)
        return 1

    use_hud_fast_path = hud_flag
    vector_match = None

    if pattern:
        if not _refresh_indexes_for_read(file_path):
            return 1
        normalized_pattern = normalize_symbol_pattern(pattern)
        vector_match = _vector_find_line_num(file_path, pattern, normalized_pattern, "code")

        strict_status, strict_line_num = _resolve_line_num_strict(file_path, pattern, normalized_pattern)
        line_num: int | None = None
        if vector_match is not None:
            line_num = vector_match.line_num
        elif strict_status == 0:
            line_num = int(strict_line_num or 0)
        elif allow_fallback:
            line_num = _find_line_num(file_path, pattern, normalized_pattern)

        if line_num is None and strict_status != 0:
            if codegraph_supports_file(file_path):
                discover_pattern = (
                    normalized_pattern
                    if normalized_pattern and normalized_pattern != pattern
                    else pattern
                )
                if not codegraph_discover_or_fail(discover_pattern, file_path.parent):
                    return 1
            vector_match = _vector_find_line_num(file_path, pattern, normalized_pattern, "code")
            if vector_match is not None:
                line_num = vector_match.line_num
            elif strict_status == 0:
                line_num = int(strict_line_num or 0)
            elif allow_fallback:
                line_num = _find_line_num(file_path, pattern, normalized_pattern)

        _emit_vector_fallback_notice(
            file_path=file_path,
            pattern=pattern,
            vector_match=vector_match,
            resolved_line=line_num,
        )

        if line_num is None:
            if strict_status == 2:
                print(
                    "ERROR: Symbol resolution ambiguous; re-run with --allow-fallback to allow bounded file-local fallback.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"ERROR: Strict symbol resolution failed for '{pattern}'. Re-run with --allow-fallback to allow bounded file-local fallback.",
                    file=sys.stderr,
                )
            return 1

        start_line = int(line_num)
    elif is_large_code_file(file_path) and not use_hud_fast_path:
        print(
            f"ERROR: symbol_or_pattern is required for files >{CODE_FILE_LINE_THRESHOLD} lines unless using HUD current-line fast-path.",
            file=sys.stderr,
        )
        print(
            "Usage: read_code_window <file> <start_line> [line_count] <symbol_or_pattern>",
            file=sys.stderr,
        )
        return 1

    end_line = start_line + line_count - 1
    _render_numbered_window(file_path, start_line, end_line)
    return 0


def _print_usage() -> None:
    print("Usage:")
    print(
        f"  read_code_context <file_path> <symbol_or_pattern> [context_lines<={READ_CODE_MAX_LINES}] [--hud-symbol] [--allow-fallback]"
    )
    print(
        f"  read_code_window  <file_path> <start_line> [line_count<={READ_CODE_MAX_LINES}] [symbol_or_pattern] [--hud-symbol] [--allow-fallback]"
    )
    print(
        "                   (for large files, HUD current-line fast-path may omit symbol when --hud-symbol is set)"
    )


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read-code.sh mode routing."""
    if len(argv) < 3:
        _print_usage()
        return 1

    mode = argv[0]
    args = argv[1:]
    if mode == "context":
        return read_code_context(args)
    if mode == "window":
        return read_code_window(args)

    print(f"ERROR: Unknown mode '{mode}'. Use: context | window", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
