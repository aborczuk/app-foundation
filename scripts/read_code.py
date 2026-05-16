#!/usr/bin/env python3
"""Python entrypoint for code discovery with semantic-first anchoring.

Code file read-efficiency contract:
- Use this helper for code files (Python, shell, YAML, and related).
- Prefer the helper over raw file reads so the read stays bounded by semantic intent.
- Use semantic search first to locate the right anchor, then step candidates as needed.
- Active discovery modes are context, find, and analyze.
- If you need only the relevant function body, pass the function name rather than scanning the whole file.
- If semantic confidence is weak, step through candidates before broadening the query.
- Scoped reads that include a file path stay on the scoped trust fast path.
- Broad reads keep mixed code-plus-markdown discovery and escalate only on explicit bad outcomes.
- Markdown targets remain markdown-aware in either mode.

How to use:
1. Invoke the Python entrypoint directly: ``uv run python scripts/read_code.py <mode> [args]``.
2. Use **context mode** when the target is a natural-language query or symbol name:
   - ``uv run python scripts/read_code.py context "<query>"`` — semantic search + bounded window.
   - ``uv run python scripts/read_code.py context "<symbol>" --path <file>`` — scope to a specific file and use scoped trust routing.
   - ``uv run python scripts/read_code.py context "<symbol>" --inline-body`` — get full function body.
   - ``uv run python scripts/read_code.py context "<symbol>" --next-candidate`` — step ranked candidates.
3. Use **find/analyze stepping** when the first semantic candidate is not the right seam:
   - ``uv run python scripts/read_code.py find <command> <query> --next-candidate`` — structural shortlist stepping.
   - ``uv run python scripts/read_code.py analyze <command> <query> --next-candidate`` — graph shortlist stepping.
   - add ``--verbose`` to keep full backend diagnostics instead of the terse shortlist output.
4. Use broad context queries without ``--path`` when you want mixed code-plus-markdown discovery; the helper will escalate only if the broad result is empty, weak, stale, or conflicting.
5. Let the helper anchor the seam semantically and print only the selected match.

Validation:
- If the symbol does not resolve, the helper prints a clear not-found error and shows ranked candidates.
- The helper keeps semantic output bounded and candidate-driven.
- Confidence scores guide candidate selection when multiple matches exist.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:  # pragma: no cover - exercised in runtime verification
    import torch  # type: ignore[import-not-found]
    from transformers import (  # type: ignore[import-not-found]
        AutoModelForSequenceClassification,
        AutoTokenizer,
    )
except ImportError:  # pragma: no cover - handled via local-cache guards
    torch = None
    AutoModelForSequenceClassification = None
    AutoTokenizer = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

from read_code_health import (
    REPO_ROOT,
    _append_jsonl_object,
    _clear_vector_runtime_note,
    _command_exists,
    _consume_vector_runtime_note,
    _find_markdown_section_end,
    _load_json_object,
    _markdown_heading_lines,
    _persist_json_object,
    _read_code_search_metadata_log_path,
    _read_code_search_scratchpad_path,
    _read_code_session_id,
    _refresh_indexes_for_read,
    _resolve_markdown_anchor_fallback,
    _resolve_markdown_anchor_vector,
    _run_command_capture,
    _set_vector_runtime_note,
    _vector_command_env,
    _vector_indexer_cmd,
    codegraph_current_edit_signature,
    codegraph_refresh_by_state,
    codegraph_supports_file,
    evaluate_read_vector_trust,
    init_codegraph_env,
)

# Backwards-compatible alias for older callers and tests.
codegraph_refresh_if_needed = codegraph_refresh_by_state

SOURCE_PATH = Path(__file__).resolve()
SCRIPT_DIR = SOURCE_PATH.parent


def _is_markdown(path: Path | None) -> bool:
    """Return whether the target file is a markdown file."""
    if path is None:
        return False
    return path.suffix.lower() == ".md"

READ_CODE_DEFAULT_CONTEXT_LINES = 60
READ_CODE_DEFAULT_WINDOW_LINES = 60
READ_CODE_MAX_LINES = int(os.environ.get("SPECKIT_READ_CODE_MAX_LINES", "80") or "80")
READ_CODE_CONTEXT_PRE_FRACTION = 0.1
READ_CODE_CONTEXT_PRE_CAP = 25
READ_CODE_RERANK_CANDIDATE_LIMIT = int(
    os.environ.get("SPECKIT_READ_CODE_RERANK_CANDIDATE_LIMIT", "20") or "20"
)
READ_CODE_FINAL_SHORTLIST_LIMIT = int(
    os.environ.get("SPECKIT_READ_CODE_FINAL_SHORTLIST_LIMIT", "5") or "5"
)
READ_CODE_RERANK_BATCH_SIZE = int(
    os.environ.get("SPECKIT_READ_CODE_RERANK_BATCH_SIZE", "16") or "16"
)
READ_CODE_SEARCH_SCRATCHPAD_TTL_SECONDS = float(
    os.environ.get("SPECKIT_READ_CODE_SEARCH_SCRATCHPAD_TTL_SECONDS", "300") or "300"
)
READ_CODE_SEARCH_SCRATCHPAD_MAX_ENTRIES = int(
    os.environ.get("SPECKIT_READ_CODE_SEARCH_SCRATCHPAD_MAX_ENTRIES", "100") or "100"
)
READ_CODE_HISTORY_DEFAULT_LIMIT = 20
READ_CODE_HISTORY_MAX_LIMIT = 50
READ_CODE_HISTORY_MAX_STATS_ROWS = 12
_READ_CODE_RERANKER_BACKEND = None


@dataclass(frozen=True)
class _VectorMatch:
    """Candidate vector hit with cosine similarity-based ranking."""

    unit_id: str
    symbol_name: str
    qualified_name: str
    line_num: int
    line_end: int
    raw_score: float
    cosine_similarity: int = 0
    symbol_type: str = ""
    has_body: bool = False
    has_docstring: bool = False
    body: str = ""
    preview: str = ""
    signature: str = ""
    file_path: Path = Path()
    docstring: str = ""


@dataclass(frozen=True)
class _RerankDebugInfo:
    """Bounded rerank diagnostics for one semantic shortlist."""

    status: str
    model_name: str | None
    candidate_count: int
    changed: bool
    before_symbols: tuple[str, ...]
    after_symbols: tuple[str, ...]


@dataclass(frozen=True)
class _AnchorResolution:
    """Shared anchor resolution result for context and window read entrypoints."""

    vector_candidates: list[_VectorMatch]
    vector_match: _VectorMatch | None
    strict_status: int
    line_num: int | None
    rerank_debug: _RerankDebugInfo | None = None


class _ReadCodeRerankerBackend:
    """Load a cached local HF reranker for query-time shortlist rescoring."""

    def __init__(self, model_name: str, *, cache_dir: Path) -> None:
        if AutoTokenizer is None or AutoModelForSequenceClassification is None or torch is None:
            raise RuntimeError(
                "transformers and torch are required for semantic shortlist reranking; run `uv sync` after adding the dependency."
            )
        self._model_name = model_name
        cache_dir.mkdir(parents=True, exist_ok=True)
        with _hf_hub_offline_mode():
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                cache_dir=str(cache_dir),
                local_files_only=True,
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_name,
                cache_dir=str(cache_dir),
                local_files_only=True,
            )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        if self._device != "cpu":
            self._model = self._model.half()
        self._model.to(self._device)
        self._model.eval()

    @property
    def model_name(self) -> str:
        """Return the resolved reranker model name."""
        return self._model_name

    def score_pairs(self, query: str, passages: list[str]) -> list[float]:
        """Return normalized reranker scores for one query over candidate passages."""
        if not passages:
            return []
        assert torch is not None  # Narrowed by __init__ guard.
        scores: list[float] = []
        for start in range(0, len(passages), READ_CODE_RERANK_BATCH_SIZE):
            batch = passages[start : start + READ_CODE_RERANK_BATCH_SIZE]
            encoded = self._tokenizer(
                [query] * len(batch),
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {key: value.to(self._device) for key, value in encoded.items()}
            with torch.no_grad():
                logits = self._model(**encoded, return_dict=True).logits.view(-1).float().cpu()
            scores.extend(float(value) for value in torch.sigmoid(logits).tolist())
        return scores


@dataclass(frozen=True)
class _ContextArgs:
    """Parsed and validated arguments for read_code_context."""

    file_path: Path | None
    pattern: str
    context: int
    allow_fallback: bool
    show_shortlist: bool
    inline_body: bool
    candidate_index: int
    content_type: str | None
    show_rerank: bool = False


@dataclass(frozen=True)
class _ContextQueryScope:
    """Stable request-scope classification for read_code_context."""

    is_scoped: bool
    reason: str


@dataclass(frozen=True)
class _WindowArgs:
    """Parsed and validated arguments for read_code_window."""

    file_path: Path
    start_line: int
    end_line: int
    pattern: str
    use_hud_fast_path: bool
    allow_fallback: bool


@dataclass(frozen=True)
class _FindArgs:
    """Parsed and validated arguments for read_code_find."""

    command: str
    forwarded_args: list[str]
    candidate_index: int
    show_shortlist: bool


@dataclass(frozen=True)
class _FindMatch:
    """Compact representation of a parsed cgc find row."""

    name: str
    symbol_type: str
    location: str
    path: Path | None
    line_num: int | None


@dataclass(frozen=True)
class _AnalyzeArgs:
    """Parsed and validated arguments for read_code_analyze."""

    command: str
    forwarded_args: list[str]
    candidate_index: int
    show_shortlist: bool


@dataclass(frozen=True)
class _AnalyzeMatch:
    """Compact representation of a parsed cgc analyze row."""

    columns: dict[str, str]
    location: str
    path: Path | None
    line_num: int | None


@dataclass(frozen=True)
class _HistoryArgs:
    """Parsed and validated arguments for read_code_history."""

    command: str
    limit: int = READ_CODE_HISTORY_DEFAULT_LIMIT


@contextmanager
def _hf_hub_offline_mode():
    """Force local-only Hugging Face model loads for the duration of one operation."""
    previous = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = previous


def _read_code_reranker_model_name() -> str:
    """Return the configured query-time reranker model name."""
    from src.mcp_codebase.index.config import DEFAULT_RERANKER_MODEL_NAME

    return os.environ.get("SPECKIT_READ_CODE_RERANKER_MODEL", DEFAULT_RERANKER_MODEL_NAME)


def _read_code_reranker_cache_dir() -> Path:
    """Return the repo-local cache directory used for query-time reranker loads."""
    from src.mcp_codebase.index.config import DEFAULT_RERANKER_CACHE_DIR

    return (REPO_ROOT / DEFAULT_RERANKER_CACHE_DIR).resolve()


def _read_code_reranker_cache_present(model_name: str) -> bool:
    """Return whether the configured reranker model is already cached locally."""
    from src.mcp_codebase.index.config import reranker_model_cache_path

    return reranker_model_cache_path(_read_code_reranker_cache_dir(), model_name).exists()


def _load_read_code_reranker() -> _ReadCodeRerankerBackend | None:
    """Return a cached query-time reranker backend when the local model is available."""
    global _READ_CODE_RERANKER_BACKEND
    if _READ_CODE_RERANKER_BACKEND is not None:
        return _READ_CODE_RERANKER_BACKEND
    if AutoTokenizer is None or AutoModelForSequenceClassification is None or torch is None:
        return None
    model_name = _read_code_reranker_model_name()
    if not _read_code_reranker_cache_present(model_name):
        return None
    try:
        _READ_CODE_RERANKER_BACKEND = _ReadCodeRerankerBackend(
            model_name,
            cache_dir=_read_code_reranker_cache_dir(),
        )
    except Exception:
        return None
    return _READ_CODE_RERANKER_BACKEND







def _split_verbose_flag(argv: list[str]) -> tuple[list[str], bool]:
    """Remove the read helper verbose flag while preserving the remaining argv."""
    verbose = False
    filtered: list[str] = []
    for token in argv:
        if token in {"--verbose", "-v"}:
            verbose = True
            continue
        filtered.append(token)
    return filtered, verbose


def _cgc_capture_env() -> dict[str, str]:
    """Return a stable environment for captured cgc output without narrow-table truncation."""
    env = os.environ.copy()
    env.setdefault("COLUMNS", "240")
    env.setdefault("NO_COLOR", "1")
    return env


def _serialize_path(path: Path | None) -> str | None:
    """Convert an optional path to a stable string payload for JSON storage."""
    if path is None:
        return None
    return str(path)


def _deserialize_path(value: object) -> Path | None:
    """Convert a JSON payload path back into a Path when possible."""
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _serialize_vector_match(match: _VectorMatch) -> dict[str, object]:
    """Convert a vector match into a JSON-friendly scratchpad payload."""
    return {
        "unit_id": match.unit_id,
        "symbol_name": match.symbol_name,
        "qualified_name": match.qualified_name,
        "line_num": match.line_num,
        "line_end": match.line_end,
        "raw_score": match.raw_score,
        "cosine_similarity": match.cosine_similarity,
        "symbol_type": match.symbol_type,
        "has_body": match.has_body,
        "has_docstring": match.has_docstring,
        "body": match.body,
        "preview": match.preview,
        "signature": match.signature,
        "file_path": _serialize_path(match.file_path),
        "docstring": match.docstring,
    }


def _deserialize_vector_match(payload: object) -> _VectorMatch | None:
    """Convert a scratchpad payload back into a vector match when valid."""
    if not isinstance(payload, dict):
        return None
    unit_id = payload.get("unit_id")
    symbol_name = payload.get("symbol_name")
    qualified_name = payload.get("qualified_name")
    line_num = payload.get("line_num")
    line_end = payload.get("line_end")
    raw_score = payload.get("raw_score")
    if not isinstance(unit_id, str) or not isinstance(symbol_name, str) or not isinstance(qualified_name, str):
        return None
    if not isinstance(line_num, int) or not isinstance(line_end, int):
        return None
    if not isinstance(raw_score, (int, float)):
        return None
    cosine_similarity = payload.get("cosine_similarity", 0)
    if not isinstance(cosine_similarity, int):
        return None
    symbol_type = payload.get("symbol_type", "")
    has_body = payload.get("has_body", False)
    has_docstring = payload.get("has_docstring", False)
    body = payload.get("body", "")
    preview = payload.get("preview", "")
    signature = payload.get("signature", "")
    docstring = payload.get("docstring", "")
    if not isinstance(symbol_type, str) or not isinstance(body, str) or not isinstance(preview, str):
        return None
    if not isinstance(signature, str) or not isinstance(docstring, str):
        return None
    if not isinstance(has_body, bool) or not isinstance(has_docstring, bool):
        return None
    return _VectorMatch(
        unit_id=unit_id,
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        line_num=line_num,
        line_end=line_end,
        raw_score=float(raw_score),
        cosine_similarity=cosine_similarity,
        symbol_type=symbol_type,
        has_body=has_body,
        has_docstring=has_docstring,
        body=body,
        preview=preview,
        signature=signature,
        file_path=_deserialize_path(payload.get("file_path")) or Path(),
        docstring=docstring,
    )


def _serialize_rerank_debug(debug: _RerankDebugInfo) -> dict[str, object]:
    """Convert rerank diagnostics into a JSON-friendly scratchpad payload."""
    return {
        "status": debug.status,
        "model_name": debug.model_name,
        "candidate_count": debug.candidate_count,
        "changed": debug.changed,
        "before_symbols": list(debug.before_symbols),
        "after_symbols": list(debug.after_symbols),
    }


def _deserialize_rerank_debug(payload: object) -> _RerankDebugInfo | None:
    """Convert a scratchpad payload back into bounded rerank diagnostics."""
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    model_name = payload.get("model_name")
    candidate_count = payload.get("candidate_count")
    changed = payload.get("changed")
    before_symbols = payload.get("before_symbols")
    after_symbols = payload.get("after_symbols")
    if not isinstance(status, str):
        return None
    if model_name is not None and not isinstance(model_name, str):
        return None
    if not isinstance(candidate_count, int) or not isinstance(changed, bool):
        return None
    if not isinstance(before_symbols, list) or not isinstance(after_symbols, list):
        return None
    if not all(isinstance(item, str) for item in before_symbols + after_symbols):
        return None
    return _RerankDebugInfo(
        status=status,
        model_name=model_name,
        candidate_count=candidate_count,
        changed=changed,
        before_symbols=tuple(before_symbols),
        after_symbols=tuple(after_symbols),
    )


def _serialize_find_match(match: _FindMatch) -> dict[str, object]:
    """Convert a parsed find result into a JSON-friendly scratchpad payload."""
    return {
        "name": match.name,
        "symbol_type": match.symbol_type,
        "location": match.location,
        "path": _serialize_path(match.path),
        "line_num": match.line_num,
    }


def _deserialize_find_match(payload: object) -> _FindMatch | None:
    """Convert a scratchpad payload back into a parsed find result when valid."""
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    symbol_type = payload.get("symbol_type")
    location = payload.get("location")
    line_num = payload.get("line_num")
    if not isinstance(name, str) or not isinstance(symbol_type, str) or not isinstance(location, str):
        return None
    if line_num is not None and not isinstance(line_num, int):
        return None
    return _FindMatch(
        name=name,
        symbol_type=symbol_type,
        location=location,
        path=_deserialize_path(payload.get("path")),
        line_num=line_num,
    )


def _serialize_analyze_match(match: _AnalyzeMatch) -> dict[str, object]:
    """Convert a parsed analyze result into a JSON-friendly scratchpad payload."""
    return {
        "columns": dict(match.columns),
        "location": match.location,
        "path": _serialize_path(match.path),
        "line_num": match.line_num,
    }


def _deserialize_analyze_match(payload: object) -> _AnalyzeMatch | None:
    """Convert a scratchpad payload back into a parsed analyze result when valid."""
    if not isinstance(payload, dict):
        return None
    columns_raw = payload.get("columns")
    location = payload.get("location")
    line_num = payload.get("line_num")
    if not isinstance(columns_raw, dict) or not isinstance(location, str):
        return None
    columns: dict[str, str] = {}
    for key, value in columns_raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return None
        columns[key] = value
    if line_num is not None and not isinstance(line_num, int):
        return None
    return _AnalyzeMatch(
        columns=columns,
        location=location,
        path=_deserialize_path(payload.get("path")),
        line_num=line_num,
    )


def _search_cache_key(command: str, query_payload: dict[str, object]) -> str:
    """Return a stable cache key for one exact read_code search request."""
    encoded = json.dumps(
        {"command": command, "query": query_payload},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


def _scratchpad_entry_cached_at(entry: dict[str, object]) -> float:
    """Return the cache timestamp for one scratchpad entry."""
    cached_at = entry.get("cached_at")
    return float(cached_at) if isinstance(cached_at, (int, float)) else 0.0


def _load_search_scratchpad_entries(session_id: str) -> dict[str, dict[str, object]]:
    """Load string-keyed scratchpad entries for the active read_code session."""
    payload = _load_json_object(_read_code_search_scratchpad_path(session_id))
    if payload is None:
        return {}
    entries_raw = payload.get("entries")
    if not isinstance(entries_raw, dict):
        return {}
    entries: dict[str, dict[str, object]] = {}
    for key, value in entries_raw.items():
        if isinstance(key, str) and isinstance(value, dict):
            entries[key] = value
    return entries


def _persist_search_scratchpad_entries(session_id: str, entries: dict[str, dict[str, object]]) -> None:
    """Persist bounded scratchpad entries for the active read_code session."""
    ordered = sorted(entries.items(), key=lambda item: _scratchpad_entry_cached_at(item[1]), reverse=True)
    if READ_CODE_SEARCH_SCRATCHPAD_MAX_ENTRIES > 0:
        ordered = ordered[:READ_CODE_SEARCH_SCRATCHPAD_MAX_ENTRIES]
    _persist_json_object(
        _read_code_search_scratchpad_path(session_id),
        {"entries": {key: value for key, value in ordered}},
        sort_keys=True,
    )


def _load_cached_search_entry(
    session_id: str,
    cache_key: str,
    *,
    signature: str,
) -> dict[str, object] | None:
    """Return a fresh scratchpad entry when the exact request is still reusable."""
    entry = _load_search_scratchpad_entries(session_id).get(cache_key)
    if entry is None:
        return None
    if entry.get("signature") != signature:
        return None
    ttl = READ_CODE_SEARCH_SCRATCHPAD_TTL_SECONDS
    cached_at = _scratchpad_entry_cached_at(entry)
    if ttl > 0 and cached_at > 0 and time.time() - cached_at > ttl:
        return None
    return entry


def _store_search_scratchpad_entry(
    session_id: str,
    cache_key: str,
    *,
    command: str,
    query_payload: dict[str, object],
    signature: str,
    matches_payload: list[dict[str, object]],
    rerank_debug_payload: dict[str, object] | None = None,
) -> None:
    """Persist one reusable search result set into the session scratchpad."""
    entries = _load_search_scratchpad_entries(session_id)
    entries[cache_key] = {
        "command": command,
        "query": dict(query_payload),
        "signature": signature,
        "cached_at": time.time(),
        "match_count": len(matches_payload),
        "matches": matches_payload,
    }
    if rerank_debug_payload is not None:
        entries[cache_key]["rerank_debug"] = rerank_debug_payload
    _persist_search_scratchpad_entries(session_id, entries)


def _context_query_payload(
    parsed: _ContextArgs,
    request_scope: _ContextQueryScope,
    normalized_pattern: str,
) -> dict[str, object]:
    """Build the exact reusable scratchpad identity for a context request."""
    return {
        "pattern": parsed.pattern,
        "normalized_pattern": normalized_pattern,
        "file_path": str(parsed.file_path.resolve()) if parsed.file_path is not None else None,
        "content_type": parsed.content_type,
        "allow_fallback": parsed.allow_fallback,
        "query_shape": "scoped" if request_scope.is_scoped else "broad",
    }


def _find_query_payload(parsed: _FindArgs) -> dict[str, object]:
    """Build the exact reusable scratchpad identity for a find request."""
    return {
        "subcommand": parsed.command,
        "forwarded_args": list(parsed.forwarded_args),
    }


def _analyze_query_payload(parsed: _AnalyzeArgs) -> dict[str, object]:
    """Build the exact reusable scratchpad identity for an analyze request."""
    return {
        "subcommand": parsed.command,
        "forwarded_args": list(parsed.forwarded_args),
    }


def _append_search_metadata_event(
    *,
    command: str,
    subcommand: str | None,
    query: str,
    query_shape: str,
    file_path: Path | None,
    hit_count: int,
    selected_candidate_index: int,
    cache_hit: bool,
    result_source: str,
    elapsed_ms: float,
    signature: str,
) -> None:
    """Append one bounded search metadata record for long-term local inspection."""
    _append_jsonl_object(
        _read_code_search_metadata_log_path(),
        {
            "ts": time.time(),
            "session_id": _read_code_session_id(),
            "command": command,
            "subcommand": subcommand,
            "query": query,
            "query_shape": query_shape,
            "file_path": str(file_path.resolve()) if file_path is not None else None,
            "hit_count": hit_count,
            "selected_candidate_index": selected_candidate_index,
            "cache_hit": cache_hit,
            "result_source": result_source,
            "elapsed_ms": round(elapsed_ms, 3),
            "repo_signature": signature,
        },
        sort_keys=True,
    )


def _load_search_metadata_events() -> list[dict[str, object]]:
    """Load persisted read_code search metadata events from the repo-local JSONL log."""
    log_path = _read_code_search_metadata_log_path()
    if not log_path.is_file():
        return []
    try:
        raw_lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, object]] = []
    for raw_line in raw_lines:
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _history_label(event: dict[str, object]) -> str:
    """Return the compact command label used for history rendering."""
    command = event.get("command")
    subcommand = event.get("subcommand")
    if not isinstance(command, str):
        return "unknown"
    if isinstance(subcommand, str) and subcommand:
        return f"{command}:{subcommand}"
    return command


def _render_history_recent(events: list[dict[str, object]], *, limit: int) -> None:
    """Render a bounded recent-event view for read_code search history."""
    print("history_command: recent")
    selected = list(reversed(events[-limit:])) if limit > 0 else list(reversed(events))
    print(f"entry_count: {len(selected)}")
    if not selected:
        print("# no recorded search events")
        return
    print("# index\ttime\tcommand\tquery_shape\thits\tselected\tcache\telapsed_ms\tquery")
    for index, event in enumerate(selected):
        ts = event.get("ts")
        rendered_time = "unknown"
        if isinstance(ts, (int, float)):
            rendered_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
        query = event.get("query")
        query_shape = event.get("query_shape")
        hit_count = event.get("hit_count")
        selected_index = event.get("selected_candidate_index")
        cache_hit = "hit" if event.get("cache_hit") is True else "miss"
        elapsed_ms = event.get("elapsed_ms")
        print(
            f"{index}\t{rendered_time}\t{_history_label(event)}\t"
            f"{query_shape if isinstance(query_shape, str) else 'unknown'}\t"
            f"{hit_count if isinstance(hit_count, int) else 0}\t"
            f"{selected_index if isinstance(selected_index, int) else -1}\t"
            f"{cache_hit}\t"
            f"{elapsed_ms if isinstance(elapsed_ms, (int, float)) else 0}\t"
            f"{query if isinstance(query, str) else ''}"
        )


def _render_history_stats(events: list[dict[str, object]]) -> None:
    """Render aggregate counts, timings, and cache hit rates for search metadata."""
    print("history_command: stats")
    total_events = len(events)
    print(f"event_count: {total_events}")
    if total_events == 0:
        print("# no recorded search events")
        return
    cache_hits = sum(1 for event in events if event.get("cache_hit") is True)
    total_elapsed = sum(float(event.get("elapsed_ms", 0.0)) for event in events if isinstance(event.get("elapsed_ms"), (int, float)))
    average_elapsed = total_elapsed / total_events if total_events else 0.0
    print(f"cache_hit_count: {cache_hits}")
    print(f"cache_hit_rate: {cache_hits / total_events:.2f}")
    print(f"average_elapsed_ms: {average_elapsed:.2f}")

    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for event in events:
        command = event.get("command")
        query_shape = event.get("query_shape")
        if not isinstance(command, str):
            continue
        shape_label = query_shape if isinstance(query_shape, str) and query_shape else "unknown"
        bucket = grouped.setdefault((command, shape_label), {"count": 0.0, "cache_hits": 0.0, "elapsed_ms": 0.0})
        bucket["count"] += 1.0
        if event.get("cache_hit") is True:
            bucket["cache_hits"] += 1.0
        elapsed_ms = event.get("elapsed_ms")
        if isinstance(elapsed_ms, (int, float)):
            bucket["elapsed_ms"] += float(elapsed_ms)

    ordered = sorted(grouped.items(), key=lambda item: (-item[1]["count"], item[0][0], item[0][1]))
    print("# command\tquery_shape\tcount\tavg_elapsed_ms\tcache_hit_rate")
    for (command, query_shape), bucket in ordered[:READ_CODE_HISTORY_MAX_STATS_ROWS]:
        count = int(bucket["count"])
        average_ms = bucket["elapsed_ms"] / count if count else 0.0
        hit_rate = bucket["cache_hits"] / count if count else 0.0
        print(f"{command}\t{query_shape}\t{count}\t{average_ms:.2f}\t{hit_rate:.2f}")


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
    prefix = "Vector semantic anchor unavailable"
    if runtime_note and runtime_note.startswith("vector trust "):
        prefix = "Vector trust escalated"
    if resolved_line is not None:
        if runtime_note:
            print(
                f"WARN: {prefix} ({runtime_note}); using strict/local anchor for '{pattern}' in {file_path}.",
                file=sys.stderr,
            )
        else:
            print(
                f"WARN: {prefix} for '{pattern}' in {file_path}; using strict/local anchor.",
                file=sys.stderr,
            )
        return

    if runtime_note:
        print(
            f"WARN: {prefix} ({runtime_note}) for '{pattern}' in {file_path}.",
            file=sys.stderr,
        )


def _coerce_line(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    return None




def _tail_lines(text: str, count: int = 20) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-count:]


def codegraph_discover_or_fail(
    pattern: str,
    scope_path: Path | None = None,
    *,
    skip_preflight_refresh: bool = False,
) -> bool:
    """Run bounded codegraph discovery and self-heal index fragility once."""
    if not pattern:
        print("ERROR: codegraph discovery requires a non-empty symbol_or_pattern", file=sys.stderr)
        return False

    if not _command_exists("uv"):
        print("ERROR: uv is required for codegraph discovery (uv run cgc ...)", file=sys.stderr)
        return False

    path = scope_path or REPO_ROOT
    init_codegraph_env()
    if not skip_preflight_refresh and not codegraph_refresh_if_needed(path):
        return False

    cmd = ["uv", "run", "--no-sync", "cgc", "find", "pattern", "--", pattern]
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode == 0:
        return True

    output = (proc.stdout or "") + (proc.stderr or "")
    safe_index = SCRIPT_DIR / "cgc_safe_index.py"
    has_self_heal_pattern = "Database Connection Error" in output or "No index metadata" in output
    if has_self_heal_pattern and safe_index.is_file() and os.access(safe_index, os.X_OK):
        _run_command_capture([str(safe_index), str(path)])
        second = _run_command_capture(cmd)
        if second.returncode == 0:
            return True
        output = (second.stdout or "") + (second.stderr or "")

    print(f"ERROR: codegraph discovery failed for pattern: {pattern}", file=sys.stderr)
    print("Hint: run scripts/cgc_safe_index.py <scoped-path> and retry.", file=sys.stderr)
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


def _is_scoped_context_pattern(pattern: str) -> bool:
    """Return whether a context query is shaped like a scoped symbol lookup."""
    if not pattern:
        return False
    normalized_pattern = normalize_symbol_pattern(pattern)
    if pattern.startswith(("async def ", "def ", "class ")):
        return bool(normalized_pattern)
    if any(char.isspace() for char in pattern):
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", normalized_pattern))


def _classify_context_query_scope(parsed: _ContextArgs) -> _ContextQueryScope:
    """Classify a parsed read_code_context request as scoped or broad."""
    if parsed.file_path is not None:
        return _ContextQueryScope(is_scoped=True, reason="file-path supplied")
    if _is_scoped_context_pattern(parsed.pattern):
        return _ContextQueryScope(is_scoped=True, reason="symbol-shaped pattern")
    return _ContextQueryScope(is_scoped=False, reason="broad natural-language pattern")


def _candidate_nested_value(item: dict[str, object], key: str) -> object | None:
    """Return candidate content[key] when a nested content mapping is present."""
    content = item.get("content")
    if isinstance(content, dict):
        return content.get(key)
    return None


def _resolve_candidate_line(item: dict[str, object]) -> int | None:
    line = _coerce_line(item.get("line_start"))
    if line is not None:
        return line
    return _coerce_line(_candidate_nested_value(item, "line_start"))


def _candidate_text(item: dict[str, object], key: str) -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, str):
        return nested
    return ""


def _candidate_int(item: dict[str, object], key: str) -> int | None:
    value = item.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value, 10)
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, int):
        return nested
    if isinstance(nested, str) and nested.isdigit():
        return int(nested, 10)
    return None


def _candidate_string_list(item: dict[str, object], key: str) -> list[str]:
    value = item.get(key)
    if isinstance(value, list):
        return [str(part) for part in value if str(part)]
    nested = _candidate_nested_value(item, key)
    if isinstance(nested, list):
        return [str(part) for part in nested if str(part)]
    return []


def _candidate_unit_id(item: dict[str, object]) -> str:
    symbol_name = _candidate_text(item, "symbol_name")
    symbol_type = _candidate_text(item, "symbol_type") or "symbol"
    if not symbol_name:
        return ""
    return f"{symbol_type}:{symbol_name}"


def _candidate_raw_score(item: dict[str, object]) -> float:
    value = item.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    nested_score = _candidate_nested_value(item, "score")
    if isinstance(nested_score, (int, float)):
        return float(nested_score)

    distance = item.get("distance")
    if isinstance(distance, (int, float)):
        return max(0.0, 1.0 - float(distance))
    nested_distance = _candidate_nested_value(item, "distance")
    if isinstance(nested_distance, (int, float)):
        return max(0.0, 1.0 - float(nested_distance))
    return 0.0


def _vector_anchor_rank(match: _VectorMatch, *, allow_test_files: bool = False) -> tuple[int, int]:
    """Rank semantic anchors with a mild default penalty for test-file candidates."""
    return (
        match.cosine_similarity,
        0 if allow_test_files or not _is_test_path(match.file_path) else -1,
    )


def _reranker_document_text(match: _VectorMatch) -> str:
    """Return the best available text payload for shortlist reranking."""
    primary = (match.body or match.preview or match.signature or "").strip()
    secondary = match.docstring.strip()
    if primary and secondary and secondary not in primary:
        return f"{primary}\n\n{secondary}"
    if primary:
        return primary
    if secondary:
        return secondary
    return match.qualified_name or match.symbol_name


def _rerank_semantic_candidates(
    query: str,
    candidates: list[_VectorMatch],
    *,
    allow_test_files: bool,
) -> tuple[list[_VectorMatch], _RerankDebugInfo]:
    """Rescore the current shortlist window with the local reranker when available."""
    before_symbols = tuple(match.symbol_name or match.qualified_name for match in candidates[:READ_CODE_RERANK_CANDIDATE_LIMIT])
    if len(candidates) < 2:
        return candidates, _RerankDebugInfo(
            status="skipped",
            model_name=None,
            candidate_count=len(candidates),
            changed=False,
            before_symbols=before_symbols,
            after_symbols=before_symbols,
        )
    backend = _load_read_code_reranker()
    if backend is None:
        return candidates, _RerankDebugInfo(
            status="unavailable",
            model_name=_read_code_reranker_model_name(),
            candidate_count=len(candidates),
            changed=False,
            before_symbols=before_symbols,
            after_symbols=before_symbols,
        )
    rerank_window = list(candidates[:READ_CODE_RERANK_CANDIDATE_LIMIT])
    scores = backend.score_pairs(query, [_reranker_document_text(match) for match in rerank_window])
    if len(scores) != len(rerank_window):
        return candidates, _RerankDebugInfo(
            status="unavailable",
            model_name=getattr(backend, "model_name", _read_code_reranker_model_name()),
            candidate_count=len(candidates),
            changed=False,
            before_symbols=before_symbols,
            after_symbols=before_symbols,
        )
    reranked = [
        match
        for _, match in sorted(
            enumerate(rerank_window),
            key=lambda item: (
                scores[item[0]],
                *(_vector_anchor_rank(item[1], allow_test_files=allow_test_files)),
                -item[0],
            ),
            reverse=True,
        )
    ]
    ordered = reranked + candidates[READ_CODE_RERANK_CANDIDATE_LIMIT :]
    after_symbols = tuple(match.symbol_name or match.qualified_name for match in ordered[:READ_CODE_RERANK_CANDIDATE_LIMIT])
    return ordered, _RerankDebugInfo(
        status="applied",
        model_name=getattr(backend, "model_name", _read_code_reranker_model_name()),
        candidate_count=len(candidates),
        changed=before_symbols != after_symbols,
        before_symbols=before_symbols,
        after_symbols=after_symbols,
    )


def _is_explicit_test_targeting(file_path: Path | None, content_type: str | None) -> bool:
    """Return whether a discovery request is explicitly aimed at tests."""
    return content_type == "tests" or (file_path is not None and _is_test_path(file_path))


def _is_test_path(path: Path) -> bool:
    """Return whether a candidate path lives under the repository test tree."""
    return any(part.lower() == "tests" for part in path.parts)


def _matches_context_content_type(match: _VectorMatch, content_type: str | None) -> bool:
    """Return whether a semantic candidate belongs to the requested content type."""
    if content_type is None:
        return True
    if content_type == "markdown":
        return _is_markdown(match.file_path)
    if content_type == "tests":
        return _is_test_path(match.file_path)
    if content_type == "code":
        return not _is_markdown(match.file_path) and not _is_test_path(match.file_path)
    return True


def _vector_match_for_item(item: dict[str, object], query: str, normalized_query: str) -> _VectorMatch | None:
    line_num = _resolve_candidate_line(item)
    if line_num is None:
        return None

    raw_score = _candidate_raw_score(item)
    body = _candidate_text(item, "body")
    preview = _candidate_text(item, "preview")
    signature = _candidate_text(item, "signature")
    docstring = _candidate_text(item, "docstring")
    has_docstring = bool(docstring)
    line_end = _candidate_int(item, "line_end") or line_num
    file_path_str = _candidate_text(item, "file_path")
    symbol_name = _candidate_text(item, "symbol_name")
    qualified_name = _candidate_text(item, "qualified_name")
    cosine_similarity = int(round(raw_score * 100))
    return _VectorMatch(
        line_num=line_num,
        raw_score=raw_score,
        cosine_similarity=cosine_similarity,
        symbol_type=_candidate_text(item, "symbol_type"),
        has_body=bool(body),
        has_docstring=has_docstring,
        body=body,
        preview=preview,
        signature=signature,
        file_path=Path(file_path_str) if file_path_str else Path(),
        unit_id=_candidate_unit_id(item),
        symbol_name=symbol_name,
        qualified_name=qualified_name,
        line_end=line_end,
        docstring=docstring,
    )


def _vector_query_candidates(
    file_path: Path | None,
    query: str,
    normalized_query: str,
    scope: str,
    *,
    allow_test_files: bool = False,
) -> list[_VectorMatch]:
    """Return the initial semantic retrieval window for one query scope."""
    if not query or not scope:
        return []
    if not _command_exists("uv"):
        _set_vector_runtime_note("uv is not available")
        return []

    cmd = _vector_indexer_cmd(
        REPO_ROOT,
        "query",
        query,
        "--scope",
        scope,
        "--top-k",
        "20",
    )
    if file_path is not None:
        cmd = _vector_indexer_cmd(
            REPO_ROOT,
            "query",
            query,
            "--file-path",
            str(file_path.resolve()),
            "--scope",
            scope,
            "--top-k",
            "20",
        )
    proc = _run_command_capture(cmd, env=_vector_command_env())
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if stderr:
            _set_vector_runtime_note(f"indexer query failed: {stderr.splitlines()[0]}")
        else:
            _set_vector_runtime_note(f"indexer query failed with exit code {proc.returncode}")
        return []

    try:
        payload = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        _set_vector_runtime_note("indexer query returned invalid JSON")
        return []
    if not isinstance(payload, list):
        _set_vector_runtime_note("indexer query returned unexpected payload shape")
        return []

    target = file_path.resolve() if file_path is not None else None
    matches: list[_VectorMatch] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate = _candidate_text(item, "file_path")
        if not candidate:
            continue
        if target is not None:
            try:
                if Path(candidate).expanduser().resolve() != target:
                    continue
            except Exception:
                continue
        match = _vector_match_for_item(item, query, normalized_query)
        if match is None:
            continue
        matches.append(match)

    return sorted(
        matches,
        key=lambda match: _vector_anchor_rank(match, allow_test_files=allow_test_files),
        reverse=True,
    )[:READ_CODE_RERANK_CANDIDATE_LIMIT]


def _vector_find_candidates(
    file_path: Path | None,
    raw_pattern: str,
    normalized_pattern: str,
    scope: str,
    *,
    allow_test_files: bool = False,
) -> list[_VectorMatch]:
    """Return the bounded shortlist for a query using raw and normalized probes."""
    _clear_vector_runtime_note()
    candidates: list[_VectorMatch] = []
    if raw_pattern:
        candidates = _vector_query_candidates(
            file_path,
            raw_pattern,
            normalized_pattern,
            scope,
            allow_test_files=allow_test_files,
        )
    if not candidates and normalized_pattern and normalized_pattern != raw_pattern:
        candidates = _vector_query_candidates(
            file_path,
            normalized_pattern,
            normalized_pattern,
            scope,
            allow_test_files=allow_test_files,
        )
    return candidates



def _render_numbered_window(file_path: Path, start: int, end: int) -> None:
    with file_path.open(encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            if idx < start:
                continue
            if idx > end:
                break
            print(f"{idx:6}\t{line.rstrip()}")


def _split_context_window(context_lines: int) -> tuple[int, int]:
    """Split context budget into a small pre-window and larger post-window."""
    if context_lines <= 1:
        return 0, context_lines

    pre_lines = max(1, int(context_lines * READ_CODE_CONTEXT_PRE_FRACTION))
    pre_lines = min(pre_lines, READ_CODE_CONTEXT_PRE_CAP, context_lines - 1)
    post_lines = context_lines - pre_lines
    return pre_lines, post_lines



def _render_candidate_shortlist(candidates: list[_VectorMatch], query: str) -> None:
    """Render a bounded shortlist of ranked vector candidates."""
    if not candidates:
        return
    limit = 3
    print(f"# shortlist for: {query}")
    print(
        "# cosine_similarity\tfile_path\tunit_id\tline_num-line_end\ttype\tbody\tdocstring\traw"
    )
    for candidate in candidates[:limit]:
        print(
            "\t".join(
                [
                    f"{candidate.cosine_similarity:3}",
                    str(candidate.file_path),
                    candidate.unit_id,
                    f"{candidate.line_num}-{candidate.line_end}",
                    candidate.symbol_type or "symbol",
                    "yes" if candidate.has_body else "no",
                    "yes" if candidate.has_docstring else "no",
                    f"{candidate.raw_score:.3f}",
                ]
            )
        )
    if len(candidates) > limit:
        print(
            f"# shortlist truncated to top {limit}; use --next-candidate or --candidate-index N to step further"
        )


def _render_compact_match(candidate: _VectorMatch, has_more_candidates: bool = False) -> None:
    """Render compact metadata for a selected semantic match with exploration hints."""
    output = f"file_path: {candidate.file_path}"
    output += f"\nsignature: {candidate.signature}"
    if candidate.docstring:
        output += f"\ndocstring: {candidate.docstring.rstrip()}"
    output += f"\ncosine_similarity: {candidate.cosine_similarity}/100"

    hints = []
    if candidate.has_body:
        hints.append("--inline-body for function body and implementation")
    if has_more_candidates:
        hints.append("--next-candidate for the next ranked candidate")
    unit_id = candidate.unit_id
    if unit_id:
        hints.append(f"uv run cgc analyze callers '{unit_id}' for call sites")
    if hints:
        output += f"\n# {', '.join(hints)}"

    print(output)


def _render_candidate_body(candidate: _VectorMatch) -> None:
    """Render an indexed symbol body when confidence clears the body-first threshold."""
    if not candidate.body:
        return
    print("# body")
    print(candidate.body.rstrip())


def _find_shortlist_limit(command: str) -> int:
    """Return the bounded shortlist size for a find subcommand."""
    return 3 if command == "content" else 5


def _analyze_shortlist_limit() -> int:
    """Return the bounded shortlist size for analyze discovery output."""
    return 3


def _render_find_shortlist(
    matches: list[_FindMatch],
    command: str,
    query: str,
    *,
    limit: int,
) -> None:
    """Render a bounded shortlist of parsed find matches."""
    if not matches:
        return
    print(f"# shortlist for find {command}: {query}")
    print("# index\tname\ttype\tlocation")
    for index, match in enumerate(matches[:limit]):
        print(f"{index}\t{match.name}\t{match.symbol_type}\t{match.location}")
    if len(matches) > limit:
        print(f"# shortlist truncated to top {limit}; use --next-candidate or --candidate-index N to step further")


def _render_compact_find_match(
    match: _FindMatch,
    *,
    command: str,
    query: str,
    candidate_index: int,
    total_matches: int,
    has_more_candidates: bool,
) -> None:
    """Render a selected find result using the same stepwise dig language as context."""
    output = f"find_command: {command}"
    output += f"\nquery: {query}"
    output += f"\nname: {match.name}"
    output += f"\ntype: {match.symbol_type}"
    output += f"\nlocation: {match.location}"
    output += f"\nmatch_index: {candidate_index}/{total_matches - 1}"

    hints = []
    if has_more_candidates:
        hints.append("--next-candidate for the next ranked match")
    hints.append("--show-shortlist to inspect ranked matches")
    hints.append("--verbose for raw cgc output")
    output += f"\n# {', '.join(hints)}"
    print(output)


def _render_analyze_shortlist(matches: list[_AnalyzeMatch], command: str, query: str) -> None:
    """Render a bounded shortlist of parsed analyze matches."""
    if not matches:
        return
    limit = _analyze_shortlist_limit()
    print(f"# shortlist for analyze {command}: {query}")
    print("# index\tlocation")
    for index, match in enumerate(matches[:limit]):
        print(f"{index}\t{match.location}")
    if len(matches) > limit:
        print(
            f"# shortlist truncated to top {limit}; use --next-candidate or --candidate-index N to step further"
        )


def _render_compact_analyze_match(
    match: _AnalyzeMatch,
    *,
    command: str,
    query: str,
    candidate_index: int,
    total_matches: int,
    has_more_candidates: bool,
) -> None:
    """Render a selected analyze result with stepwise dig hints."""
    output = f"analyze_command: {command}"
    output += f"\nquery: {query}"
    for key, value in match.columns.items():
        label = key.lower().replace(" ", "_")
        output += f"\n{label}: {value}"
    output += f"\nmatch_index: {candidate_index}/{total_matches - 1}"
    hints = []
    if has_more_candidates:
        hints.append("--next-candidate for the next ranked match")
    hints.append("--show-shortlist to inspect ranked matches")
    hints.append("--verbose for raw cgc output")
    output += f"\n# {', '.join(hints)}"
    print(output)


def candidate_body_helper(candidates: list[_VectorMatch], index: int) -> str | None:
    """Return a non-top shortlist candidate body through a bounded lookup."""
    if index < 0 or index >= len(candidates):
        return None
    candidate = candidates[index]
    if not candidate.body:
        return None
    return candidate.body


def _select_vector_candidate(candidates: list[_VectorMatch], index: int) -> tuple[_VectorMatch | None, str | None]:
    """Select a ranked candidate index while returning actionable selection errors."""
    if index < 0:
        return None, f"candidate index must be >= 0: {index}"
    if not candidates:
        if index == 0:
            return None, None
        return None, "no ranked candidates available for requested candidate index"
    if index >= len(candidates):
        return None, f"candidate index {index} is out of range (available: 0..{len(candidates) - 1})"
    return candidates[index], None


def _select_semantic_anchor_candidate(
    candidates: list[_VectorMatch],
    index: int,
) -> tuple[_VectorMatch | None, str | None]:
    """Select the semantic anchor at the requested index."""
    selected, error = _select_vector_candidate(candidates, index)
    return selected, error


def _semantic_anchor_candidate_scopes(
    request_scope: _ContextQueryScope | None,
    content_type: str | None,
) -> tuple[str, ...]:
    """Return the candidate scopes needed for semantic anchor retrieval."""
    if request_scope is not None and request_scope.is_scoped and content_type != "markdown":
        return ("code",)
    return ("code", "markdown")


def _query_semantic_anchor_candidate_with_debug(
    file_path: Path | None,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    show_shortlist_hint: bool,
    content_type: str | None,
    request_scope: _ContextQueryScope | None = None,
) -> tuple[list[_VectorMatch], _VectorMatch | None, bool, _RerankDebugInfo | None]:
    """Query ranked candidates and select a semantic anchor with standardized error handling."""
    candidate_scopes = _semantic_anchor_candidate_scopes(request_scope, content_type)
    allow_test_files = _is_explicit_test_targeting(file_path, content_type)
    code_candidates = _vector_find_candidates(
        file_path,
        pattern,
        normalized_pattern,
        "code",
        allow_test_files=allow_test_files,
    )
    markdown_candidates = (
        _vector_find_candidates(
            file_path,
            pattern,
            normalized_pattern,
            "markdown",
            allow_test_files=allow_test_files,
        )
        if "markdown" in candidate_scopes
        else []
    )
    vector_candidates = sorted(
        [
            candidate
            for candidate in (code_candidates + markdown_candidates)
            if _matches_context_content_type(candidate, content_type)
        ],
        key=lambda match: _vector_anchor_rank(match, allow_test_files=allow_test_files),
        reverse=True,
    )[:READ_CODE_RERANK_CANDIDATE_LIMIT]
    vector_candidates, rerank_debug = _rerank_semantic_candidates(
        pattern,
        vector_candidates,
        allow_test_files=allow_test_files,
    )
    vector_candidates = vector_candidates[:READ_CODE_FINAL_SHORTLIST_LIMIT]
    vector_match, candidate_error = _select_semantic_anchor_candidate(vector_candidates, candidate_index)
    if candidate_error is not None:
        print(f"ERROR: {candidate_error}", file=sys.stderr)
        if show_shortlist_hint and vector_candidates:
            print("Hint: re-run with --show-shortlist to inspect ranked candidates.", file=sys.stderr)
        return vector_candidates, None, False, rerank_debug
    return vector_candidates, vector_match, True, rerank_debug


def _query_semantic_anchor_candidate(
    file_path: Path | None,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    show_shortlist_hint: bool,
    content_type: str | None,
    request_scope: _ContextQueryScope | None = None,
) -> tuple[list[_VectorMatch], _VectorMatch | None, bool]:
    """Query ranked candidates and select a semantic anchor."""
    vector_candidates, vector_match, selection_ok, _ = _query_semantic_anchor_candidate_with_debug(
        file_path,
        pattern,
        normalized_pattern,
        candidate_index=candidate_index,
        show_shortlist_hint=show_shortlist_hint,
        content_type=content_type,
        request_scope=request_scope,
    )
    return vector_candidates, vector_match, selection_ok


def _render_rerank_debug(debug: _RerankDebugInfo, *, result_source: str) -> None:
    """Render a bounded, opt-in rerank summary for one context resolution."""
    print("# rerank_debug")
    print(f"rerank_status: {debug.status}")
    if debug.model_name:
        print(f"reranker_model: {debug.model_name}")
    print(f"candidate_window: {debug.candidate_count}")
    print(f"shortlist_changed: {'true' if debug.changed else 'false'}")
    print(f"result_source: {result_source}")
    print(f"before: {' | '.join(debug.before_symbols) if debug.before_symbols else '(empty)'}")
    print(f"after: {' | '.join(debug.after_symbols) if debug.after_symbols else '(empty)'}")


def _broad_read_trusts_vector_cache(
    file_path: Path | None,
    request_scope: _ContextQueryScope | None,
) -> bool:
    """Return whether a broad read can skip codegraph escalation."""
    return (
        file_path is not None
        and request_scope is not None
        and request_scope.is_scoped is False
        and evaluate_read_vector_trust(file_path, request_is_scoped=False)
    )


def _broad_read_needs_recovery(
    file_path: Path | None,
    vector_candidates: list[_VectorMatch],
    vector_match: _VectorMatch | None,
    *,
    allow_fallback: bool,
    request_scope: _ContextQueryScope | None,
) -> bool:
    """Return whether a broad read should escalate to codegraph recovery."""
    if not allow_fallback or file_path is None:
        return False
    if request_scope is None or request_scope.is_scoped is True:
        return False
    if not _broad_read_trusts_vector_cache(file_path, request_scope):
        return True
    if vector_match is None:
        return True
    if vector_match.cosine_similarity < 80:
        return True
    if len(vector_candidates) > 1 and (vector_candidates[0].cosine_similarity - vector_candidates[1].cosine_similarity) <= 5:
        return True
    return False


def _resolve_pattern_anchor(
    file_path: Path | None,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    allow_fallback: bool,
    show_shortlist_hint: bool,
    content_type: str | None,
    request_scope: _ContextQueryScope | None = None,
) -> _AnchorResolution | None:
    if _is_markdown(file_path):
        assert file_path is not None
        line_num = _resolve_markdown_anchor_vector(file_path, pattern)
        if line_num is None:
            line_num = _resolve_markdown_anchor_fallback(file_path, pattern)

        if line_num is not None:
            # Construct a synthetic match for markdown
            vector_match = _VectorMatch(
                unit_id="markdown",
                symbol_name=pattern,
                qualified_name=f"{file_path}:{pattern}",
                line_num=line_num,
                line_end=line_num,
                raw_score=1.0,
                file_path=file_path,
                signature=f"## {pattern}",
                docstring="",
                cosine_similarity=100,
            )
            if not _matches_context_content_type(vector_match, content_type):
                return None
            return _AnchorResolution(
                vector_candidates=[vector_match],
                vector_match=vector_match,
                strict_status=0,
                line_num=line_num,
                rerank_debug=None,
            )
        return None

    vector_candidates, vector_match, selection_ok, rerank_debug = _query_semantic_anchor_candidate_with_debug(
        file_path,
        pattern,
        normalized_pattern,
        candidate_index=candidate_index,
        show_shortlist_hint=show_shortlist_hint,
        content_type=content_type,
        request_scope=request_scope,
    )
    if not selection_ok:
        return None

    line_num: int | None = vector_match.line_num if vector_match is not None else None
    needs_recovery = _broad_read_needs_recovery(
        file_path,
        vector_candidates,
        vector_match,
        allow_fallback=allow_fallback,
        request_scope=request_scope,
    )
    emitted_fallback_notice = False
    if file_path is not None and needs_recovery:
        _emit_vector_fallback_notice(
            file_path=file_path,
            pattern=pattern,
            vector_match=None,
            resolved_line=line_num,
        )
        emitted_fallback_notice = True
        if codegraph_supports_file(file_path):
            discover_pattern = (
                normalized_pattern
                if normalized_pattern and normalized_pattern != pattern
                else pattern
            )
            if not codegraph_discover_or_fail(
                discover_pattern,
                file_path.parent,
                skip_preflight_refresh=True,
            ):
                return None

            refreshed_candidates, refreshed_match, selection_ok, rerank_debug = _query_semantic_anchor_candidate_with_debug(
                file_path,
                pattern,
                normalized_pattern,
                candidate_index=candidate_index,
                show_shortlist_hint=show_shortlist_hint,
                content_type=content_type,
                request_scope=request_scope,
            )
            if not selection_ok:
                return None
            if refreshed_candidates:
                vector_candidates = refreshed_candidates
                vector_match = refreshed_match
                if vector_match is not None:
                    line_num = vector_match.line_num

    if file_path is not None:
        if emitted_fallback_notice:
            return _AnchorResolution(
                vector_candidates=vector_candidates,
                vector_match=vector_match,
                strict_status=0,
                line_num=line_num,
                rerank_debug=rerank_debug,
            )
        _emit_vector_fallback_notice(
            file_path=file_path,
            pattern=pattern,
            vector_match=vector_match,
            resolved_line=line_num,
        )
    return _AnchorResolution(
        vector_candidates=vector_candidates,
        vector_match=vector_match,
        strict_status=0,
        line_num=line_num,
        rerank_debug=rerank_debug,
    )


def _render_read_context_inline_body(vector_match: _VectorMatch, line_num: int, context: int) -> None:
    """Render the existing inline-body window for a resolved read context."""
    start = 1
    end = 1
    if _is_markdown(vector_match.file_path):
        start = line_num
        end = _find_markdown_section_end(vector_match.file_path, line_num)
    else:
        pre_lines, post_lines = _split_context_window(context)
        start = max(1, line_num - pre_lines)
        end = line_num + post_lines
    _render_numbered_window(vector_match.file_path, start, end)


def _validate_file_and_positive_int(
    file_arg: str,
    value_raw: str,
    *,
    value_label: str,
) -> tuple[Path, int] | None:
    """Validate an existing file path plus a positive integer argument."""
    file_path = Path(file_arg)
    if not file_path.is_file():
        print(f"ERROR: File not found: {file_arg}", file=sys.stderr)
        return None
    if not value_raw.isdigit() or int(value_raw, 10) <= 0:
        print(f"ERROR: {value_label} must be a positive integer: {value_raw}", file=sys.stderr)
        return None
    return file_path, int(value_raw, 10)


def _validate_positive_int(value_raw: str, *, value_label: str) -> int | None:
    """Validate a standalone positive integer argument."""
    if not value_raw.isdigit() or int(value_raw, 10) <= 0:
        print(f"ERROR: {value_label} must be a positive integer: {value_raw}", file=sys.stderr)
        return None
    return int(value_raw, 10)


def _parse_context_args(argv: list[str]) -> _ContextArgs | None:
    """Parse and validate read_code_context arguments."""
    if len(argv) < 1:
        print(
            "ERROR: read_code_context requires: <file_path> <symbol_or_pattern> [context_lines] OR <symbol_or_pattern> [--path <file>]",
            file=sys.stderr,
        )
        return None

    file_path: Path | None = None
    pattern: str = ""
    context = READ_CODE_DEFAULT_CONTEXT_LINES
    context_set = False
    allow_fallback = False
    show_shortlist = False
    show_rerank = False
    inline_body = False
    candidate_index = 0
    content_type: str | None = None
    expect_candidate_index = False
    expect_path = False
    expect_content_type = False

    first_arg = argv[0]
    first_is_file = False
    first_path: Path | None = None
    try:
        first_path = Path(first_arg)
        first_is_file = first_path.is_file()
    except (OSError, ValueError):
        pass

    if first_is_file and len(argv) >= 2:
        # Old syntax: read_code context <file_path> <query> [...]
        assert first_path is not None
        file_path = first_path
        pattern = argv[1]
        extra = argv[2:]
    else:
        # New syntax: read_code context "<query>" [...--path <file>...]
        pattern = first_arg
        extra = argv[1:]

    for token in extra:
        if expect_candidate_index:
            if not token.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {token}", file=sys.stderr)
                return None
            candidate_index = int(token, 10)
            expect_candidate_index = False
        elif expect_content_type:
            if token not in {"code", "markdown", "tests"}:
                print(f"ERROR: --content-type expects one of: code, markdown, tests ({token})", file=sys.stderr)
                return None
            content_type = token
            expect_content_type = False
        elif expect_path:
            path_candidate = Path(token)
            if not path_candidate.is_file():
                print(f"ERROR: --path requires an existing file: {token}", file=sys.stderr)
                return None
            file_path = path_candidate
            expect_path = False
        elif token == "--hud-symbol":
            continue
        elif token == "--allow-fallback":
            allow_fallback = True
        elif token == "--show-shortlist":
            show_shortlist = True
        elif token == "--show-rerank":
            show_rerank = True
        elif token == "--inline-body":
            inline_body = True
        elif token == "--next-candidate":
            candidate_index += 1
        elif token == "--candidate-index":
            expect_candidate_index = True
        elif token.startswith("--candidate-index="):
            _, _, value = token.partition("=")
            if not value.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {value}", file=sys.stderr)
                return None
            candidate_index = int(value, 10)
        elif token == "--content-type":
            expect_content_type = True
        elif token.startswith("--content-type="):
            _, _, value = token.partition("=")
            if value not in {"code", "markdown", "tests"}:
                print(f"ERROR: --content-type expects one of: code, markdown, tests ({value})", file=sys.stderr)
                return None
            content_type = value
        elif token == "--path":
            expect_path = True
        elif token.startswith("--path="):
            _, _, value = token.partition("=")
            path_candidate = Path(value)
            if not path_candidate.is_file():
                print(f"ERROR: --path requires an existing file: {value}", file=sys.stderr)
                return None
            file_path = path_candidate
        elif token.isdigit() and not context_set:
            context = int(token, 10)
            context_set = True
        else:
            print(f"ERROR: Unexpected argument for context mode: {token}", file=sys.stderr)
            return None
    if expect_candidate_index:
        print("ERROR: --candidate-index requires a value", file=sys.stderr)
        return None
    if expect_content_type:
        print("ERROR: --content-type requires a value", file=sys.stderr)
        return None
    if expect_path:
        print("ERROR: --path requires a value", file=sys.stderr)
        return None

    if not pattern:
        print("ERROR: symbol_or_pattern is required", file=sys.stderr)
        return None

    if context > READ_CODE_MAX_LINES:
        print(f"ERROR: context_lines exceeds max ({READ_CODE_MAX_LINES}): {context}", file=sys.stderr)
        return None

    return _ContextArgs(
        file_path=file_path,
        pattern=pattern,
        context=context,
        allow_fallback=allow_fallback,
        show_shortlist=show_shortlist,
        inline_body=inline_body,
        candidate_index=candidate_index,
        content_type=content_type,
        show_rerank=show_rerank,
    )


def _parse_window_args(argv: list[str]) -> _WindowArgs | None:
    """Parse and validate read_code_window arguments."""
    if len(argv) < 3:
        print(
            "ERROR: read_code_window requires: <file_path> <start_line> <end_line>",
            file=sys.stderr,
        )
        return None

    file_arg = argv[0]
    start_line_raw = argv[1]
    end_line_raw = argv[2]
    extra = argv[3:]

    pattern = ""
    hud_flag = False
    allow_fallback = False

    for token in extra:
        if token == "--hud-symbol":
            hud_flag = True
        elif token == "--allow-fallback":
            allow_fallback = True
        elif not pattern:
            pattern = token
        else:
            print(f"ERROR: Unexpected argument for window mode: {token}", file=sys.stderr)
            return None

    validated = _validate_file_and_positive_int(file_arg, start_line_raw, value_label="start_line")
    if validated is None:
        return None
    file_path, start_line = validated

    end_line = _validate_positive_int(end_line_raw, value_label="end_line")
    if end_line is None:
        return None

    if end_line < start_line:
        print(
            f"ERROR: end_line must be greater than or equal to start_line: {end_line} < {start_line}",
            file=sys.stderr,
        )
        return None

    window_lines = end_line - start_line + 1
    if window_lines > READ_CODE_MAX_LINES:
        print(f"ERROR: window exceeds max ({READ_CODE_MAX_LINES}) lines: {window_lines}", file=sys.stderr)
        return None

    return _WindowArgs(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        pattern=pattern,
        use_hud_fast_path=hud_flag,
        allow_fallback=allow_fallback,
    )


def _parse_find_args(argv: list[str]) -> _FindArgs | None:
    """Parse read_code_find arguments while preserving cgc flags."""
    if not argv:
        print("ERROR: find mode requires a command (e.g. name, pattern)", file=sys.stderr)
        return None

    command = argv[0]
    if len(argv) == 1 or "--help" in argv[1:]:
        return _FindArgs(
            command=command,
            forwarded_args=argv[1:],
            candidate_index=0,
            show_shortlist=False,
        )

    candidate_index = 0
    show_shortlist = False
    expect_candidate_index = False
    forwarded_args: list[str] = []

    for token in argv[1:]:
        if expect_candidate_index:
            if not token.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {token}", file=sys.stderr)
                return None
            candidate_index = int(token, 10)
            expect_candidate_index = False
            continue
        if token == "--show-shortlist":
            show_shortlist = True
            continue
        if token == "--next-candidate":
            candidate_index += 1
            continue
        if token == "--candidate-index":
            expect_candidate_index = True
            continue
        if token.startswith("--candidate-index="):
            _, _, value = token.partition("=")
            if not value.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {value}", file=sys.stderr)
                return None
            candidate_index = int(value, 10)
            continue
        forwarded_args.append(token)

    if expect_candidate_index:
        print("ERROR: --candidate-index requires a value", file=sys.stderr)
        return None

    return _FindArgs(
        command=command,
        forwarded_args=forwarded_args,
        candidate_index=candidate_index,
        show_shortlist=show_shortlist,
    )


def _parse_analyze_args(argv: list[str]) -> _AnalyzeArgs | None:
    """Parse read_code_analyze arguments while preserving cgc flags."""
    if not argv:
        print("ERROR: analyze mode requires a command (e.g. callers, deps)", file=sys.stderr)
        return None

    command = argv[0]
    if len(argv) == 1 or "--help" in argv[1:]:
        return _AnalyzeArgs(
            command=command,
            forwarded_args=argv[1:],
            candidate_index=0,
            show_shortlist=False,
        )

    candidate_index = 0
    show_shortlist = False
    expect_candidate_index = False
    forwarded_args: list[str] = []
    for token in argv[1:]:
        if expect_candidate_index:
            if not token.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {token}", file=sys.stderr)
                return None
            candidate_index = int(token, 10)
            expect_candidate_index = False
            continue
        if token == "--show-shortlist":
            show_shortlist = True
            continue
        if token == "--next-candidate":
            candidate_index += 1
            continue
        if token == "--candidate-index":
            expect_candidate_index = True
            continue
        if token.startswith("--candidate-index="):
            _, _, value = token.partition("=")
            if not value.isdigit():
                print(f"ERROR: --candidate-index expects a non-negative integer: {value}", file=sys.stderr)
                return None
            candidate_index = int(value, 10)
            continue
        forwarded_args.append(token)
    if expect_candidate_index:
        print("ERROR: --candidate-index requires a value", file=sys.stderr)
        return None
    return _AnalyzeArgs(
        command=command,
        forwarded_args=forwarded_args,
        candidate_index=candidate_index,
        show_shortlist=show_shortlist,
    )


def _parse_history_args(argv: list[str]) -> _HistoryArgs | None:
    """Parse read_code_history arguments for bounded recent/stats inspection."""
    if not argv:
        print("ERROR: history mode requires a command (recent | stats)", file=sys.stderr)
        return None
    command = argv[0]
    if command not in {"recent", "stats"}:
        print(f"ERROR: Unknown history command '{command}'. Use: recent | stats", file=sys.stderr)
        return None
    if command == "stats":
        if len(argv) > 1:
            print("ERROR: history stats does not accept extra arguments", file=sys.stderr)
            return None
        return _HistoryArgs(command=command)
    limit = READ_CODE_HISTORY_DEFAULT_LIMIT
    if len(argv) > 2:
        print("ERROR: history recent accepts at most one optional limit", file=sys.stderr)
        return None
    if len(argv) == 2:
        limit_raw = argv[1]
        if not limit_raw.isdigit() or int(limit_raw, 10) <= 0:
            print(f"ERROR: history recent limit must be a positive integer: {limit_raw}", file=sys.stderr)
            return None
        limit = min(int(limit_raw, 10), READ_CODE_HISTORY_MAX_LIMIT)
    return _HistoryArgs(command=command, limit=limit)


def _repo_local_find_path(path: Path | None) -> bool:
    """Return whether a parsed find location points at repo-owned source content."""
    if path is None:
        return False
    try:
        resolved = path.resolve()
    except OSError:
        return False
    repo_root = REPO_ROOT.resolve()
    if not str(resolved).startswith(str(repo_root)):
        return False
    relative = resolved.relative_to(repo_root)
    return bool(relative.parts) and relative.parts[0] not in {".venv", ".uv-cache"}


def _parse_find_location(location: str) -> tuple[Path | None, int | None]:
    """Parse a cgc find location cell into a file path and optional line number."""
    if ":" not in location:
        return None, None
    raw_path, _, raw_line = location.rpartition(":")
    if not raw_line.isdigit():
        return Path(location), None
    return Path(raw_path), int(raw_line, 10)


def _parse_cgc_find_output(raw_output: str) -> list[_FindMatch]:
    """Parse the rich table emitted by cgc find into compact repo-local matches."""
    matches: list[_FindMatch] = []
    current_name = ""
    current_type = ""
    current_location = ""

    def flush_current() -> None:
        nonlocal current_name, current_type, current_location
        if not current_location:
            return
        path, line_num = _parse_find_location(current_location)
        match = _FindMatch(
            name=current_name,
            symbol_type=current_type or "symbol",
            location=current_location,
            path=path,
            line_num=line_num,
        )
        if _repo_local_find_path(match.path):
            matches.append(match)
        current_name = ""
        current_type = ""
        current_location = ""

    for raw_line in raw_output.splitlines():
        stripped = raw_line.rstrip()
        if not stripped.startswith("│"):
            continue
        parts = [part.strip() for part in stripped.split("│")[1:-1]]
        if len(parts) < 3:
            continue
        name_cell, type_cell, location_cell = parts[:3]
        if name_cell == "Name" and type_cell == "Type":
            continue
        if name_cell or type_cell:
            flush_current()
            current_name = name_cell
            current_type = type_cell
            current_location = location_cell
            continue
        if location_cell:
            current_location += location_cell

    flush_current()
    return matches


def _parse_cgc_analyze_output(raw_output: str) -> list[_AnalyzeMatch]:
    """Parse a cgc analyze rich table into compact repo-local matches."""
    headers: list[str] = []
    matches: list[_AnalyzeMatch] = []
    current_values: list[str] | None = None

    def flush_current() -> None:
        nonlocal current_values
        if not headers or current_values is None:
            return
        row = dict(zip(headers, current_values, strict=False))
        location = row.get("Location", "")
        path, line_num = _parse_find_location(location)
        match = _AnalyzeMatch(
            columns=row,
            location=location,
            path=path,
            line_num=line_num,
        )
        if _repo_local_find_path(match.path):
            matches.append(match)
        current_values = None

    for raw_line in raw_output.splitlines():
        stripped = raw_line.rstrip()
        if not stripped.startswith("│"):
            continue
        parts = [part.strip() for part in stripped.split("│")[1:-1]]
        if len(parts) < 2:
            continue
        if not headers:
            headers = parts
            continue
        if current_values is None:
            current_values = parts
            continue
        if any(parts[index] for index in range(len(parts) - 1)):
            flush_current()
            current_values = parts
            continue
        current_values[-1] += parts[-1]

    flush_current()
    return [match for match in matches if match.location]


def _render_resolution_extras(
    pattern: str,
    vector_candidates: list[_VectorMatch],
    vector_match: _VectorMatch | None,
    *,
    show_shortlist: bool,
    inline_body: bool,
) -> None:
    """Render optional shortlist/body output after anchor resolution."""
    if vector_candidates and show_shortlist:
        _render_candidate_shortlist(vector_candidates, pattern)
    if inline_body and vector_match is not None:
        _render_candidate_body(vector_match)


def _context_resolution_from_cached_entry(
    entry: dict[str, object],
    *,
    candidate_index: int,
    show_shortlist_hint: bool,
) -> tuple[_AnchorResolution | None, bool]:
    """Restore a cached context result set and re-select the requested candidate index."""
    matches_raw = entry.get("matches")
    if not isinstance(matches_raw, list):
        return None, False
    vector_candidates = [
        match
        for item in matches_raw
        if (match := _deserialize_vector_match(item)) is not None
    ]
    vector_match, candidate_error = _select_semantic_anchor_candidate(vector_candidates, candidate_index)
    if candidate_error is not None:
        print(f"ERROR: {candidate_error}", file=sys.stderr)
        if show_shortlist_hint and vector_candidates:
            print("Hint: re-run with --show-shortlist to inspect ranked candidates.", file=sys.stderr)
        return None, True
    line_num = vector_match.line_num if vector_match is not None else None
    rerank_debug = _deserialize_rerank_debug(entry.get("rerank_debug"))
    return _AnchorResolution(
        vector_candidates=vector_candidates,
        vector_match=vector_match,
        strict_status=0,
        line_num=line_num,
        rerank_debug=rerank_debug,
    ), True


def _find_matches_from_cached_entry(entry: dict[str, object]) -> list[_FindMatch] | None:
    """Restore cached find results when the scratchpad entry has the expected shape."""
    matches_raw = entry.get("matches")
    if not isinstance(matches_raw, list):
        return None
    matches: list[_FindMatch] = []
    for item in matches_raw:
        match = _deserialize_find_match(item)
        if match is None:
            return None
        matches.append(match)
    return matches


def _analyze_matches_from_cached_entry(entry: dict[str, object]) -> list[_AnalyzeMatch] | None:
    """Restore cached analyze results when the scratchpad entry has the expected shape."""
    matches_raw = entry.get("matches")
    if not isinstance(matches_raw, list):
        return None
    matches: list[_AnalyzeMatch] = []
    for item in matches_raw:
        match = _deserialize_analyze_match(item)
        if match is None:
            return None
        matches.append(match)
    return matches


def _resolve_pattern_anchor_with_scratchpad(
    parsed: _ContextArgs,
    *,
    request_scope: _ContextQueryScope,
    normalized_pattern: str,
) -> tuple[_AnchorResolution | None, bool, str]:
    """Resolve a context request from session scratchpad first, then backend search."""
    session_id = _read_code_session_id()
    signature = codegraph_current_edit_signature()
    query_payload = _context_query_payload(parsed, request_scope, normalized_pattern)
    cache_key = _search_cache_key("context", query_payload)
    cached_entry = _load_cached_search_entry(session_id, cache_key, signature=signature)
    if cached_entry is not None:
        cached_resolution, handled = _context_resolution_from_cached_entry(
            cached_entry,
            candidate_index=parsed.candidate_index,
            show_shortlist_hint=True,
        )
        if handled:
            return cached_resolution, True, signature

    resolution = _resolve_pattern_anchor(
        parsed.file_path,
        parsed.pattern,
        normalized_pattern,
        candidate_index=parsed.candidate_index,
        allow_fallback=parsed.allow_fallback,
        show_shortlist_hint=True,
        content_type=parsed.content_type,
        request_scope=request_scope,
    )
    if resolution is not None:
        _store_search_scratchpad_entry(
            session_id,
            cache_key,
            command="context",
            query_payload=query_payload,
            signature=signature,
            matches_payload=[_serialize_vector_match(match) for match in resolution.vector_candidates],
            rerank_debug_payload=(
                _serialize_rerank_debug(resolution.rerank_debug) if resolution.rerank_debug is not None else None
            ),
        )
    return resolution, False, signature


def read_code_context(argv: list[str], *, verbose: bool = False) -> int:
    """Resolve an anchor and return compact semantic match metadata."""
    started_at = time.perf_counter()
    parsed = _parse_context_args(argv)
    if parsed is None:
        return 1

    request_scope = _classify_context_query_scope(parsed)
    preflight_path = parsed.file_path or Path.cwd()
    if not _refresh_indexes_for_read(
        preflight_path,
        verbose=verbose,
        request_is_scoped=request_scope.is_scoped,
    ):
        return 1
    normalized_pattern = normalize_symbol_pattern(parsed.pattern)
    resolution, cache_hit, signature = _resolve_pattern_anchor_with_scratchpad(
        parsed,
        request_scope=request_scope,
        normalized_pattern=normalized_pattern,
    )
    if resolution is None:
        _append_search_metadata_event(
            command="context",
            subcommand=None,
            query=parsed.pattern,
            query_shape="scoped" if request_scope.is_scoped else "broad",
            file_path=parsed.file_path,
            hit_count=0,
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return 1
    vector_candidates = resolution.vector_candidates
    vector_match = resolution.vector_match
    line_num = resolution.line_num

    if line_num is None:
        print(f"ERROR: No match found for '{parsed.pattern}'", file=sys.stderr)
        _append_search_metadata_event(
            command="context",
            subcommand=None,
            query=parsed.pattern,
            query_shape="scoped" if request_scope.is_scoped else "broad",
            file_path=parsed.file_path,
            hit_count=len(vector_candidates),
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return 1

    if vector_match is None:
        print("ERROR: No semantic match available", file=sys.stderr)
        _append_search_metadata_event(
            command="context",
            subcommand=None,
            query=parsed.pattern,
            query_shape="scoped" if request_scope.is_scoped else "broad",
            file_path=parsed.file_path,
            hit_count=len(vector_candidates),
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return 1

    has_more_candidates = len(vector_candidates) > parsed.candidate_index + 1
    _render_compact_match(vector_match, has_more_candidates=has_more_candidates)
    _render_resolution_extras(
        parsed.pattern,
        vector_candidates,
        vector_match,
        show_shortlist=parsed.show_shortlist,
        inline_body=parsed.inline_body,
    )
    if parsed.show_rerank and resolution.rerank_debug is not None:
        _render_rerank_debug(
            resolution.rerank_debug,
            result_source="scratchpad" if cache_hit else "backend",
        )

    if parsed.inline_body:
        _render_read_context_inline_body(vector_match, line_num, parsed.context)

    _append_search_metadata_event(
        command="context",
        subcommand=None,
        query=parsed.pattern,
        query_shape="scoped" if request_scope.is_scoped else "broad",
        file_path=parsed.file_path,
        hit_count=len(vector_candidates),
        selected_candidate_index=parsed.candidate_index,
        cache_hit=cache_hit,
        result_source="scratchpad" if cache_hit else "backend",
        elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
        signature=signature,
    )
    return 0


def read_code_window(argv: list[str], *, verbose: bool = False) -> int:
    """Reject direct window reads and force semantic-first discovery."""
    _ = (argv, verbose)
    print(
        "ERROR: window mode is disabled. Use read_code.py context/find/analyze instead.",
        file=sys.stderr,
    )
    return 1


def read_code_headings(argv: list[str], *, verbose: bool = False) -> int:
    """List markdown headings with line numbers."""
    if not argv:
        print("ERROR: headings mode requires a file path", file=sys.stderr)
        return 1
    file_path = Path(argv[0])
    if not file_path.is_file():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 1
    if not _is_markdown(file_path):
        print(f"ERROR: headings mode is only supported for markdown files: {file_path}", file=sys.stderr)
        return 1

    if not _refresh_indexes_for_read(file_path, verbose=verbose):
        return 1

    headings = _markdown_heading_lines(file_path)
    for line_num, text in headings:
        print(f"{line_num:6}\t{text}")
    return 0


def read_code_history(argv: list[str], *, verbose: bool = False) -> int:
    """Render bounded recent-event or aggregate stats views for search metadata."""
    _ = verbose
    parsed = _parse_history_args(argv)
    if parsed is None:
        return 1
    events = _load_search_metadata_events()
    if parsed.command == "recent":
        _render_history_recent(events, limit=parsed.limit)
        return 0
    _render_history_stats(events)
    return 0


def read_code_analyze(argv: list[str], *, verbose: bool = False) -> int:
    """Run cgc analyze and present repo-local table rows as a stepwise shortlist."""
    started_at = time.perf_counter()
    parsed = _parse_analyze_args(argv)
    if parsed is None:
        return 1

    signature = codegraph_current_edit_signature()
    query = " ".join(parsed.forwarded_args)
    query_payload = _analyze_query_payload(parsed)
    session_id = _read_code_session_id()
    cache_key = _search_cache_key("analyze", query_payload)
    matches: list[_AnalyzeMatch] | None = None
    raw_output = ""
    cache_hit = False

    if not verbose:
        cached_entry = _load_cached_search_entry(session_id, cache_key, signature=signature)
        if cached_entry is not None:
            matches = _analyze_matches_from_cached_entry(cached_entry)
            cache_hit = matches is not None

    result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    if matches is None:
        init_codegraph_env()
        cmd = ["uv", "run", "cgc", "analyze", parsed.command] + parsed.forwarded_args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=_cgc_capture_env(),
        )
        raw_output = ((result.stdout or "") + (result.stderr or "")).rstrip()

        if result.returncode != 0 or "--help" in parsed.forwarded_args:
            if raw_output:
                print(raw_output)
            return result.returncode

        matches = _parse_cgc_analyze_output(raw_output)
        _store_search_scratchpad_entry(
            session_id,
            cache_key,
            command="analyze",
            query_payload=query_payload,
            signature=signature,
            matches_payload=[_serialize_analyze_match(match) for match in matches],
        )

    assert matches is not None
    if not matches:
        if verbose and raw_output:
            print("# raw_cgc_output")
            print(raw_output)
        else:
            print(f"analyze_command: {parsed.command}")
            print(f"query: {query}")
            print("match_count: 0")
            print("# no parsed analyze matches; rerun with --verbose for raw cgc output")
        _append_search_metadata_event(
            command="analyze",
            subcommand=parsed.command,
            query=query,
            query_shape=parsed.command,
            file_path=None,
            hit_count=0,
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return result.returncode

    if parsed.candidate_index < 0 or parsed.candidate_index >= len(matches):
        print(
            f"ERROR: candidate index {parsed.candidate_index} is out of range (available: 0..{len(matches) - 1})",
            file=sys.stderr,
        )
        print("Hint: re-run with --show-shortlist to inspect ranked matches.", file=sys.stderr)
        _append_search_metadata_event(
            command="analyze",
            subcommand=parsed.command,
            query=query,
            query_shape=parsed.command,
            file_path=None,
            hit_count=len(matches),
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return 1

    if parsed.show_shortlist:
        _render_analyze_shortlist(matches, parsed.command, query)
    _render_compact_analyze_match(
        matches[parsed.candidate_index],
        command=parsed.command,
        query=query,
        candidate_index=parsed.candidate_index,
        total_matches=len(matches),
        has_more_candidates=parsed.candidate_index < len(matches) - 1,
    )
    if verbose and raw_output:
        print("# raw_cgc_output")
        print(raw_output)
    _append_search_metadata_event(
        command="analyze",
        subcommand=parsed.command,
        query=query,
        query_shape=parsed.command,
        file_path=None,
        hit_count=len(matches),
        selected_candidate_index=parsed.candidate_index,
        cache_hit=cache_hit,
        result_source="scratchpad" if cache_hit else "backend",
        elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
        signature=signature,
    )
    return result.returncode


def read_code_find(argv: list[str], *, verbose: bool = False) -> int:
    """Run cgc find and present repo-local matches as a stepwise shortlist."""
    started_at = time.perf_counter()
    parsed = _parse_find_args(argv)
    if parsed is None:
        return 1

    signature = codegraph_current_edit_signature()
    query = " ".join(parsed.forwarded_args)
    query_payload = _find_query_payload(parsed)
    session_id = _read_code_session_id()
    cache_key = _search_cache_key("find", query_payload)
    matches: list[_FindMatch] | None = None
    raw_output = ""
    cache_hit = False

    if not verbose:
        cached_entry = _load_cached_search_entry(session_id, cache_key, signature=signature)
        if cached_entry is not None:
            matches = _find_matches_from_cached_entry(cached_entry)
            cache_hit = matches is not None

    result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    if matches is None:
        init_codegraph_env()
        cmd = ["uv", "run", "cgc", "find", parsed.command] + parsed.forwarded_args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=_cgc_capture_env(),
        )
        raw_output = ((result.stdout or "") + (result.stderr or "")).rstrip()

        if result.returncode != 0 or "--help" in parsed.forwarded_args:
            if raw_output:
                print(raw_output)
            return result.returncode

        matches = _parse_cgc_find_output(raw_output)
        _store_search_scratchpad_entry(
            session_id,
            cache_key,
            command="find",
            query_payload=query_payload,
            signature=signature,
            matches_payload=[_serialize_find_match(match) for match in matches],
        )

    assert matches is not None
    if not matches:
        if verbose and raw_output:
            print("# raw_cgc_output")
            print(raw_output)
        else:
            print(f"find_command: {parsed.command}")
            print(f"query: {query}")
            print("match_count: 0")
            print("# no parsed find matches; rerun with --verbose for raw cgc output")
        _append_search_metadata_event(
            command="find",
            subcommand=parsed.command,
            query=query,
            query_shape=parsed.command,
            file_path=None,
            hit_count=0,
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return result.returncode

    if parsed.candidate_index < 0 or parsed.candidate_index >= len(matches):
        print(
            f"ERROR: candidate index {parsed.candidate_index} is out of range (available: 0..{len(matches) - 1})",
            file=sys.stderr,
        )
        print("Hint: re-run with --show-shortlist to inspect ranked matches.", file=sys.stderr)
        _append_search_metadata_event(
            command="find",
            subcommand=parsed.command,
            query=query,
            query_shape=parsed.command,
            file_path=None,
            hit_count=len(matches),
            selected_candidate_index=parsed.candidate_index,
            cache_hit=cache_hit,
            result_source="scratchpad" if cache_hit else "backend",
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            signature=signature,
        )
        return 1

    if parsed.show_shortlist:
        _render_find_shortlist(
            matches,
            parsed.command,
            query,
            limit=_find_shortlist_limit(parsed.command),
        )
    _render_compact_find_match(
        matches[parsed.candidate_index],
        command=parsed.command,
        query=query,
        candidate_index=parsed.candidate_index,
        total_matches=len(matches),
        has_more_candidates=parsed.candidate_index < len(matches) - 1,
    )
    if verbose and raw_output:
        print("# raw_cgc_output")
        print(raw_output)
    _append_search_metadata_event(
        command="find",
        subcommand=parsed.command,
        query=query,
        query_shape=parsed.command,
        file_path=None,
        hit_count=len(matches),
        selected_candidate_index=parsed.candidate_index,
        cache_hit=cache_hit,
        result_source="scratchpad" if cache_hit else "backend",
        elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
        signature=signature,
    )
    return result.returncode


def _print_usage() -> None:
    print("Usage:")
    print(
        "  read_code context <file_path> <symbol_or_pattern> [--inline-body] [...]"
    )
    print(
        "  read_code headings <markdown_file>"
    )
    print(
        "  read_code analyze <command> <symbol> [--show-shortlist] [--next-candidate] [...]"
    )
    print(
        "  read_code find    <command> <pattern> [--show-shortlist] [--next-candidate] [...]"
    )
    print(
        "  read_code history <recent [limit] | stats>"
    )
    print("  --verbose / -v    show detailed vector preflight diagnostics")
    print("  --show-rerank     show opt-in rerank diagnostics for context results")
    print("\nModes:")
    print("  context:  Resolve anchor semantically and show metadata (opt-in body/lines).")
    print("  headings: List markdown headings with line numbers.")
    print("  analyze:  Graph discovery via CodeGraph with one-match-at-a-time shortlist stepping when table output is available.")
    print("  find:     Structural search via CodeGraph with one-match-at-a-time shortlist stepping.")
    print("  history:  Inspect bounded recent search events and aggregate cache/timing stats.")


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read_code.py mode routing."""
    import os
    from pathlib import Path

    if not os.environ.get("READ_CODE_SESSION_ID"):
        os.environ["READ_CODE_SESSION_ID"] = _read_code_session_id()

    if not os.environ.get("UV_CACHE_DIR"):
        repo_root = Path(__file__).parent.parent
        os.environ["UV_CACHE_DIR"] = str(repo_root / ".codegraphcontext" / ".uv-cache")

    argv, verbose = _split_verbose_flag(argv)
    if len(argv) < 2:
        _print_usage()
        return 1

    mode = argv[0]
    args = argv[1:]
    if mode == "context":
        return read_code_context(args, verbose=verbose)
    if mode == "window":
        return read_code_window(args, verbose=verbose)
    if mode == "headings":
        return read_code_headings(args, verbose=verbose)
    if mode == "analyze":
        return read_code_analyze(args, verbose=verbose)
    if mode == "find":
        return read_code_find(args, verbose=verbose)
    if mode == "history":
        return read_code_history(args, verbose=verbose)

    print(f"ERROR: Unknown mode '{mode}'. Use: context | window | headings | analyze | find | history", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
