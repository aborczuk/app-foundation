# Financial Tracker Operations

This runbook covers filing refresh, worker recovery, rollout, rollback, and
operator-visible degradation. It is the operational contract for the refresh
and observability runtime. The primary runtime seams are
`DiscoveryScheduler.from_environment`, `FilingRefreshCoordinator.process`,
and `RuntimeObservability.record_event` / `record_metric`.

## Runtime Modes

The safe default is fixture or manual-refresh mode:

- `SEC_SCHEDULE_ENABLED=false`
- `GOOGLE_SHEETS_DELIVERY_ENABLED=false`

`DiscoveryScheduler.from_environment` reads `SEC_SCHEDULE_ENABLED` and enables
only `1`, `true`, `yes`, or `on`; missing or invalid values are disabled. The
Google Sheets flag is a deployment gate for the explicit delivery path, not a
replacement for `GoogleSheetsDeliveryService` credential and owner checks.
A failed readiness check must leave the system in fixture/manual-refresh mode;
it must not publish partial filing or external-delivery results.

## Refresh Signals

Emit `RuntimeEvent` records with a shared `correlation_id` for each refresh
request, filing discovery attempt, work-item transition, and recalculation
handoff. Metric labels must remain low-cardinality. Use issuer, accession, and
full error text in the event or artifact, not metric labels.

Runtime metrics:

| Metric | Required dimensions | Meaning |
| --- | --- | --- |
| `financial_tracker_refresh_total` | `outcome` | Refresh requests by success, partial, or failure. |
| `financial_tracker_refresh_duration_seconds` | `outcome` | End-to-end refresh duration. |
| `financial_tracker_filing_total` | `source`, `outcome` | Filings discovered, accepted, duplicate, or rejected. |
| `financial_tracker_work_items_total` | `state`, `kind` | Work-item transitions and terminal outcomes. |
| `financial_tracker_queue_age_seconds` | `tenant_scope` | Age of the oldest eligible work item. |
| `financial_tracker_sec_requests_total` | `source`, `outcome` | SEC and EdgarTools request outcomes. |
| `financial_tracker_sec_circuit_open_total` | `source` | Requests prevented by the shared circuit state. |
| `financial_tracker_dead_letter_total` | `kind`, `category` | Work that exhausted bounded recovery. |

Alert on a sustained SEC circuit-open state, queue age beyond the service
objective, repeated refresh failures, or a rising dead-letter count. Alerts
must include the correlation ID and a link to the bounded failure artifact.

## Failure Artifacts

Every refresh or work-item failure records one compact event and, when more
detail is needed, one durable artifact. The compact event must contain:

- `correlation_id`, `operation`, `tenant_scope`, and UTC timestamps
- issuer identifier and filing accession when applicable
- source (`direct_sec`, `edgar_tools`, or `fixture`)
- failure `category`, `retryable`, `attempt`, and current work state
- a bounded `message_excerpt` with secrets and response bodies removed
- `artifact_uri` for the full diagnostic record, when one exists

The planned full artifact may contain stack details, request timing, response status,
and policy decisions. Do not include authorization headers, credentials,
portfolio holdings, or unbounded upstream response bodies. Artifact retention
must follow the repository retention policy and must not be used as a second
source of financial facts.

## Readiness Checks

Before enabling scheduled refresh, an operator verifies:

1. The foundation migration is applied and PostgreSQL is reachable.
2. The worker can lease, start, renew, complete, retry, and recover work.
3. The SEC User-Agent, timeout, rate budget, retry, and circuit policies are configured.
4. `RuntimeObservability` events, allowlisted metrics, alert routing, and the failure-artifact path are visible; otherwise readiness fails.
5. The last successful observation remains queryable with freshness and quality state.
6. The rollback action is known and has been exercised against a non-production fixture.

## Migration and Rollback

Apply migrations in numeric order: `001_foundation.sql`, then
`002_metric_definitions.sql`. Verify the `financial_tracker` schema and a
successful `SELECT 1` before enabling workers. The disposable integration
harness reapplies both files in sorted order; production uses the repository's
normal migration runner and must record the applied revision.

There are no destructive down migrations in this feature. For a code or
configuration rollback, disable both rollout flags, stop scheduled discovery,
allow in-flight work to finish or recover expired leases, and deploy the last
known-good application revision. Do not delete immutable filings, facts,
observations, or metric-definition history. A schema rollback requires the
database snapshot/restore procedure approved for the environment, followed by
the foundation and metric-registry live checks.

## Feature-Flag Rollout

1. Keep `SEC_SCHEDULE_ENABLED=false` and
   `GOOGLE_SHEETS_DELIVERY_ENABLED=false` in fixture/manual-refresh mode.
2. In a disposable or staging environment, apply migrations, run the guarded
   real-PostgreSQL suite, and verify worker, SEC, observability, and rollback
   checks.
3. Enable `SEC_SCHEDULE_ENABLED=true` for a canary worker only. Confirm due
   triggers, queue age, circuit behavior, correlation IDs, and last-successful
   observations before expanding the rollout.
4. Enable Google Sheets delivery only for an explicitly selected destination
   with a matching server-owned credential. The delivery adapter must reject
   owner, requester, issuer, or credential mismatches before any write.
5. If any check fails, disable the flags and follow the rollback procedure.

## Freshness and Quality States

Freshness is carried on each analysis row and must remain visible in API,
dashboard, XLSX, and Sheets projections. Current values include `fresh`,
`current`, and `recalculation-pending`. During an outage, preserve the last
successful value and update freshness or quality; do not replace it with null.
Use the finite `QualityState` values: `verified`, `derived`, `ambiguous`,
`incomplete`, `stale`, `superseded`, or `failed`. A recalculation must carry
the metric definition version/hash, analysis run ID, source selectors, and
correlation ID so an operator can distinguish stale data from missing data.

## Outage Procedure

During an SEC or worker outage:

1. Disable `SEC_SCHEDULE_ENABLED` if refresh is not already safely disabled.
2. Preserve the last successful observation; mark freshness or quality state rather than writing nulls.
3. Stop unbounded retries. Leave recoverable items in `retry_wait` and inspect dead-letter artifacts.
4. Check the shared SEC circuit state, queue age, failure categories, and affected correlation IDs in `RuntimeObservability`; use bounded run logs when the collector is unavailable.
5. Resume scheduled refresh only after dependency and worker readiness checks pass. Expired leases may be recovered by a coordinator; completed writes must not be replayed.
6. Record the incident outcome and link the relevant failure artifact when available; otherwise retain the bounded run log.

## Manual Recovery

Manual recovery is limited to recoverable work items identified by idempotency
key and current work-item state. Include the correlation ID emitted by
`RuntimeObservability`. An operator must not edit immutable filings, facts, or observations
to repair a queue failure. Re-run the coordinator recovery path, verify that
the item transitions to `retry_wait` or `dead_letter` as expected, then confirm
that any resulting recalculation is targeted and idempotent.

## Evidence

For every refresh incident, retain the test or run log, the correlation ID, the
bounded failure artifact URI, the final work-item state, and the last successful
observation timestamp. A green dashboard without this evidence is not a
successful operational verification.
