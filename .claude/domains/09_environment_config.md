# Domain: Environment & configuration

> How settings, secrets, and environments are managed

## Core Principles

- **Validate Configuration at Startup**: Required configuration MUST be validated on startup; invalid config MUST fail fast.
- **Deterministic Precedence**: Config sources and precedence MUST be deterministic and documented.
- **Secrets Are Separate and Never Logged**: Secrets MUST come from env vars (or equivalent secret provider) and MUST never be logged.
- **Safe Defaults**: Defaults MUST be safe for local dev and MUST NOT create unsafe production behavior.
- **Feature Flags Have Lifecycle**: Flags MUST have an owner and an expiry/cleanup plan.
- **No Hidden Production Toggles**: Production-only behavior MUST be controlled explicitly via config/flags, not code forks.
- **Secret Rotation Policy**: Secrets/tokens MUST have an owner and rotation expectations (cadence or trigger-based). Long-lived secrets require explicit justification.
- **Config Drift Detection**: The effective runtime configuration (non-secret) SHOULD have a stable “fingerprint” or version to detect drift across environments/runs.

## Best Practices

- Use Pydantic Settings for runtime configuration.
- Use typed settings (Pydantic Settings or equivalent).
- Load all secrets from environment variables (NEVER hardcode defaults).
- Separate secret and non-secret config.
- Map environment-specific configs to staging/production branches (if applicable).
- Expose effective runtime config safely (without secrets) for debugging.
- Emit a non-secret config fingerprint/version at startup for drift detection.

## Subchecklists

- [ ] Are all secrets loaded from the environment (not files)?
- [ ] Are setting defaults safe for local-only development?
- [ ] Is `config.yaml` or equivalent versioned without secrets?
- [ ] Does startup fail on missing/invalid required configuration?
- [ ] Is config precedence documented and deterministic?
- [ ] Are secrets sourced from environment variables (or secret provider) and never logged?
- [ ] Are defaults safe and environment-appropriate?
- [ ] Do feature flags have an owner and expiry?
- [ ] Is production behavior controlled via explicit config (not hardcoded forks)?
- [ ] Do critical secrets/tokens have an owner and rotation expectations (cadence/trigger)?
- [ ] Is there a safe, non-secret config fingerprint/version visible at runtime for drift detection?
- [ ] Are old/rotated secrets revoked or invalidated where applicable?

## Deterministic Checks

- Run `pytest tests/config/` for configuration validation.
- Verify environmental secrets are correctly mapped in the task runner.
- Verify runtime config dump redacts secrets.
- Verify config fingerprint/version is emitted at startup (without secrets).
- Verify secret rotation procedure exists for critical integrations.