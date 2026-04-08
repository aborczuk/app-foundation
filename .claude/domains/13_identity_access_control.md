# Domain: Identity & access control

> Who can do what in the system

## Core Principles

- **Authorization Is Separate from Authentication**: Authn verifies identity; authz verifies permission. Both are required.
- **Default Deny**: Missing scope/role MUST deny access.
- **Least Privilege (NON-NEGOTIABLE)**: Component and user permissions MUST be scoped to the minimum access required.
- **Identity Enforcement**: Authentication MUST be verified at every trust boundary.
- **Role-Based Access**: Use roles/scopes instead of individual accounts where possible.
- **Machine Identities Matter**: Service accounts/tokens MUST be managed with the same rigor as user identities.
- **Auditable Access Decisions**: Access decisions MUST be logged with actor, resource, and outcome.
- **Token Lifecycle**: Token expiry/rotation/revocation expectations MUST be defined for each credential type.
- **Privileged MFA (If Humans Administer)**: Privileged human roles MUST require MFA (or equivalent strong auth) unless explicitly impossible and justified.
- **Session Policy**: Session lifetime, refresh, and revocation behavior MUST be defined for user-facing auth.

## Best Practices

- Standardize on OAuth/OIDC for external auth where possible.
- Implement session timeouts and audit trails for all critical access.
- Audit IAM roles for least privilege.
- Prefer short-lived tokens and narrow scopes; avoid long-lived broad-scoped tokens.

## Subchecklists

- [ ] Is authentication mandatory for every external-facing resource?
- [ ] Is authorization enforced separately from authentication?
- [ ] Is default deny enforced when scope/role is missing?
- [ ] Are all API keys and tokens scoped correctly (least privilege)?
- [ ] Are machine identities scoped and rotated?
- [ ] Are failed access attempts logged?
- [ ] Are access decisions logged (actor/resource/outcome)?
- [ ] Are token expiry/rotation/revocation expectations defined and testable?
- [ ] Do privileged roles require MFA (where applicable)?
- [ ] Are session lifetimes and revocation behavior defined and tested (where applicable)?

## Deterministic Checks

- Run `pytest tests/auth/` for permission verification.
- Audit `catalog.yaml` (or equivalent) to verify identity mappings.
- Verify at least one negative authz test exists for each critical permission boundary.
- Verify at least one test covers session expiry/revocation for privileged actions (where applicable).