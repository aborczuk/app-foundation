# Data Model: Codebase Vector Index

Entities, relationships, and state transitions for the local semantic index.

---

## Entities

### CodeSymbol

**Purpose**: A Python function, method, or class extracted from `src/` or `tests/` and indexed for semantic lookup.  
**Lifecycle**: discovered -> embedded -> persisted -> refreshed -> superseded

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `id` | string | Yes | Stable hash or deterministic composite key | Derived from path + symbol span + symbol name. |
| `symbol_name` | string | Yes | Non-empty | Public name of the symbol. |
| `symbol_type` | enum/string | Yes | `function`, `method`, `class` | Finite-state / constrained vocabulary. |
| `signature` | string | Yes | Can be empty only for malformed source | Parsed function/class signature. |
| `docstring` | string | Yes | Empty string allowed | Source-of-truth text; empty if absent. |
| `code_body` | string | Yes | Must preserve source order | Full symbol body used in embedding input. |
| `file_path` | string | Yes | Repo-relative path | Authoritative file location. |
| `start_line` | int | Yes | 1-based, positive | Inclusive span start. |
| `end_line` | int | Yes | >= start_line | Inclusive span end. |
| `content_hash` | string | Yes | Deterministic hash | Used for idempotent refresh and stale detection. |
| `source_commit` | string | Yes | Git SHA | Commit hash of the repository snapshot used to build the record. |
| `embedding_ref` | string | Yes | Must resolve to a persisted vector entry | Vector-store identity, not the vector itself. |

**Source of Truth**: The repository file at `file_path` and the source span identified by `start_line`/`end_line`. The stored `docstring` and `code_body` are derived from that source.

### MarkdownSection

**Purpose**: A markdown heading plus its content block extracted from `specs/`, `.claude/`, or root docs.  
**Lifecycle**: discovered -> embedded -> persisted -> refreshed -> superseded

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `id` | string | Yes | Stable hash or deterministic composite key | Derived from path + breadcrumb + content hash. |
| `file_path` | string | Yes | Repo-relative path | Markdown source location. |
| `heading_text` | string | Yes | Non-empty | Section heading text. |
| `breadcrumb` | string | Yes | Deterministic heading chain | Full nested heading path. |
| `section_depth` | int | Yes | >= 1 | Heading level depth. |
| `section_text` | string | Yes | May be truncated for preview storage | Extracted section content used for embedding input. |
| `content_preview` | string | Yes | <= 200 chars | Query-facing preview field required by the spec. |
| `content_hash` | string | Yes | Deterministic hash | Used for incremental refresh and identity. |
| `source_commit` | string | Yes | Git SHA | Repository snapshot used for the record. |
| `embedding_ref` | string | Yes | Must resolve to a persisted vector entry | Vector-store identity, not the vector itself. |

**Source of Truth**: The markdown file at `file_path` and the section text between the heading and the next same-or-higher heading.

### IndexMetadata

**Purpose**: Snapshot metadata for the last successful index build or refresh.  
**Lifecycle**: pending -> current -> stale -> rebuilding -> current

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `build_timestamp_utc` | datetime/string | Yes | ISO 8601 | Time of the last successful build. |
| `head_commit` | string | Yes | Git SHA | Commit hash captured at build time. |
| `source_root` | string | Yes | Repo-relative or absolute path | Root used for the build. |
| `symbol_count` | int | Yes | >= 0 | Count of indexed Python symbols. |
| `section_count` | int | Yes | >= 0 | Count of indexed markdown sections. |
| `embedding_model_id` | string | Yes | Non-empty | Local embedding model identifier. |
| `storage_path` | string | Yes | Stable on-disk path | Location of the active vector collection under `.codegraphcontext/db/vector-index/`. |
| `index_version` | string | Yes | Semver or monotonic version | Supports future migration. |
| `refresh_reason` | string | No | Controlled vocabulary if present | `full_build`, `watcher_update`, `post_commit_update`, or `manual_refresh`. |

**Source of Truth**: The persisted metadata record written with the active collection.

### QueryResult

**Purpose**: A ranked result returned to the caller for either a code symbol or a markdown section.  
**Lifecycle**: ephemeral -> returned -> consumed

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `result_id` | string | Yes | Must match an indexed record | Points back to `CodeSymbol` or `MarkdownSection`. |
| `result_kind` | enum/string | Yes | `code_symbol` or `markdown_section` | Controlled vocabulary. |
| `score` | float | Yes | Higher is better or lower distance normalized | Similarity score returned by the vector store. |
| `title` | string | Yes | Non-empty | Symbol name or section heading. |
| `file_path` | string | Yes | Repo-relative path | Target file for follow-up read. |
| `line_start` | int | No | 1-based if present | For code symbols. |
| `line_end` | int | No | >= line_start if present | For code symbols. |
| `breadcrumb` | string | No | Non-empty if present | For markdown sections. |
| `preview` | string | Yes | <= 200 chars recommended | Snippet to help the caller decide whether to read more. |
| `symbol_type` | string | No | Present for code symbols | Function, method, or class. |
| `source_commit` | string | Yes | Git SHA | Lets the caller detect freshness. |

**Source of Truth**: Derived from `CodeSymbol` or `MarkdownSection` plus the current vector search score.

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| IndexMetadata | CodeSymbol | describes | 1:N | One build snapshot describes many symbols. |
| IndexMetadata | MarkdownSection | describes | 1:N | One build snapshot describes many markdown sections. |
| CodeSymbol | QueryResult | appears in | 1:N | A symbol may be returned in many queries. |
| MarkdownSection | QueryResult | appears in | 1:N | A section may be returned in many queries. |

---

## State Transitions

### IndexMetadata Lifecycle

```
pending -> current -> stale -> rebuilding -> current
            ↓             ↓
          missing       failed
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| `pending` | `current` | Full build completes | All extracted units embedded and written atomically | Persist build timestamp, commit hash, counts, and model ID. |
| `current` | `stale` | Repo HEAD advances or file watcher sees a change | Current commit hash differs from HEAD or file hashes differ | Mark metadata as stale; keep the last good collection active. |
| `stale` | `rebuilding` | Refresh starts | Refresh lock acquired | Stage new writes without touching the active snapshot. |
| `rebuilding` | `current` | Refresh succeeds | All new/updated records committed atomically | Swap the staged collection into place and update metadata. |
| `rebuilding` | `failed` | Refresh fails or is interrupted | Error or timeout occurs | Retain prior collection, record failure, and leave active snapshot queryable. |

---

## Storage & Indexing

- **Primary storage**: On-disk Chroma collection under `.codegraphcontext/db/vector-index/`
- **Caching**: Optional in-memory hot path cache for the current process only; never the source of truth
- **Indexes**:
  - Stable record identity on `id`
  - Metadata filters on `file_path`, `symbol_type`, `result_kind`, and scope
  - Build snapshot metadata keyed by `head_commit` and `build_timestamp_utc`

---

## Concurrency & Locking

- **Read**: Read the current active snapshot without blocking refresh when possible
- **Write**: Single-flight refresh lock per repo checkout
- **Conflict resolution**: Deterministic upsert by `content_hash` plus path/span identity; the newest successful refresh wins only after an atomic swap
