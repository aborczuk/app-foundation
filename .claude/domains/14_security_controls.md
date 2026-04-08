# Domain: Security controls

> How you protect data and comply with requirements

## Core Principles

- **No Secrets in Code/Logs/Committed Files**: Credentials, tokens, and secrets MUST never appear in source code, log output (including URLs), or any committed file.
- **Secrets from Env Vars at Runtime**: All secrets MUST be loaded exclusively from environment variables at runtime (or an explicitly approved secrets provider).
- **Least Privilege**: Every credential and component permission MUST be scoped to the minimum access required. Token scopes, IAM roles, and API permissions MUST be explicitly justified.
- **Zero-Trust Boundaries**: Every trust boundary between components MUST be identified in the Architecture Flow diagram. All cross-boundary inputs are untrusted until verified.
- **External Inputs Validated**: All inputs from outside (tool arguments, files, API responses, env vars, webhooks) MUST be validated before use. Path traversal and injection MUST be addressed.
- **Authenticated Webhooks**: All inbound webhook endpoints MUST require authentication; unauthenticated triggers are prohibited.
- **Errors Don't Expose Internals**: Error messages returned to callers MUST NOT include raw API responses, stack traces, or internal system state.
- **Supply-Chain Awareness**: Dependency integrity/vulnerability posture MUST be managed as part of security.
- **Threat Modeling Trigger**: New trust boundaries, new external integrations, or new privileged capabilities MUST trigger a lightweight threat model (assets, actors, attack paths, mitigations).

## Best Practices

- Use Pydantic (or equivalent) for input validation of all external data.
- Rotate credentials regularly and never hardcode defaults.
- Always use the principle of fail-secure.
- Prefer allowlists over denylists where feasible at trust boundaries.

## Subchecklists

- [ ] Does this pull a secret/token from an environment variable (not code, logs, or committed files)?
- [ ] Is input validation applied to all untrusted data?
- [ ] Do all inbound webhook endpoints require authentication (no unauthenticated triggers), and are required secrets/tokens sourced from environment variables (not code or logs)?
- [ ] Does the error message hide internal system secrets and internals?
- [ ] Are token scopes/IAM permissions explicitly justified (least privilege)?
- [ ] Are dependencies scanned for known vulnerabilities where applicable?
- [ ] For new trust boundaries/integrations/privileged capabilities, was a threat model performed and documented?
- [ ] Are threat mitigations reflected in tests/checklists (not only in prose)?

## Deterministic Checks

- Run `ruff check .` for hardcoded secrets patterns.
- Check `.gitignore` to ensure `.env` and sensitive files are excluded.
- Run dependency scan tooling (if configured) and confirm PASS.
- Verify threat model artifact exists for qualifying changes (where applicable).