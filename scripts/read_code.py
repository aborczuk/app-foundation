#!/usr/bin/env python3
"""Python entrypoint for code discovery and bounded function/class reads with semantic-first anchoring.

Code file read-efficiency contract:
- Use this helper for code files (Python, shell, YAML, and related).
- Prefer the helper over raw file reads so the read stays bounded by semantic intent.
- Use semantic search first to locate the right anchor, then retrieve a bounded context window.
- Two modes: context (semantic search + window), window (direct line-range read).
- If you need only the relevant function body, pass the function name rather than scanning the whole file.
- If semantic confidence is weak, step through candidates before falling back to exact symbol matching.

How to use:
1. Invoke the Python entrypoint directly: ``uv run python scripts/read_code.py <mode> [args]``.
2. Use **context mode** when the target is a natural-language query or symbol name:
   - ``uv run python scripts/read_code.py context "<query>"`` — semantic search + bounded window.
   - ``uv run python scripts/read_code.py context "<symbol>" --path <file>`` — scope to a specific file.
   - ``uv run python scripts/read_code.py context "<symbol>" --inline-body`` — get full function body.
   - ``uv run python scripts/read_code.py context "<symbol>" --next-candidate`` — step ranked candidates.
3. Use **window mode** when you know the exact file and line range:
   - ``uv run python scripts/read_code.py window <file> <start_line> [line_count]`` — direct window read.
4. Let the helper anchor the seam semantically and print only the relevant window.

Validation:
- If the symbol does not resolve, the helper prints a clear not-found error and shows ranked candidates.
- The helper keeps the read window bounded (default 60 lines, max 80 per settings).
- Confidence scores guide candidate selection when multiple matches exist.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from read_code_health import (
    CODEGRAPH_DB_DIR,
    REPO_ROOT,
    _clear_vector_runtime_note,
    _command_exists,
    _consume_vector_runtime_note,
    _find_markdown_section_end,
    _markdown_heading_lines,
    _refresh_indexes_for_read,
    _resolve_markdown_anchor_fallback,
    _resolve_markdown_anchor_vector,
    _run_command_capture,
    _set_vector_runtime_note,
    _vector_command_env,
    _vector_indexer_cmd,
    codegraph_health_status,
    codegraph_refresh_if_needed,
    codegraph_supports_file,
    init_codegraph_env,
)

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


@dataclass(frozen=True)
class _WindowArgs:
    """Parsed and validated arguments for read_code_window."""

    file_path: Path
    start_line: int
    line_count: int
    pattern: str
    use_hud_fast_path: bool
    allow_fallback: bool






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
    safe_index = SCRIPT_DIR / "cgc_safe_index.sh"
    has_self_heal_pattern = "Database Connection Error" in output or "No index metadata" in output
    if has_self_heal_pattern and safe_index.is_file() and os.access(safe_index, os.X_OK):
        _run_command_capture([str(safe_index), str(path)])
        second = _run_command_capture(cmd)
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


def _vector_anchor_rank(match: _VectorMatch) -> tuple[int]:
    return (match.cosine_similarity,)


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

    return sorted(matches, key=_vector_anchor_rank, reverse=True)[:5]


def _vector_find_candidates(
    file_path: Path | None,
    raw_pattern: str,
    normalized_pattern: str,
    scope: str,
) -> list[_VectorMatch]:
    """Return the bounded shortlist for a query using raw and normalized probes."""
    _clear_vector_runtime_note()
    candidates: list[_VectorMatch] = []
    if raw_pattern:
        candidates = _vector_query_candidates(file_path, raw_pattern, normalized_pattern, scope)
    if not candidates and normalized_pattern and normalized_pattern != raw_pattern:
        candidates = _vector_query_candidates(file_path, normalized_pattern, normalized_pattern, scope)
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
    print(f"# shortlist for: {query}")
    print(
        "# cosine_similarity\tfile_path\tunit_id\tline_num-line_end\ttype\tbody\tdocstring\traw"
    )
    for candidate in candidates[:5]:
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


def _query_semantic_anchor_candidate(
    file_path: Path | None,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    show_shortlist_hint: bool,
) -> tuple[list[_VectorMatch], _VectorMatch | None, bool]:
    """Query ranked candidates and select a semantic anchor with standardized error handling."""
    code_candidates = _vector_find_candidates(file_path, pattern, normalized_pattern, "code")
    markdown_candidates = _vector_find_candidates(file_path, pattern, normalized_pattern, "markdown")
    vector_candidates = sorted(
        code_candidates + markdown_candidates,
        key=_vector_anchor_rank,
        reverse=True,
    )[:5]
    vector_match, candidate_error = _select_semantic_anchor_candidate(vector_candidates, candidate_index)
    if candidate_error is not None:
        print(f"ERROR: {candidate_error}", file=sys.stderr)
        if show_shortlist_hint and vector_candidates:
            print("Hint: re-run with --show-shortlist to inspect ranked candidates.", file=sys.stderr)
        return vector_candidates, None, False
    return vector_candidates, vector_match, True


def _resolve_pattern_anchor(
    file_path: Path | None,
    pattern: str,
    normalized_pattern: str,
    *,
    candidate_index: int,
    allow_fallback: bool,
    show_shortlist_hint: bool,
) -> _AnchorResolution | None:
    if _is_markdown(file_path):
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
    )
    if not selection_ok:
        return None

    line_num: int | None = None
    if vector_match is not None:
        line_num = vector_match.line_num
    elif file_path is not None:
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
            )
            if not selection_ok:
                return None
            if refreshed_candidates:
                vector_candidates = refreshed_candidates
                vector_match = refreshed_match
                if vector_match is not None:
                    line_num = vector_match.line_num

    if file_path is not None:
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
    expect_candidate_index = False
    expect_path = False

    first_arg = argv[0]
    first_is_file = False
    try:
        first_path = Path(first_arg)
        first_is_file = first_path.is_file()
    except (OSError, ValueError):
        pass

    if first_is_file and len(argv) >= 2:
        # Old syntax: read_code context <file_path> <query> [...]
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
    )


def _parse_window_args(argv: list[str]) -> _WindowArgs | None:
    """Parse and validate read_code_window arguments."""
    if len(argv) < 2:
        print(
            "ERROR: read_code_window requires: <file_path> <start_line> [line_count]",
            file=sys.stderr,
        )
        return None

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
            return None

    validated = _validate_file_and_positive_int(file_arg, start_line_raw, value_label="start_line")
    if validated is None:
        return None
    file_path, start_line = validated

    line_count_raw = str(line_count)
    if not line_count_raw.isdigit() or int(line_count_raw, 10) <= 0:
        print(f"ERROR: line_count must be a positive integer: {line_count}", file=sys.stderr)
        return None
    line_count_value = int(line_count_raw, 10)
    if line_count_value > READ_CODE_MAX_LINES:
        print(f"ERROR: line_count exceeds max ({READ_CODE_MAX_LINES}): {line_count_value}", file=sys.stderr)
        return None

    return _WindowArgs(
        file_path=file_path,
        start_line=start_line,
        line_count=line_count_value,
        pattern=pattern,
        use_hud_fast_path=hud_flag,
        allow_fallback=allow_fallback,
    )


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



def read_code_context(argv: list[str]) -> int:
    """Resolve an anchor and return compact semantic match metadata."""
    parsed = _parse_context_args(argv)
    if parsed is None:
        return 1

    preflight_path = parsed.file_path or Path.cwd()
    if not _refresh_indexes_for_read(preflight_path):
        return 1
    normalized_pattern = normalize_symbol_pattern(parsed.pattern)
    resolution = _resolve_pattern_anchor(
        parsed.file_path,
        parsed.pattern,
        normalized_pattern,
        candidate_index=parsed.candidate_index,
        allow_fallback=parsed.allow_fallback,
        show_shortlist_hint=True,
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
        start = 1
        end = 1
        if _is_markdown(vector_match.file_path):
            start = line_num
            end = _find_markdown_section_end(vector_match.file_path, line_num)
        else:
            pre_lines, post_lines = _split_context_window(parsed.context)
            start = max(1, line_num - pre_lines)
            end = line_num + post_lines
        _render_numbered_window(vector_match.file_path, start, end)

    return 0


def read_code_window(argv: list[str]) -> int:
    """Print a numbered bounded window and ignore out-of-window semantic anchors."""
    parsed = _parse_window_args(argv)
    if parsed is None:
        return 1

    if parsed.pattern:
        if not _refresh_indexes_for_read(parsed.file_path):
            return 1
        normalized_pattern = normalize_symbol_pattern(parsed.pattern)
        resolution = _resolve_pattern_anchor(
            parsed.file_path,
            parsed.pattern,
            normalized_pattern,
            candidate_index=0,
            allow_fallback=parsed.allow_fallback,
            show_shortlist_hint=False,
        )
        if resolution is None:
            return 1
        line_num = resolution.line_num

        if line_num is None:
            print(f"ERROR: No match found for '{parsed.pattern}'", file=sys.stderr)
            return 1

    end_line = parsed.start_line + parsed.line_count - 1
    _render_numbered_window(parsed.file_path, parsed.start_line, end_line)
    return 0


def read_code_headings(argv: list[str]) -> int:
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

    if not _refresh_indexes_for_read(file_path):
        return 1

    headings = _markdown_heading_lines(file_path)
    for line_num, text in headings:
        print(f"{line_num:6}\t{text}")
    return 0


def read_code_analyze(argv: list[str]) -> int:
    """Proxy to codegraph (cgc) analyze commands."""
    if not argv:
        print("ERROR: analyze mode requires a command (e.g. callers, deps)", file=sys.stderr)
        return 1
    
    init_codegraph_env()
    cmd = ["uv", "run", "cgc", "analyze"] + argv
    return subprocess.run(cmd, check=False).returncode


def read_code_find(argv: list[str]) -> int:
    """Proxy to codegraph (cgc) find commands."""
    if not argv:
        print("ERROR: find mode requires a command (e.g. name, pattern)", file=sys.stderr)
        return 1
    
    init_codegraph_env()
    cmd = ["uv", "run", "cgc", "find"] + argv
    return subprocess.run(cmd, check=False).returncode


def _print_usage() -> None:
    print("Usage:")
    print(
        "  read_code context <file_path> <symbol_or_pattern> [--inline-body] [...]"
    )
    print(
        "  read_code window  <file_path> <start_line> [line_count]"
    )
    print(
        "  read_code headings <markdown_file>"
    )
    print(
        "  read_code analyze <command> <symbol> [...]"
    )
    print(
        "  read_code find    <command> <pattern> [...]"
    )
    print("\nModes:")
    print("  context:  Resolve anchor semantically and show metadata (opt-in body/lines).")
    print("  window:   Show a raw numbered line window.")
    print("  headings: List markdown headings with line numbers.")
    print("  analyze:  Graph discovery via CodeGraph (callers, deps, dead-code, etc.).")
    print("  find:     Structural search via CodeGraph (name, pattern, type, etc.).")


def main(argv: list[str]) -> int:
    """CLI entrypoint compatible with read-code.sh mode routing."""
    import os
    from pathlib import Path

    if not os.environ.get("READ_CODE_SESSION_ID"):
        session_id = (
            os.environ.get("CODEX_SESSION_ID")
            or os.environ.get("TERM_SESSION_ID")
            or str(os.getppid())
            or str(os.getpid())
        )
        os.environ["READ_CODE_SESSION_ID"] = session_id

    if not os.environ.get("UV_CACHE_DIR"):
        repo_root = Path(__file__).parent.parent
        os.environ["UV_CACHE_DIR"] = str(repo_root / ".codegraphcontext" / ".uv-cache")

    if len(argv) < 2:
        _print_usage()
        return 1

    mode = argv[0]
    args = argv[1:]
    if mode == "context":
        return read_code_context(args)
    if mode == "window":
        return read_code_window(args)
    if mode == "headings":
        return read_code_headings(args)
    if mode == "analyze":
        return read_code_analyze(args)
    if mode == "find":
        return read_code_find(args)

    print(f"ERROR: Unknown mode '{mode}'. Use: context | window | headings | analyze | find", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
