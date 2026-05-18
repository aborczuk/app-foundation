# Runtime Backend Governance Template

Use this template for backend/runtime docs where an agent or operator needs to understand:

- what process is running
- what symbols own the runtime behavior
- what model or runtime policy is active
- what warmup/reuse guarantees exist
- what startup and cold-start behavior to expect

## Purpose

State the operational problem this backend solves in one short paragraph.

Example prompts:

- What repeated startup cost is being avoided?
- Who is the intended caller: agent, CLI, operator, service?
- What is the accepted path versus compatibility-only path?

## Active Design

Name the live runtime components explicitly:

- entrypoint module/file
- transport (`stdio`, HTTP, socket, in-process, etc.)
- caller/client symbol
- bounded tool or command surface

Expected content:

- process owner
- transport type
- registered tools/commands
- where the client session lives

## Key Runtime Symbols

List the exact symbols that matter operationally.

For each symbol, state:

- file reference
- ownership role
- why it matters

Recommended symbol types:

- client/session owner
- server entrypoint
- adapter layer
- readiness gate
- warmup function
- model/backend wrapper
- device-selection or precision-policy function

## Model And Runtime Policy

Document the concrete runtime dependencies that affect latency, memory, or correctness.

Minimum fields:

- active model name(s)
- backend wrapper symbol
- device selection policy
- precision policy
- cache/warmup policy

Use explicit statements like:

- `cuda` -> half precision
- `mps` -> half precision
- `cpu` -> float32

If memory or latency tradeoffs are intentional, say so directly.

## Ownership Split

Separate responsibilities between:

- caller/orchestrator
- backend/server
- shared library logic

Be explicit about what each side still owns.

## Current Reuse Boundary

Document what is guaranteed to stay warm and what is not.

Use two lists:

- Guaranteed now
- Not guaranteed now

This section must answer:

- does one session reuse one process?
- do separate CLI invocations reuse anything?
- do hooks or subprocesses share the same backend?

## Verified Behavior

Record the proof shape, not just the conclusion.

Include:

- live tests or probes used
- what was compared (`pid`, `started_at`, timings, device)
- what was proven
- what was disproven

## Runtime Setup

Write the operator or agent startup checklist.

Typical items:

1. refresh/restart condition
2. tool/command presence check
3. runtime capability probe
4. explicit warmup step
5. optional timing probe

## Expected Cold Starts

Split expected timings by phase, for example:

1. first backend/model load
2. first probe after warmup
3. repeated warm probe
4. first real end-to-end read

These should be acceptance landmarks, not vague claims.

## Operational Risks

Name the real costs and failure modes:

- high resident memory
- accelerator visibility differences
- duplicate process risk
- stale status scans
- unsupported hook/session ownership assumptions

## Where To Change It

Point maintainers at the exact seams for future work.

Recommended bullets:

- server lifecycle
- warmup behavior
- model/device policy
- readiness or freshness gate
- client transport or fallback policy

## Related Tests

List the specific unit and live/integration tests that guard the runtime behavior.

Always include at least:

- one contract/unit seam
- one live verification seam
