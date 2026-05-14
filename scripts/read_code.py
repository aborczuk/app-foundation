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

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from read_code_health import (
    REPO_ROOT,
    _clear_vector_runtime_note,
    _command_exists,
    _consume_vector_runtime_note,
    _find_markdown_section_end,
    _markdown_heading_lines,
    _read_code_session_id,
    _refresh_indexes_for_read,
    _resolve_markdown_anchor_fallback,
    _resolve_markdown_anchor_vector,
    _run_command_capture,
    _set_vector_runtime_note,
    _vector_command_env,
    _vector_indexer_cmd,
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
class _AnchorResolution:
    """Shared anchor resolution result for context and window read entrypoints."""

    vector_candidates: list[_VectorMatch]
    vector_match: _VectorMatch | None
    strict_status: int
    line_num: int | None


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

    return sorted(matches, key=lambda match: _vector_anchor_rank(match, allow_test_files=allow_test_files), reverse=True)[:5]


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
    )[:5]
    vector_match, candidate_error = _select_semantic_anchor_candidate(vector_candidates, candidate_index)
    if candidate_error is not None:
        print(f"ERROR: {candidate_error}", file=sys.stderr)
        if show_shortlist_hint and vector_candidates:
            print("Hint: re-run with --show-shortlist to inspect ranked candidates.", file=sys.stderr)
        return vector_candidates, None, False
    return vector_candidates, vector_match, True


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
            )
        return None

    vector_candidates, vector_match, selection_ok = _query_semantic_anchor_candidate(
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

            refreshed_candidates, refreshed_match, selection_ok = _query_semantic_anchor_candidate(
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



def read_code_context(argv: list[str], *, verbose: bool = False) -> int:
    """Resolve an anchor and return compact semantic match metadata."""
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
    if resolution is None:
        return 1
    vector_candidates = resolution.vector_candidates
    vector_match = resolution.vector_match
    line_num = resolution.line_num

    if line_num is None:
        print(f"ERROR: No match found for '{parsed.pattern}'", file=sys.stderr)
        return 1

    if vector_match is None:
        print("ERROR: No semantic match available", file=sys.stderr)
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

    if parsed.inline_body:
        _render_read_context_inline_body(vector_match, line_num, parsed.context)

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


def read_code_analyze(argv: list[str], *, verbose: bool = False) -> int:
    """Run cgc analyze and present repo-local table rows as a stepwise shortlist."""
    parsed = _parse_analyze_args(argv)
    if parsed is None:
        return 1

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
    if not matches:
        if verbose and raw_output:
            print("# raw_cgc_output")
            print(raw_output)
        else:
            query = " ".join(parsed.forwarded_args)
            print(f"analyze_command: {parsed.command}")
            print(f"query: {query}")
            print("match_count: 0")
            print("# no parsed analyze matches; rerun with --verbose for raw cgc output")
        return result.returncode

    if parsed.candidate_index < 0 or parsed.candidate_index >= len(matches):
        print(
            f"ERROR: candidate index {parsed.candidate_index} is out of range (available: 0..{len(matches) - 1})",
            file=sys.stderr,
        )
        print("Hint: re-run with --show-shortlist to inspect ranked matches.", file=sys.stderr)
        return 1

    query = " ".join(parsed.forwarded_args)
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
    return result.returncode


def read_code_find(argv: list[str], *, verbose: bool = False) -> int:
    """Run cgc find and present repo-local matches as a stepwise shortlist."""
    parsed = _parse_find_args(argv)
    if parsed is None:
        return 1

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
    if not matches:
        if verbose and raw_output:
            print("# raw_cgc_output")
            print(raw_output)
        else:
            query = " ".join(parsed.forwarded_args)
            print(f"find_command: {parsed.command}")
            print(f"query: {query}")
            print("match_count: 0")
            print("# no parsed find matches; rerun with --verbose for raw cgc output")
        return result.returncode

    if parsed.candidate_index < 0 or parsed.candidate_index >= len(matches):
        print(
            f"ERROR: candidate index {parsed.candidate_index} is out of range (available: 0..{len(matches) - 1})",
            file=sys.stderr,
        )
        print("Hint: re-run with --show-shortlist to inspect ranked matches.", file=sys.stderr)
        return 1

    query = " ".join(parsed.forwarded_args)
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
    print("  --verbose / -v    show detailed vector preflight diagnostics")
    print("\nModes:")
    print("  context:  Resolve anchor semantically and show metadata (opt-in body/lines).")
    print("  headings: List markdown headings with line numbers.")
    print("  analyze:  Graph discovery via CodeGraph with one-match-at-a-time shortlist stepping when table output is available.")
    print("  find:     Structural search via CodeGraph with one-match-at-a-time shortlist stepping.")


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

    print(f"ERROR: Unknown mode '{mode}'. Use: context | window | headings | analyze | find", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
