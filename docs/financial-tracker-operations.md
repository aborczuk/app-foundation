# Financial Tracker Operations

This runbook covers filing refresh, worker recovery, and operator-visible
degradation. It is the operational contract for the refresh and observability
runtime. The metric and event emitters are implemented by T046; until then,
these names and fields are the required interface rather than evidence that a
live emitter is enabled.

## Runtime Modes

The safe default is fixture or manual-refresh mode:

- `SEC_SCHEDULE_ENABLED=false`
- `GOOGLE_SHEETS_DELIVERY_ENABLED=false`

Do not enable scheduled SEC refresh until PostgreSQL migrations, live-backend
tests, worker readiness, alert routing, and rollback instructions have passed.
A failed readiness check must leave the system in fixture/manual-refresh mode;
it must not publish partial filing or external-delivery results.

## Refresh Signals

When T046 is implemented, emit structured events with a shared
`correlation_id` for each refresh request, filing discovery attempt, work-item
transition, and recalculation handoff. Metric labels must remain low-cardinality.
Use issuer, accession, and full error text in the event or artifact, not metric
labels. Before T046, these events are not a readiness signal.

Planned T046 metrics:

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

After T046 is implemented, alert on a sustained SEC circuit-open state, queue
age beyond the service objective, repeated refresh failures, or a rising
dead-letter count. Alerts must include the correlation ID and a link to the
bounded failure artifact. Until then, observability readiness has not passed
and scheduled refresh must remain disabled.

## Planned Failure Artifacts

When T046 is implemented, every refresh or work-item failure will record one
compact event and, when more detail is needed, one durable artifact. The
compact event must contain:

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
4. The T046 observability events, metrics, alert routing, and failure-artifact path are implemented and visible; otherwise readiness fails.
5. The last successful observation remains queryable with freshness and quality state.
6. The rollback action is known and has been exercised against a non-production fixture.

## Outage Procedure

During an SEC or worker outage:

1. Disable `SEC_SCHEDULE_ENABLED` if refresh is not already safely disabled.
2. Preserve the last successful observation; mark freshness or quality state rather than writing nulls.
3. Stop unbounded retries. Leave recoverable items in `retry_wait` and inspect dead-letter artifacts when T046 is available.
4. After T046, check the shared SEC circuit state, queue age, failure categories, and affected correlation IDs. Before T046, use bounded run logs and direct work-item state checks instead.
5. Do not resume scheduled refresh before T046. For manual or fixture recovery, resume only after dependency and worker readiness checks pass. Expired leases may be recovered by a coordinator; completed writes must not be replayed.
6. Record the incident outcome and link the relevant failure artifact when available; otherwise retain the bounded run log.

## Manual Recovery

Manual recovery is limited to recoverable work items identified by idempotency
key and correlation ID. An operator must not edit immutable filings, facts, or
observations to repair a queue failure. Re-run the coordinator recovery path,
verify that the item transitions to `retry_wait` or `dead_letter` as expected,
then confirm that any resulting recalculation is targeted and idempotent.

## Evidence

For a refresh incident after T046 is implemented, retain the test or run log,
the correlation ID, the bounded failure artifact URI, the final work-item
state, and the last successful observation timestamp. Before T046, retain the
available bounded test or run log and keep scheduled refresh disabled. A green
dashboard without this evidence is not a successful operational verification.
