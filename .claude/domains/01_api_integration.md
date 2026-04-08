# Domain: API & integration

> How the system exposes and consumes capabilities

## External Integration Rules

- **Venue-Constrained Discovery and Live Data Request Discipline**: For features that operate on venue-constrained entities (for example contracts or instruments), metadata-first object validation is mandatory.
- **Metadata First**: Discover the valid object set from venue metadata first, then request live data only for that validated set.
- **No Synthetic Objects**: Synthetic object generation that bypasses venue metadata validation is prohibited for live-data requests.

## Best Practices

- Standardize on sync-then-async patterns for external API calls.
- Use circuit breakers for high-latency integrations.
- Always include explicit versioning in internal/external API contracts.

## Integration Safety Rules

- **Explicit Timeout Ownership**: Every outbound integration call MUST define explicit timeout behavior before implementation. Timeout selection is part of the contract, not a library default.
- **Operation-Specific Retry Policy**: Retry behavior MUST be defined per operation. Retries are allowed only for operations that are proven safe under retry, with explicit max attempts and backoff policy.
- **Idempotent External Writes**: Any outbound write that can be retried, replayed, or duplicated MUST define an idempotency mechanism, or MUST explicitly state that it is non-idempotent and how duplicate execution is prevented.
- **Duplicate / Delayed / Out-of-Order Handling**: For any integration that can return callbacks, events, or repeated responses, the system MUST define how duplicate, delayed, stale, or out-of-order deliveries are detected and handled.
- **Fail Closed on Ambiguous External State**: Partial, ambiguous, or conflicting external responses MUST NOT be silently interpreted as success. Ambiguous state MUST block downstream side effects until reconciliation or explicit operator handling.
- **Contract Versioning and Compatibility**: All externally consumed or exposed contracts MUST define versioning and compatibility expectations. Breaking assumptions about payload shape, field meaning, or callback behavior are design-time gaps.
- **Correlation and Trace Propagation**: Every outbound request and inbound callback/event MUST carry a correlation identifier that links the external interaction to the local run, request, or operation.
- **Authenticated Async Callbacks**: Every inbound callback/webhook from an external service MUST define and enforce an authentication mechanism before payload processing.
- **Schema-Validated Integration Boundaries**: All inbound and outbound integration payloads MUST be validated against explicit schemas before use. Loose parsing of integration payloads is prohibited.
- **Explicit External State Authority**: For each integration, the system MUST define whether the external service is authoritative for status/result state, and downstream behavior MUST follow that authority model.

## Async Return Path (MANDATORY for every external service integration)

For every external service this system calls outbound, the return path MUST be explicitly modeled before implementation begins. Ask: does the result arrive synchronously in the HTTP response, or does the external service execute and respond later?

- **Synchronous**: result returns in the same HTTP response — no further modeling required
- **Asynchronous**: the external service executes independently and must notify this system when done — ALL of the following MUST be defined before tasks are generated:
  1. A callback/webhook edge FROM the external service back TO this system appears in the Architecture Flow diagram
  2. A contract exists covering: how the external service discovers the callback URL, what auth mechanism it presents, and what the payload looks like
  3. A spec FR names the requirement from the external service's perspective — not just "we receive the callback" but "the external service MUST POST to X when done"

An external service node in the Architecture Flow with only an outbound edge and no defined return path is always a `❌` gap at plan stage unless the integration is explicitly confirmed to be synchronous. The sync/async question MUST be answered explicitly — never assumed.

## Subchecklists

- [ ] Does the integration discover the valid set via metadata first?
- [ ] Are error response formats defined for all failure modes?
- [ ] Are rate limiting requirements quantified with specific thresholds?
- [ ] For each async external service: does the callback endpoint exist, is auth enforced on it, and is the incoming payload validated before processing?
- [ ] Does every outbound call define explicit timeout behavior?
- [ ] Is retry behavior defined per operation, including max attempts and backoff policy?
- [ ] For any retried or replayable write, is idempotency explicitly enforced?
- [ ] Are duplicate, delayed, stale, or out-of-order callbacks/responses handled safely?
- [ ] Does ambiguous or partial external state block downstream side effects until reconciliation?
- [ ] Are request/response and callback contracts versioned with compatibility expectations documented?
- [ ] Is a correlation ID propagated across outbound requests and inbound callbacks/events?
- [ ] Are non-idempotent operations explicitly marked, with duplicate-prevention behavior defined?
- [ ] Is callback/webhook authentication explicitly defined and enforced before payload processing?
- [ ] For any workflow/webhook integration (e.g., n8n), are the required secret(s)/token(s) explicitly named in the integration contract and enforced at the boundary (and not hardcoded)?
- [ ] Are inbound and outbound payloads validated against explicit schemas rather than parsed loosely?
- [ ] Is the source of truth for externally produced status/result state explicitly identified?

## Deterministic Checks

- Run `pytest tests/integration/` (or equivalent) to verify live connectivity.
- Verify contract validation logic via `codebase-lsp get_diagnostics`.