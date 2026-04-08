# Domain: Ops & governance

> How you run, document, and evolve the system

## Core Principles

- **Reuse at Every Scale**: Never write new code or design custom architecture where an existing solution already fits. Choose established standard frameworks over custom.
- **Spec-First (NON-NEGOTIABLE)**: Every feature begins with a completed specification. No implementation begins before the spec is reviewed and approved.
- **Documentation as a First-Class Standard**: Docs are an essential deliverable, versioned with code. High-value docs MUST live close to the source.
- **Architectural Flow Visualization**: Every technical plan MUST have an Architecture Flow diagram describing the major components and trust boundaries.
- **Ownership Is Explicit**: Major components MUST have an owner.
- **Runbooks for Critical Operations**: Critical operations MUST have runbooks (deploy, rollback, recovery, incident response).
- **Incident Response & On-Call**: Critical systems MUST define incident response expectations (who responds, escalation, communication, and where runbooks live).
- **ADRs for Major Decisions**: Significant architectural decisions MUST be recorded (ADR or equivalent), including alternatives considered and rationale.
- **Learnings Feed Back**: Postmortems/reviews MUST produce actionable updates to specs/tests/checklists.
- **Exceptions Require Documentation**: Any exception to a domain rule MUST be documented with rationale and expiry.

## Best Practices

- Run `scripts/cgc_safe_index.sh` to keep the code graph fresh.
- Always update `walkthrough.md` for any feature change.
- Prefer a no-server solution (automation nodes, etc.) over building custom backend servers when it meets requirements safely.

## Subchecklists

- [ ] Does a complete specification (WHAT) exist before implementation?
- [ ] Has a reuse-first approach been seriously evaluated?
- [ ] Is versioned documentation included with the feature?
- [ ] Is there an Architecture Flow diagram for the change?
- [ ] Is component ownership clear?
- [ ] Are runbooks present/updated for critical operations?
- [ ] Is incident response/on-call responsibility defined for critical systems?
- [ ] Are escalation and communication paths defined (where applicable)?
- [ ] Is there an ADR (or equivalent) for major architectural decisions?
- [ ] Are learnings fed back into specs/tests/checklists?
- [ ] Are any rule exceptions documented with rationale and expiry?

## Deterministic Checks

- Run `/speckit.analyze` to verify consistency of specs and plans.
- Run `ls tests/docs/` to check if example code in docs is exercised.
- Verify runbooks exist for critical paths (deploy/rollback/recovery).
- Verify ADR exists for major changes (where applicable).
- Verify on-call/incident response links exist for critical operations (where applicable).