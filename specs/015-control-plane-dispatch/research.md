# Research: Phase 1 Event-Driven Dispatch

Date: 2026-04-02  
Spec: [spec.md](spec.md)

## Prior Art

### Candidate 1: n8n core platform

- Name: n8n
- URL: https://github.com/n8n-io/n8n
- Language: TypeScript
- License: Fair-code/Other
- Maintenance status: Active
- Installability verification:
  - `gh api repos/n8n-io/n8n` -> exists, active repo
  - `npm view n8n version` -> `2.14.2`

FR coverage estimate:
- Covers workflow execution and trigger handling substrate (partial FR-001/003/005)
- Does not provide project-specific ClickUp allowlist policy, metadata validation, dedupe guarantees, or single-run locking
- Coverage against phase FRs: ~35%

Adoption decision:
- Adopt as orchestration runtime dependency (already part of target architecture), but still requires custom dispatch policy layer in this repository.

### Candidate 2: ClickUp API v2 demo repository

- Name: clickup-APIv2-demo
- URL: https://github.com/clickup/clickup-APIv2-demo
- Language: TypeScript
- License: Not specified
- Maintenance status: Low-to-moderate (demo project)
- Installability verification:
  - `gh api repos/clickup/clickup-APIv2-demo` -> exists

FR coverage estimate:
- Demonstrates auth/webhook/REST patterns
- Not production-ready library; no idempotency, lock management, or policy enforcement
- Coverage against phase FRs: ~20%

Adoption decision:
- Use as reference only; do not adopt directly.

### Candidate 3: `clickup-sdk` (PyPI)

- Name: clickup-sdk
- URL: https://pypi.org/project/clickup-sdk/
- Language: Python
- License: Not evaluated deeply in this pass
- Maintenance status: Unclear
- Installability verification:
  - `uv pip install --dry-run clickup-sdk` -> resolves `clickup-sdk==0.1.6`

FR coverage estimate:
- Provides API convenience methods
- Does not provide webhook auth policy, dedupe/lock semantics, or routing governance
- Coverage against phase FRs: ~25%

Gap and rejection rationale:
- Pulls `httpx` down to `0.27.2` in dry-run resolution; this introduces dependency friction with existing repo baseline.
- Adds little value over direct `httpx` client for our strict policy/observability needs.

Decision:
- Reject.

### Candidate 4: `pyclickup` (PyPI)

- Name: pyclickup
- URL: https://pypi.org/project/pyclickup/
- Language: Python
- License: MIT
- Maintenance status: Unclear
- Installability verification:
  - `uv pip install --dry-run pyclickup` -> resolves `pyclickup==0.1.4`

FR coverage estimate:
- Basic API wrapper only
- No first-class workflow safety primitives required by phase 1
- Coverage against phase FRs: ~20%

Decision:
- Reject.

### Candidate 5: `n8n-nodes-clickup` package

- Name: n8n-nodes-clickup (claimed)
- URL: npm package lookup
- Installability verification:
  - `npm view n8n-nodes-clickup version` -> `404 Not Found`

Decision:
- Reject immediately (not installable as claimed).

## Build vs Adopt Conclusion

No single external tool covers >=70% of phase-1 FRs.  
Chosen approach:
- Reuse existing repo stack (`fastapi`, `httpx`, `pydantic`, `aiosqlite`)
- Implement a thin custom policy + state layer for FR-001..FR-008 guarantees
- Keep n8n as execution backend, not as policy engine

## Key Technical Decisions

### Decision: Use direct `httpx` clients for ClickUp + n8n interactions

Rationale:
- Maximum control over request signing, retry behavior, timeouts, and log redaction
- Consistent with existing project style in `mcp_trello`

Alternatives considered:
- `clickup-sdk`, `pyclickup` wrappers (rejected per above)

### Decision: Persist dedupe keys and active-run guard in local SQLite

Rationale:
- Needed to satisfy FR-004 and FR-006 across process restarts
- `aiosqlite` is already a project dependency

Alternatives considered:
- In-memory cache (insufficient on restart)
- ClickUp-only state checks (race-prone without local atomic guard)

### Decision: Fail closed on invalid signature or schema mismatch

Rationale:
- Directly satisfies FR-007 and FR-008
- Prevents unsafe dispatch on untrusted input

Alternatives considered:
- Soft-fail and continue processing (rejected as security risk)

## Dependency Security

Research snapshot date: 2026-04-02

| Dependency | Planned Version Baseline | Security Notes |
| :--------- | :----------------------- | :------------- |
| `httpx` | `0.28.1` (existing env baseline) | No critical issue selected in this planning pass; keep pinned and monitor upstream advisories |
| `fastapi` | `>=0.115.0` | No known blocker identified in this planning pass; maintain minor updates |
| `uvicorn` | `>=0.30.0` | No known blocker identified in this planning pass |
| `pydantic` | `>=2.0,<3.0` | No known blocker identified in this planning pass |
| `aiosqlite` | `>=0.20,<1.0` | No known blocker identified in this planning pass |

Action:
- Add dependency-security recheck to implementation checkpoint before merge.
