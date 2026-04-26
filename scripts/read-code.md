# read_code references: safer follow-up commands, pagination, and count metadata

## Summary

This change improves `read_code references` so its output is safer for agent follow-up and more honest about result counts. The references mode now supports explicit section pagination, includes offset and next-offset metadata, reports graph-native totals for callers/callees, and avoids treating codegraph UIDs as vector read IDs.

## What changed

### 1. Added `--offset=N` support for explicit reference sections

`read_code references` now accepts:

    read_code references <file_path> <target> --kind=<section> --offset=N

Supported paginated sections:

    callers
    callees
    reads
    writes
    variables
    tests
    ambiguous_mentions

`--offset` is intentionally limited to explicit section reads. It is rejected for `--kind=default` and `--kind=all` because those outputs contain multiple sections, so a single offset would be ambiguous.

### 2. Added pagination metadata

For paginated section output, references now prints:

    offset=N
    returned=N
    total=N
    truncated=true|false
    next_offset=N

`next_offset` is printed only when more results are available.

This gives follow-up agents a deterministic way to continue:

    read_code references <file> <target> --kind=callers --offset=<next_offset>

### 3. Added count queries for graph-native callers/callees totals

For `--kind=callers` and `--kind=callees`, the command now runs direct Cypher count queries that count distinct caller/callee nodes. This makes paginated `total` values for callers/callees graph-derived rather than capped by the returned row list.

### 4. Added `_reference_query_count()`

A new helper wraps direct Cypher count results and normalizes the first `total` field into an integer:

    def _reference_query_count(query: str) -> tuple[int | None, str | None]:

It handles integer-like payloads and reports malformed count payloads as errors.

### 5. Added `_slice_reference_hits()`

A new helper centralizes offset pagination behavior:

    def _slice_reference_hits(
        hits: list[_ReferenceHit],
        offset: int,
        max_items: int,
        *,
        total: int | None = None,
    ) -> tuple[list[_ReferenceHit], int, int, bool, int | None]:

It returns:

    page_hits
    returned
    total
    truncated
    next_offset

### 6. Updated reference section rendering

`_render_reference_section()` now accepts optional explicit metadata:

    total
    returned
    truncated

This lets paginated sections render the real section total instead of only `len(hits)`.

### 7. Added `ambiguous_mentions` as a first-class `--kind`

`ambiguous_mentions` is now accepted in the references kind list:

    default|callers|callees|reads|writes|variables|tests|ambiguous_mentions|all

This lets agents page ambiguous source hits explicitly without relying on `--kind=all`.

### 8. Preserved graph UID separation from vector read IDs

The output target table now distinguishes:

    id         vector-style unit id used by read
    graph_uid diagnostic codegraph UID

Follow-up `read` commands still use vector-style unit IDs only when they are actually vector-style IDs. Codegraph UIDs are not used as read targets.

## Behavior notes

For explicit paginated sections, the output includes the definition plus the selected section page:

    # target
    ...
    # definition returned=1 total=1
    ...
    # callers returned=20 total=54
    ...
    next_offset=20

For non-paginated modes (`default`, `all`), behavior remains compact and section-based. `truncated` is still computed only across visible sections.

## Remaining limitation

Only callers/callees have true graph-native total counts right now.

For `reads`, `writes`, `variables`, `tests`, and `ambiguous_mentions`, totals are still derived from the currently collected hit list, which may be bounded upstream by the source/variable query cap. A later change should make those sections graph-native too, or explicitly mark their counts as bounded.