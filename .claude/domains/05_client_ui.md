# Domain: Client/UI

> How users interact with the system

## Core Principles

- **Server Is Authoritative**: Client state MUST reconcile to server truth; the client must not become a source of truth for critical state.
- **Explicit UI States**: Loading, empty, error, and success states MUST be distinct and deliberate.
- **Confirm Consequential Actions**: Destructive or high-impact actions MUST require explicit user confirmation.
- **Permissions Reflected and Enforced**: UI MUST reflect permissions, but authorization MUST also be enforced on the server.
- **Accessibility Is Non-Negotiable**: Core flows MUST meet baseline accessibility (keyboard navigation, labels, focus management).
- **Responsive by Default**: UI MUST remain usable across supported viewport sizes; mobile responsiveness is required unless explicitly out of scope.
- **Client Security Boundaries**: The client MUST NOT store secrets. Any client-available token MUST be treated as public and scoped accordingly.
- **Resilient UX**: The UI MUST handle retries, timeouts, and partial failures without corrupting user-visible state.
- **Data Consistency**: If optimistic updates are used, rollback and reconciliation MUST be implemented.
- **Client Telemetry (Redacted)**: Client-side errors and key UX events SHOULD be captured with structured telemetry, and MUST be redacted to avoid leaking secrets/PII.

## Best Practices

- Prefer optimistic updates only when rollback is safe and implemented.
- Minimize bundle size by trimming unused dependencies and avoiding heavy client libraries unless justified.
- Implement robust client-side validation for UX, but treat server validation as authoritative.
- Make failure messages actionable (what failed, what to do next).
- Avoid infinite spinners: enforce timeouts and show recovery paths.
- Prefer correlation IDs (or run/operation IDs) in client requests when supported so client failures can be traced to backend events.

## Subchecklists

- [ ] Are loading/empty/error/success states clearly implemented (no ambiguous spinners)?
- [ ] Are destructive/high-impact actions confirmed?
- [ ] If optimistic updates exist, is rollback + reconciliation implemented?
- [ ] Does the UI reconcile with server truth after refresh/reconnect?
- [ ] Are permission constraints enforced server-side (not only hidden in UI)?
- [ ] Are key flows accessible (labels, focus management, keyboard navigation)?
- [ ] Is the UI responsive across supported breakpoints (mobile/tablet/desktop) or explicitly marked out of scope?
- [ ] Are tokens treated as public and scoped appropriately (no secrets stored on client)?
- [ ] Are client failures actionable (clear retry/recovery paths)?
- [ ] Is client-side validation present for UX but not relied on for security?
- [ ] Are client-side errors captured (where applicable) with redaction (no secrets/PII)?
- [ ] Are user-visible failures traceable to backend events via correlation identifiers when applicable?

## Deterministic Checks

- Run UI test suite (`npm test` or equivalent).
- Run an accessibility check (axe/Lighthouse) on key screens.
- Run a responsive viewport check on key screens (mobile + desktop).
- Simulate network failure (offline/timeout) for a key flow and verify recovery.
- Trigger a known UI error path and confirm redacted telemetry is emitted (where applicable).