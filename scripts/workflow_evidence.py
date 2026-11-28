#!/usr/bin/env python3
"""Shared stdlib-only workflow evidence, freshness state, and repo-local tool environment."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES: tuple[str, ...] = (
    "pyproject.toml",
    "ruff.toml",
    ".ruff.toml",
    "pyrightconfig.json",
    "pytest.ini",
)
LOCK_FILE = "uv.lock"
VALID_FRESHNESS_STATUSES: frozenset[str] = frozenset({"current", "stale", "unverifiable"})
KNOWN_SCOPES: tuple[str, ...] = ("scripts", "src", "tests", "specs")
CODEGRAPH_SCOPES: frozenset[str] = frozenset({"scripts", "src", "tests"})
IGNORE_DIRS_DEFAULT = (
    "node_modules,venv,.venv,env,.env,dist,build,target,out,.git,.idea,.vscode,"
    "__pycache__,.uv-cache,logs,shadow-runs"
)


@dataclass(frozen=True)
class EvidenceRecord:
    """Persisted validation or commit evidence record bound to a SHA-256 digest."""

    validator_id: str
    digest: str
    paths: tuple[str, ...]
    selectors: tuple[str, ...]
    python_minor: str
    recorded_at_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScopeFreshness:
    """Freshness status for one discovery backend and scope."""

    status: str
    edit_signature: str = ""
    last_error: str = ""
    updated_at_utc: str = ""


@dataclass
class FreshnessState:
    """Per-backend, per-scope discovery freshness map."""

    backends: dict[str, dict[str, ScopeFreshness]] = field(default_factory=dict)

    def get_entry(self, backend: str, scope: str) -> ScopeFreshness:
        """Return the freshness record for a backend and scope, defaulting to current."""
        return self.backends.get(backend, {}).get(scope, ScopeFreshness(status="current"))

    def get_status(self, backend: str, scope: str) -> str:
        """Return the status string for a backend and scope."""
        return self.get_entry(backend, scope).status

    def stale_scopes(self, backend: str) -> list[str]:
        """Return sorted scopes currently marked stale or unverifiable for a backend."""
        entries = self.backends.get(backend, {})
        return sorted(scope for scope, item in entries.items() if item.status != "current")


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _python_minor_version(override: str | None = None) -> str:
    """Return the Python major.minor version string."""
    if override:
        return str(override)
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def workflow_state_dir(repo_root: Path | None = None) -> Path:
    """Return the repo-local directory holding workflow evidence and freshness JSON."""
    root = (repo_root or REPO_ROOT).resolve()
    return root / ".codegraphcontext" / "workflow-state"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Persist JSON atomically via a sibling temporary file and os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk, failing closed to an empty dict on error."""
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_repo_paths(repo_root: Path, raw_paths: Sequence[str | Path]) -> list[str]:
    """Normalize, deduplicate, and sort paths that lie inside repo_root."""
    root = repo_root.resolve()
    normalized: set[str] = set()
    for raw in raw_paths:
        text = str(raw).strip()
        if not text:
            continue
        candidate = Path(text)
        resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            rel = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel and rel != ".":
            normalized.add(rel)
    return sorted(normalized)


def _hash_file_bytes(path: Path) -> str:
    """Return a SHA-256 hex digest for a file or a deterministic sentinel if absent."""
    if path.is_symlink():
        try:
            target = os.readlink(path).encode("utf-8", errors="surrogateescape")
            return f"SYMLINK:{hashlib.sha256(target).hexdigest()}"
        except OSError:
            return "UNREADABLE"
    if not path.exists():
        return "DELETED"
    if path.is_dir():
        return "DIRECTORY"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "UNREADABLE"


def record_changed_paths(repo_root: Path, raw_paths: Sequence[str | Path]) -> list[str]:
    """Merge and persist repo-local changed paths atomically, returning the full sorted list."""
    existing = load_changed_paths(repo_root)
    merged = normalize_repo_paths(repo_root, [*existing, *raw_paths])
    _atomic_write_json(
        workflow_state_dir(repo_root) / "changed_paths.json",
        {"paths": merged, "updated_at_utc": _utc_now_iso()},
    )
    return merged


def load_changed_paths(repo_root: Path) -> list[str]:
    """Return the persisted sorted list of repo-local changed paths."""
    payload = _read_json_dict(workflow_state_dir(repo_root) / "changed_paths.json")
    raw = payload.get("paths")
    if not isinstance(raw, list):
        return []
    return normalize_repo_paths(repo_root, [str(item) for item in raw])


def clear_changed_paths(repo_root: Path) -> None:
    """Clear the persisted changed-path set after a successful closeout."""
    _atomic_write_json(
        workflow_state_dir(repo_root) / "changed_paths.json",
        {"paths": [], "updated_at_utc": _utc_now_iso()},
    )


def compute_evidence_digest(
    repo_root: Path,
    *,
    validator_id: str,
    paths: Sequence[str | Path],
    selectors: Sequence[str] = (),
    python_minor: str | None = None,
) -> str:
    """Compute a deterministic SHA-256 digest binding content, config, lockfile, and selectors."""
    root = repo_root.resolve()
    norm_paths = normalize_repo_paths(root, paths)
    content_hashes = {rel: _hash_file_bytes(root / rel) for rel in norm_paths}
    config_hashes = {name: _hash_file_bytes(root / name) for name in CONFIG_FILES if (root / name).exists()}
    lock_hash = _hash_file_bytes(root / LOCK_FILE) if (root / LOCK_FILE).exists() else "MISSING"
    payload = {
        "validator_id": validator_id,
        "python_minor": _python_minor_version(python_minor),
        "selectors": sorted(dict.fromkeys(str(sel) for sel in selectors if str(sel).strip())),
        "content_hashes": content_hashes,
        "config_hashes": config_hashes,
        "dependency_hash": lock_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evidence_key(validator_id: str, selectors: Sequence[str]) -> str:
    """Build a stable dictionary key for storing evidence per validator and selector set."""
    norm_selectors = sorted(dict.fromkeys(str(sel) for sel in selectors if str(sel).strip()))
    selector_hash = hashlib.sha256(json.dumps(norm_selectors).encode("utf-8")).hexdigest()[:16]
    return f"{validator_id}:{selector_hash}"


def record_validation_evidence(
    repo_root: Path,
    *,
    validator_id: str,
    paths: Sequence[str | Path],
    selectors: Sequence[str] = (),
    python_minor: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceRecord:
    """Compute and atomically persist a validation or commit evidence record."""
    norm_paths = tuple(normalize_repo_paths(repo_root, paths))
    norm_selectors = tuple(sorted(dict.fromkeys(str(sel) for sel in selectors if str(sel).strip())))
    py_minor = _python_minor_version(python_minor)
    digest = compute_evidence_digest(
        repo_root,
        validator_id=validator_id,
        paths=norm_paths,
        selectors=norm_selectors,
        python_minor=py_minor,
    )
    record = EvidenceRecord(
        validator_id=validator_id,
        digest=digest,
        paths=norm_paths,
        selectors=norm_selectors,
        python_minor=py_minor,
        recorded_at_utc=_utc_now_iso(),
        metadata=dict(metadata or {}),
    )
    evidence_path = workflow_state_dir(repo_root) / "evidence.json"
    store = _read_json_dict(evidence_path)
    records = store.get("records")
    if not isinstance(records, dict):
        records = {}
    records[_evidence_key(validator_id, norm_selectors)] = asdict(record)
    _atomic_write_json(evidence_path, {"records": records, "updated_at_utc": _utc_now_iso()})
    return record


def has_valid_evidence(
    repo_root: Path,
    *,
    validator_id: str,
    paths: Sequence[str | Path],
    selectors: Sequence[str] = (),
    python_minor: str | None = None,
) -> bool:
    """Return True only if persisted evidence exists and matches the current digest."""
    store = _read_json_dict(workflow_state_dir(repo_root) / "evidence.json")
    records = store.get("records")
    if not isinstance(records, dict):
        return False
    entry = records.get(_evidence_key(validator_id, selectors))
    if not isinstance(entry, dict):
        return False
    expected = compute_evidence_digest(
        repo_root,
        validator_id=validator_id,
        paths=paths,
        selectors=selectors,
        python_minor=python_minor,
    )
    return entry.get("digest") == expected and entry.get("validator_id") == validator_id


def infer_scopes_for_paths(repo_root: Path, raw_paths: Sequence[str | Path]) -> dict[str, list[str]]:
    """Map repo-local paths to affected discovery backends and scope names."""
    norm_paths = normalize_repo_paths(repo_root, raw_paths)
    codegraph_scopes: set[str] = set()
    vector_scopes: set[str] = set()
    for rel in norm_paths:
        top = rel.split("/", 1)[0]
        scope = top if top in KNOWN_SCOPES else "repo"
        vector_scopes.add(scope)
        if scope in CODEGRAPH_SCOPES or rel.endswith((".py", ".pyi")):
            codegraph_scopes.add(scope)
    result: dict[str, list[str]] = {}
    if codegraph_scopes:
        result["codegraph"] = sorted(codegraph_scopes)
    if vector_scopes:
        result["vector"] = sorted(vector_scopes)
    return result


def load_freshness_state(repo_root: Path) -> FreshnessState:
    """Load persisted per-backend, per-scope freshness state (failing closed on corrupt JSON)."""
    raw = _read_json_dict(workflow_state_dir(repo_root) / "freshness.json")
    raw_backends = raw.get("backends")
    if not isinstance(raw_backends, dict):
        return FreshnessState()
    backends: dict[str, dict[str, ScopeFreshness]] = {}
    for backend, scopes in raw_backends.items():
        if not isinstance(scopes, dict):
            continue
        parsed_scopes: dict[str, ScopeFreshness] = {}
        for scope, info in scopes.items():
            if not isinstance(info, dict):
                continue
            status = str(info.get("status", "unverifiable"))
            if status not in VALID_FRESHNESS_STATUSES:
                status = "unverifiable"
            parsed_scopes[str(scope)] = ScopeFreshness(
                status=status,
                edit_signature=str(info.get("edit_signature", "")),
                last_error=str(info.get("last_error", "")),
                updated_at_utc=str(info.get("updated_at_utc", "")),
            )
        backends[str(backend)] = parsed_scopes
    return FreshnessState(backends=backends)


def _save_freshness_state(repo_root: Path, state: FreshnessState) -> None:
    """Persist freshness state atomically to freshness.json."""
    serialized = {
        backend: {scope: asdict(entry) for scope, entry in scopes.items()}
        for backend, scopes in state.backends.items()
    }
    _atomic_write_json(
        workflow_state_dir(repo_root) / "freshness.json",
        {"backends": serialized, "updated_at_utc": _utc_now_iso()},
    )


def mark_paths_stale(repo_root: Path, raw_paths: Sequence[str | Path]) -> FreshnessState:
    """Mark all discovery backends and scopes affected by raw_paths as stale."""
    affected = infer_scopes_for_paths(repo_root, raw_paths)
    state = load_freshness_state(repo_root)
    now = _utc_now_iso()
    for backend, scopes in affected.items():
        backend_map = state.backends.setdefault(backend, {})
        for scope in scopes:
            prev = backend_map.get(scope)
            backend_map[scope] = ScopeFreshness(
                status="stale",
                edit_signature=prev.edit_signature if prev else "",
                last_error="",
                updated_at_utc=now,
            )
    _save_freshness_state(repo_root, state)
    return state


def mark_scope_current(
    repo_root: Path,
    *,
    backend: str,
    scope: str,
    edit_signature: str = "",
) -> FreshnessState:
    """Mark a discovery backend and scope as current after a verified refresh."""
    state = load_freshness_state(repo_root)
    state.backends.setdefault(backend, {})[scope] = ScopeFreshness(
        status="current",
        edit_signature=edit_signature,
        last_error="",
        updated_at_utc=_utc_now_iso(),
    )
    _save_freshness_state(repo_root, state)
    return state


def mark_scope_unverifiable(
    repo_root: Path,
    *,
    backend: str,
    scope: str,
    error: str,
) -> FreshnessState:
    """Mark a discovery backend and scope as unverifiable with captured error detail."""
    state = load_freshness_state(repo_root)
    state.backends.setdefault(backend, {})[scope] = ScopeFreshness(
        status="unverifiable",
        edit_signature="",
        last_error=error.strip(),
        updated_at_utc=_utc_now_iso(),
    )
    _save_freshness_state(repo_root, state)
    return state


def stale_scopes_for_backend(repo_root: Path, backend: str) -> list[str]:
    """Return sorted scopes that are stale or unverifiable for the given backend."""
    return load_freshness_state(repo_root).stale_scopes(backend)


def repo_local_tool_env(
    repo_root: Path | None = None,
    *,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a subprocess env isolating HOME, XDG_*, UV, Semble, and CGC inside the repo."""
    root = (repo_root or REPO_ROOT).resolve()
    cgc_dir = root / ".codegraphcontext"
    db_dir = cgc_dir / "db"
    home_dir = cgc_dir / "home"
    xdg_config = cgc_dir / "xdg" / "config"
    xdg_cache = cgc_dir / "xdg" / "cache"
    xdg_data = cgc_dir / "xdg" / "data"
    uv_cache = cgc_dir / ".uv-cache"
    semble_cache = cgc_dir / "semble-cache"

    for directory in (cgc_dir, db_dir, home_dir, xdg_config, xdg_cache, xdg_data, uv_cache, semble_cache):
        directory.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ if base_env is None else base_env)
    env["HOME"] = str(home_dir)
    env["XDG_CONFIG_HOME"] = str(xdg_config)
    env["XDG_CACHE_HOME"] = str(xdg_cache)
    env["XDG_DATA_HOME"] = str(xdg_data)
    env["CODEGRAPH_CONTEXT_DIR"] = str(cgc_dir)
    env["CODEGRAPH_DB_DIR"] = str(db_dir)
    env["DEFAULT_DATABASE"] = env.get("DEFAULT_DATABASE", "kuzudb")
    env["KUZUDB_PATH"] = str(db_dir / "kuzudb")
    env["FALKORDB_PATH"] = str(db_dir / "falkordb")
    env["FALKORDB_SOCKET_PATH"] = str(db_dir / "falkordb.sock")
    env["IGNORE_DIRS"] = env.get("IGNORE_DIRS", IGNORE_DIRS_DEFAULT)
    env["UV_CACHE_DIR"] = str(uv_cache)
    env["SEMBLE_CACHE_LOCATION"] = str(semble_cache)
    return env
