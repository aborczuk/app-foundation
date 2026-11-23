# Financial Acceleration Tracker Data Model

## Authority

PostgreSQL is authoritative for identity, portfolio ownership, filing metadata, normalized facts, metric-definition versions, analysis runs, observations, work items, export requests, and audit events. Cache entries and exported files are derived artifacts and never replace the source records.

## Core Entities

| Entity | Key identity | Required invariants |
|---|---|---|
| User / API Client | tenant and subject ID | Every request resolves to a server-side subject and scope. |
| Watchlist / Portfolio | owner, type, stable ID | Membership is owner-scoped; client-supplied owner IDs are not trusted. |
| Company | issuer ID and CIK | CIK resolution is stable and preserves ticker history separately. |
| Filing | authority, CIK, accession | Accession and source authority are unique; amendments create a new snapshot. |
| Financial Fact | filing, concept, period, dimensions, unit | Facts are append-only and retain source context and quality state. |
| Metric Definition Version | metric ID, version, content hash | Versions are immutable, validated, authorized, and never overwritten. |
| Metric Observation | company, period, source snapshot, definition version, analysis run | Observation writes are immutable and idempotent for the same calculation identity. |
| Analysis Run | stable run ID and scope | Run scope and selected filing/definition versions are auditable. |
| Work Item | idempotency key and state | One coordinator owns transitions; retries cannot duplicate facts or observations. |
| Export Request | requester, filter hash, destination | Manifest captures the authorized read contract, schema version, and source IDs. |

## State Transitions

Work items use `queued -> leased -> running -> succeeded` or `retry_wait -> leased`; terminal failure is `dead_letter`, and explicit cancellation is `cancelled`. Lease expiry returns work to a recoverable state without replaying completed observation writes.

Quality states are finite and explicit: `verified`, `derived`, `ambiguous`, `incomplete`, `stale`, `superseded`, and `failed`. A missing or invalid result is an observation with a quality state, not a silent null.

Metric definitions use `draft -> active -> retired` or `invalid`. Activation persists a new immutable version and enqueue request in one transaction. Retirement prevents new calculations but does not remove historical observations.

## Transaction Boundaries

1. Filing and fact ingestion validates source identity, writes append-only facts, and records an idempotency/audit event atomically.
2. Metric activation validates the expression, units, dependencies, authorization, and version hash before persisting activation and recalculation work atomically.
3. Observation writes use uniqueness constraints and a transactional handoff so retries cannot create duplicate results.
4. Export requests capture the authorized filter and manifest before delivery; delivery failure is retryable and cannot alter financial results.

## Read Model Requirements

Every dashboard, API, XLSX, and Google Sheets result uses the same authorized projection. The projection includes company identity, fiscal period, metric ID/version, result or quality state, analysis run, filing accession, source fact selectors, calculated time, and freshness state. Tenant scope is applied before pagination, sorting, caching, or export generation.
