# Domain: Networking & connectivity

> How components discover and talk to each other

## Core Principles

- **Explicit Timeouts**: All network operations MUST define timeouts; library defaults are prohibited.
- **Safe Retries**: Retries MUST be bounded, jittered, and limited to operations that are safe under retry.
- **TLS by Default Where Applicable**: Connections handling sensitive data MUST use TLS with certificate verification.
- **Assume Partitions**: Network partitions and partial failures MUST be assumed possible.
- **Least-Privilege Egress**: Outbound network access MUST be restricted to required destinations.
- **Error Classification**: Network failures MUST be classified separately from application failures.
- **Connection Limits**: Connection pooling and limits MUST be explicit to prevent resource exhaustion.
- **Certificate Lifecycle**: TLS certificate expiry/rotation MUST be monitored. Expiring certificates MUST alert before failure, and rotation MUST be tested.
- **DNS Failure Handling**: DNS failures MUST be treated as a distinct failure class, observable, and handled without uncontrolled retries.

## Best Practices

- Use service discovery instead of hardcoded IPs.
- Encrypt all internal traffic with TLS.
- Minimize DNS lookups by using long-lived connections where appropriate.
- Prefer connection pooling with explicit limits.
- Distinguish connect/read/write timeouts when supported.
- Prefer exponential backoff with jitter for retries.
- Classify network errors distinctly from application errors.

## Subchecklists

- [ ] Is internal traffic between services encrypted?
- [ ] Is service discovery functioning for all dependent microservices?
- [ ] Are retry mechanisms in place for flaky network connections?
- [ ] Are connect/read/write timeouts explicit?
- [ ] Are retries bounded, jittered, and limited to safe operations?
- [ ] Is TLS enforced with certificate verification where applicable?
- [ ] Is outbound egress restricted to required destinations?
- [ ] Are network failures observable and classified?
- [ ] Are connection pool limits explicit and tested under load?
- [ ] Is certificate expiry monitored and alerting configured (where applicable)?
- [ ] Is certificate rotation tested or procedurally defined?
- [ ] Are DNS failures observable and handled with bounded retries/backoff?

## Deterministic Checks

- Run `netcat -z -v <host> <port>` (or `nc -z -v <host> <port>`) to check service reachability.
- Verify TLS versioning in the client configuration and confirm certificate verification is enabled.
- Load test: confirm no connection leak under repeated failures.
- Verify certificate expiry monitoring exists for TLS endpoints (where applicable).