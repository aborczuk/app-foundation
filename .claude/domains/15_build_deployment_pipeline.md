# Domain: Build & deployment pipeline

> How code becomes a running system safely

## Core Principles

- **Reproducible Builds**: Builds MUST be reproducible from pinned inputs (lockfiles, pinned tool versions).
- **Immutable, Traceable Artifacts**: Deployment artifacts MUST be immutable and traceable to a commit SHA (and build ID).
- **Promote the Same Artifact**: The same artifact MUST be promoted across environments (dev → staging → prod) where applicable; environments differ by configuration, not code.
- **Supply-Chain Hygiene**: Dependencies MUST be pinned; vulnerability scanning and provenance/SBOM generation MUST be part of the pipeline for production releases.
- **Deploy Authorization**: Who can deploy and under what conditions MUST be explicitly defined for production-impacting releases (permissions/approvals). Deploy actions MUST be attributable to an actor.
- **Infra/Config as Code**: Infrastructure and deployment configuration SHOULD be versioned and reviewed as code, not modified ad hoc.
- **Rollbacks Are Required**: Rollback steps MUST exist, be documented, and be exercised.
- **Safe Rollout Compatibility**: Code and schema changes MUST be compatible with rollout order (old+new running concurrently) or explicitly coordinated using expand/contract patterns.
- **Release Verification**: Every release MUST define a post-deploy verification step (smoke checks/health checks) and explicit rollback triggers.
- **Automated E2E Release Gates**: If E2E verification exists for a critical flow, it MUST be automated and runnable as part of the pipeline (pre-deploy and/or post-deploy). Manual-only E2E verification is prohibited for release gating.
- **Monitoring Window**: For production-impacting releases, define a monitoring window before declaring success (what metrics are watched, for how long).
- **Progressive Delivery Where Applicable**: High-risk changes SHOULD use canary/gradual rollout where feasible.

## Best Practices

- Run tests and linters as blocking CI gates.
- Record build metadata (commit SHA, build time, version).
- Prefer small, reversible deploys and gradual rollout where possible.

## Subchecklists

- [ ] Are builds reproducible with pinned dependencies and tool versions?
- [ ] Are artifacts immutable and traceable to commit SHA + build ID?
- [ ] Is the same artifact promoted across environments (no env-specific builds)?
- [ ] Are dependency/vulnerability scans run for release builds (and results reviewed/blocked as needed)?
- [ ] Is an SBOM/provenance artifact produced for production releases (where applicable)?
- [ ] Are deploy permissions/approvals defined for production-impacting releases, and is the deploy actor attributable?
- [ ] Are infrastructure/deployment config changes versioned and reviewed as code (where applicable)?
- [ ] Is rollback documented and tested?
- [ ] Are schema migrations safe with rollout sequencing (old+new compatibility / expand-contract) or explicitly coordinated?
- [ ] Is there a post-deploy verification step (smoke/health checks)?
- [ ] If E2E verification exists for critical flows, is it automated and executed as a release gate (not manual-only)?
- [ ] Are rollback triggers defined (what signals cause rollback)?
- [ ] Is a monitoring window defined (what signals, how long) before declaring success?
- [ ] If change is high-risk, is progressive delivery used (canary/gradual rollout) or explicitly justified if not?

## Deterministic Checks

- Run CI pipeline (tests + lint) and confirm green.
- Verify artifact metadata includes commit SHA + build ID.
- Run post-deploy smoke checks and confirm PASS.
- Verify deploy actor identity is recorded in release metadata/logs (where applicable).