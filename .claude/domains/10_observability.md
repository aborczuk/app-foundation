# Domain: Observability

> How you see behavior (logs/metrics/traces/alerts)

## Core Principles

- **No Silent Failures**: Swallowed exceptions and silent failures are prohibited.
- **Structured Event Logs**: Logs MUST be structured, machine-parseable event records (e.g., JSON lines) with stable keys for timestamp, level, and event name.
- **Correlation Everywhere**: Logs/metrics MUST include identifiers that connect events across boundaries (run_id, request_id, operation_id).
- **Startup Visibility**: Every startup MUST emit the active run ID and resolved log path.
- **Latest-Run Pointer**: A deterministic latest-run pointer MUST be maintained; startup MUST expose the active run ID.
- **Actionable Alerts**: Alerts MUST be actionable and tied to a runbook or documented response.
- **Detect Stalls and Missing Signals**: The absence of expected events (stall) MUST be detectable.
- **Long-Running Work Must Be Visible**: Long-running build, index, embed, and write paths MUST emit stage markers, batch counts, and completion timing so silence is not the only signal.
- **Concise-By-Default CLI Logs**: Success-path command logging MUST be concise by default; full commands/arguments/path lists MUST be opt-in via explicit verbose mode.
- **Redaction and Privacy**: Sensitive data MUST be consistently redacted from logs/traces.
- **Forensic Reconstruction**: It MUST be possible to reconstruct major lifecycle events for critical operations from telemetry.
- **Minimum Metrics**: Critical paths MUST emit at least latency, error rate, and throughput metrics; saturation signals (queue depth, concurrency, DB busy) SHOULD be emitted where applicable.
- **Telemetry Retention & Access**: Logs/metrics/traces MUST define retention windows and access controls (who can read, how long retained).

## Best Practices

- Use `rich` for terminal output and `jsonl` for persistent logs.
- Include correlation IDs across component boundaries.
- Log context (e.g. `contract_id`, `strategy_name`) alongside every event.
- Keep high-cardinality fields controlled and intentional.
- Prefer dashboards that pair latency/error/throughput with saturation signals for critical paths.

## Subchecklists

- [ ] Does the application emit its `run_id` on startup?
- [ ] Is logging structured (JSON/JSONL)?
- [ ] Do logs include enough context to diagnose a silent failure?
- [ ] Do logs include run_id/request_id/operation_id for correlation?
- [ ] Are key business events emitted as structured events (where applicable)?
- [ ] Are alerts actionable and linked to a runbook/response?
- [ ] Can stalls/missing signals be detected?
- [ ] Do long-running build/index/embed/write paths emit stage markers, batch counts, and completion timing?
- [ ] Are default success logs concise, with full command/path detail emitted only in explicit verbose mode?
- [ ] Are secrets and sensitive values redacted?
- [ ] Can critical flows be reconstructed from logs/metrics?
- [ ] Do critical paths emit latency + error rate + throughput metrics?
- [ ] Are saturation signals emitted for constrained resources (queues, DB locks, worker pools) where applicable?
- [ ] Are log/metric retention windows explicit and access controlled?

## Deterministic Checks

- Run a dry-run and verify `latest_run.log` resolves to a real log (if applicable).
- Run `cat logs/last.jsonl | jq .` (or equivalent) to verify parseability.
- Trigger a known failure and confirm alert/event emitted (where applicable).
- Verify dashboards include latency/error/throughput for critical flows (where applicable).
- For a representative long-running build or refresh, verify stage markers and batch progress appear before completion.
- Verify retention policy is documented and applied.
