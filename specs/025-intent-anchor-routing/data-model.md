# Data Model: Read-Code Anchor Output Simplification

Entities, relationships, and state transitions for the read-code shortlist and body-first contract.

---

## Entities

### ReadRequest

**Purpose**: Represents one agent-initiated read-code lookup.  
**Lifecycle**: Created when the agent asks for a read, then resolved into a shortlist or body payload.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `id` | UUID | Yes | Primary key, immutable | Unique request identifier. |
| `query` | string | Yes | Non-empty | The symbol-like or semantic query. |
| `intent` | enum | Yes | `auto`, `exact_symbol`, `semantic_anchor`, `dependency_guided`, `window_only` | Selected or inferred query mode. |
| `created_at` | timestamp | Yes | ISO 8601 UTC | Request timestamp. |

**Example**:
```json
{
  "id": "8e8c2f78-9f3c-4e61-a822-4f83e8bc2a11",
  "query": "read_code_context",
  "intent": "semantic_anchor",
  "created_at": "2026-04-21T19:00:00Z"
}
```

### ReadRuleSet

**Purpose**: Encodes the agent-facing rules that live in `AGENTS.md` and the feature docs.  
**Lifecycle**: Stable documentation artifact, updated when the read contract changes.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `source_path` | string | Yes | Must point to `AGENTS.md` or the feature docs | Authoritative rule location. |
| `line_cap` | integer | Yes | Must be bounded | Current read limit behavior. |
| `default_shortlist_size` | integer | Yes | Must be `5` | The shortlist visible to the agent. |
| `max_expansions` | integer | Yes | Must be `1` | Hard cap on follow-up expansion. |

**Example**:
```json
{
  "source_path": "AGENTS.md",
  "line_cap": 80,
  "default_shortlist_size": 5,
  "max_expansions": 1
}
```

### AnchorCandidate

**Purpose**: One ranked semantic candidate returned by read-code.  
**Lifecycle**: Generated during retrieval, then inspected by the agent or replaced by a bounded expansion.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `symbol` | string | Yes | Non-empty | Symbol or pattern name. |
| `file_path` | string | Yes | Repo-relative path | Where the candidate lives. |
| `line` | integer | Yes | Positive line number | Suggested anchor line. |
| `confidence` | integer | Yes | `0` to `100` | Normalized composite confidence score visible to the agent. |
| `has_body` | boolean | Yes | Derived | Whether indexed full body content exists. |
| `is_exact_symbol` | boolean | No | Derived | Helpful for deterministic tie-breaks. |
| `body_excerpt` | string | No | Present when body is returned | Can be full body text when confidence is high. |

**Example**:
```json
{
  "symbol": "read_code_context",
  "file_path": "scripts/read_code.py",
  "line": 654,
  "confidence": 98,
  "has_body": true,
  "is_exact_symbol": true,
  "body_excerpt": "def read_code_context(...): ..."
}
```

### AnchorShortlist

**Purpose**: The bounded candidate set visible to the agent after retrieval and ranking.  
**Lifecycle**: Produced from the semantic pool, optionally expanded once, then consumed by the agent.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `request_id` | UUID | Yes | Must match `ReadRequest.id` | Links shortlist to the originating query. |
| `candidates` | array[AnchorCandidate] | Yes | Length `<= 5` by default | Shortlist shown to the agent. |
| `expanded_once` | boolean | Yes | `true` or `false` | Records whether the one allowed expansion was used. |
| `candidate_cap` | integer | Yes | Bounded | Maximum total candidates exposed. |

**Example**:
```json
{
  "request_id": "8e8c2f78-9f3c-4e61-a822-4f83e8bc2a11",
  "candidates": [
    {
      "symbol": "read_code_context",
      "file_path": "scripts/read_code.py",
      "line": 654,
      "confidence": 0.98,
      "has_body": true,
      "is_exact_symbol": true
    }
  ],
  "expanded_once": false,
  "candidate_cap": 5
}
```

### SymbolBodyPayload

**Purpose**: Full indexed body text for a confident symbol hit.  
**Lifecycle**: Read from the existing index and returned when the candidate is highly confident and body text exists.

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `symbol` | string | Yes | Non-empty | Symbol name. |
| `file_path` | string | Yes | Repo-relative path | Location of the symbol. |
| `body` | string | Yes | Non-empty | Indexed function/class body. |
| `confidence` | integer | Yes | `0` to `100` | Normalized composite confidence score; must be at least `90` to prefer body-first. |

**Example**:
```json
{
  "symbol": "read_code_context",
  "file_path": "scripts/read_code.py",
  "body": "def read_code_context(...):\n    ...",
  "confidence": 99
}
```

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| `ReadRequest` | `ReadRuleSet` | uses | N:1 | The request is evaluated against documented rules. |
| `ReadRequest` | `AnchorShortlist` | produces | 1:1 | The request resolves into one shortlist. |
| `AnchorShortlist` | `AnchorCandidate` | contains | 1:N | The shortlist holds the returned candidates. |
| `AnchorCandidate` | `SymbolBodyPayload` | may resolve to | 0:1 | Only high-confidence candidates with body text return the full body payload. |

---

## State Transitions

### ReadRequest Lifecycle

```
Created → Retrieved → Ranked → Shortlisted → Completed
                    ↓
                ExpandedOnce
                    ↓
                Completed
                    ↓
               Ambiguous/Degraded
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| `Created` | `Retrieved` | Query accepted | Request is valid | Load rules and semantic pool. |
| `Retrieved` | `Ranked` | Candidates found | Retrieval returns hits | Rank by deterministic confidence and tie-break rules. |
| `Ranked` | `Shortlisted` | Top 5 selected | Candidate list not empty | Return shortlist to the agent. |
| `Shortlisted` | `ExpandedOnce` | Agent asks for more | Expansion has not been used yet | Fetch the next bounded batch. |
| `ExpandedOnce` | `Completed` | Expansion consumed | Candidate cap not exceeded | Return the expanded shortlist. |
| `Shortlisted` | `Completed` | Agent accepts a candidate | Confidence is sufficient | Return the chosen anchor/body payload. |
| Any active state | `Ambiguous/Degraded` | Strong uncertainty or missing body | Guard rails prevent overcommitment | Preserve candidates and avoid looping. |

---

## Storage & Indexing

- **Primary storage**: Existing repository files plus the current vector index.
- **Caching**: None required for the narrowed scope.
- **Indexes**:
  - Existing semantic index for retrieval
  - Existing symbol `body` payload stored in the codebase index
  - Deterministic ordering derived from candidate metadata

---

## Concurrency & Locking

- **Read**: Read-only lookup path; no write transaction is introduced.
- **Write**: No new write path is required.
- **Conflict resolution**: Deterministic ordering and a one-expansion cap prevent competing retries from turning into loops.
