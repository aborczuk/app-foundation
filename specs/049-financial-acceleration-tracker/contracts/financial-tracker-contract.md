# Financial Tracker Boundary Contract

## Requester Classes

| Requester | Allowed boundary | Secret rule |
|---|---|---|
| Interactive browser | Server-rendered dashboard and authorized mutations | No source or provider secret reaches the browser. |
| API client | Versioned authorized query and metric-definition endpoints | Scope is resolved from server identity, never request payload ownership. |
| Scheduled worker | SEC discovery, recalculation, and export work | Uses least-privilege service identity and bounded feature flags. |
| Spreadsheet adapter | Explicitly authorized Google Sheets destination | Credential and destination scope are server-side and auditable. |

## Observation Response

Every observation response, dashboard row, XLSX row, and Sheets row carries:

- company identity and fiscal period;
- metric ID, definition version/hash, and definition state;
- result or finite quality state;
- analysis-run ID and freshness state;
- filing accession and source fact selectors;
- calculated timestamp and correlation ID when produced by a request.

Structured failures are limited to `unauthorized`, `forbidden`, `invalid_definition`, `source_unavailable`, `quality_unavailable`, `recalculation_pending`, and `export_failed`. Raw provider responses and internal stack traces are not returned.

## Metric Definition Contract

Definitions accept only approved selectors, existing supported metrics, typed bounded parameters, and allowlisted operations. Validation returns resolved inputs, dependency graph, errors, and the version/hash that activation would create. Activation is authorized, immutable, and enqueues targeted recalculation without changing historical observations.

## Export Contract

An export request records requester scope, filter/sort parameters, schema version, content hash, source accessions, and the authorized read-model snapshot. XLSX and Google Sheets adapters consume that same projection. Delivery failure changes export state only; it never mutates facts or observations.

## Runtime Contract

SEC requests use User-Agent, connection/read timeout, rate budget, classified retry, jitter, and circuit-open state. Work items carry idempotency key, lease, attempt count, retry state, terminal reason, and correlation ID. Scheduled refresh and Sheets delivery remain disabled until the plan readiness gate is green.
