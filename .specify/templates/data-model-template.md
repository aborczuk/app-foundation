# Data Model: [FEATURE NAME]

Entities, relationships, and state transitions for this feature.

---

## Entities

### [Entity 1 Name]

**Purpose**: [What this entity represents and why it's needed]  
**Lifecycle**: [How it moves through states — created, active, archived, etc.]

| Field | Type | Required? | Constraints | Notes |
|-------|------|-----------|-------------|-------|
| `id` | UUID | Yes | Primary key, immutable | Unique identifier |
| [field] | [type] | [Yes/No] | [Constraints] | [Notes] |

**Example**:
```json
{
  "id": "uuid-here",
  "created_at": "2026-04-08T...",
  "[field]": "[value]"
}
```

### [Entity 2 Name]

[Same structure]

---

## Relationships

| From Entity | To Entity | Relationship | Cardinality | Notes |
|-------------|-----------|--------------|-------------|-------|
| [Entity A] | [Entity B] | [has, belongs_to, links_to] | [1:1, 1:N, N:M] | [Details] |

---

## State Transitions

### [Entity Name] Lifecycle

```
[Initial State] → [State 2] → [State 3] → [Terminal State]
                     ↓
                  [Error State]
```

| From State | To State | Trigger | Guard Conditions | Actions |
|-----------|----------|---------|------------------|---------|
| [state1] | [state2] | [event] | [preconditions] | [side effects] |

---

## Storage & Indexing

- **Primary storage**: [Database type and location — SQLite, PostgreSQL, etc.]
- **Caching**: [If any cache layer — Redis, in-memory, etc.]
- **Indexes**: 
  - Primary key on `id`
  - [Other indexes for query performance]

---

## Concurrency & Locking

- **Read**: [Isolation level — serializable, snapshot, etc. if applicable]
- **Write**: [Locking strategy — optimistic, pessimistic, etc.]
- **Conflict resolution**: [How to handle concurrent updates if possible]
