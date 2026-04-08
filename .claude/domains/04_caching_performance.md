# Domain: Caching & performance

> How latency and load are reduced without violating correctness

## Core Principles

- **Correctness Over Speed**: Caching and performance optimizations MUST NOT change functional behavior.
- **Cache Is Never the Source of Truth**: Authoritative state MUST live in durable storage or the external authority; caches may only accelerate reads.
- **Explicit Staleness Tolerance**: Every cache MUST define its maximum tolerated staleness (TTL and/or invalidation rules). Implicit staleness is prohibited.
- **Invalidation Strategy Is Mandatory**: Every cache MUST specify invalidation/refresh semantics (TTL-only, event-driven, write-through, write-behind). “We’ll figure it out later” is prohibited.
- **Deterministic Cache Keys**: Cache keys MUST be deterministic, collision-resistant, versioned where needed, and MUST NOT leak sensitive information.
- **Bounded Growth**: Every cache MUST have bounded growth (TTL, LRU, size limits, quotas) to prevent unbounded memory/disk usage.
- **Safe Degradation**: Cache unavailability MUST degrade to the authoritative path (possibly slower) rather than failing silently or serving incorrect data.
- **No Cross-Tenant Leakage**: Private/authenticated responses MUST NOT be cached publicly, and shared caches MUST be partitioned to prevent cross-user leaks.
- **Stampede Protection**: High-fanout caches MUST mitigate stampedes (singleflight, request coalescing, jittered TTL, or locking).
- **Performance Budgets**: Critical paths MUST define latency budgets (p95/p99) and throughput expectations. Optimization work MUST target explicit budgets.
- **Load Shedding / Overload Behavior**: Under saturation, the system MUST have explicit behavior (reject, degrade, queue, or shed) rather than uncontrolled failure or incorrect data serving.

## Best Practices

- Prefer event-driven invalidation when correctness requires freshness; otherwise use explicit TTL.
- Use jitter for TTLs to reduce synchronized expirations.
- Record cache hit/miss/eviction/stale-serve metrics and include them in dashboards.
- Cache negative results carefully (short TTL) and document correctness impact.

## Subchecklists

- [ ] Is correctness preserved if the cache is cold, stale, or unavailable?
- [ ] Is max tolerated staleness explicitly defined (TTL and/or invalidation strategy)?
- [ ] Is the invalidation/refresh strategy explicitly defined (TTL-only vs event-driven vs write-through/write-behind)?
- [ ] Are cache keys deterministic, stable, collision-resistant, and free of sensitive data?
- [ ] Is cache growth bounded (TTL/LRU/size limits/quotas)?
- [ ] Is there stampede protection for high-fanout keys (singleflight/coalescing/jitter/locks)?
- [ ] Are private/authenticated responses prevented from leaking via caching (partitioning/no-store)?
- [ ] Are cache hit/miss/eviction/stale-serve signals observable?
- [ ] Are p95/p99 latency budgets defined for the relevant critical path?
- [ ] Is overload behavior explicitly defined (shed/degrade/queue/reject) and safe?
- [ ] Are caches prevented from amplifying load during outages (stampede + fallback behavior validated)?

## Deterministic Checks

- Unit test: cache key stability/versioning and TTL/invalidation behavior.
- Load test (where applicable): verify stampede protection under concurrent access.
- Run `pytest tests/performance/` (or equivalent) for latency expectations.
- Run a load test for the critical path and verify p95/p99 targets (where applicable).
- Run a saturation test to verify load shedding behavior is correct (where applicable).