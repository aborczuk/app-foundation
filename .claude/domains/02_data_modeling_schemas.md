# Domain: Data modeling & schemas

> How information is structured, validated, and evolved

## Core Principles

- **Explicit Field Authority**: Every persisted or exchanged field MUST have a clearly identified source of truth. Mirrored, cached, or copied fields MUST document synchronization and reconciliation expectations.
- **Nullability Must Be Intentional**: Nullable or optional fields MUST be explicitly justified. Optional is not the default.
- **Schema Evolution Rules**: Changes to persisted or exchanged schemas MUST define backward/forward compatibility expectations and migration strategy before implementation.
- **Finite State Must Be Typed**: Finite sets of values (for example status, side, venue, lifecycle stage, or reason code) MUST use enums or other constrained types rather than free-text strings.
- **Derived Fields Are Not Authoritative**: Computed or derived fields MUST be clearly distinguished from authoritative fields. Persist derived values only when justified by performance, audit, or interoperability requirements.
- **Precision-Safe Numeric Types**: Money, price, quantity, ratios, and financial values MUST use precision-safe types and explicit units. Floating-point types are prohibited for authoritative financial state unless explicitly justified.
- **Validate at Boundaries**: External or persisted data MUST be validated at ingress/egress boundaries before domain use. Internal code must not rely on ad hoc downstream validation.
- **Identity and Mutability Must Be Explicit**: Identity fields and immutable fields MUST be clearly distinguished from mutable operational fields.

## Best Practices

- Use Pydantic models for ingress/egress validation and schema contracts.
- Keep schemas small, composable, and purpose-specific rather than using one model for every context.
- Avoid circular schema dependencies and deeply nested recursive model graphs unless clearly required.
- Prefer explicit field names and normalized units over implicit conventions.
- Design models to evolve safely across persistence, APIs, and async workflows.

## Subchecklists

- [ ] Does every field have an explicit source of truth or owner?
- [ ] Are nullable or optional fields explicitly justified?
- [ ] Are finite-state fields represented with enums or constrained literals instead of free text?
- [ ] Are derived fields clearly separated from authoritative stored fields?
- [ ] Are money, price, quantity, and ratio values modeled with precision-safe types and explicit units?
- [ ] Does this schema change define compatibility and migration expectations?
- [ ] Are immutable identity fields separated from mutable operational fields?
- [ ] Is validation performed at ingress/egress boundaries rather than deferred downstream?
- [ ] Are mirrored or copied fields documented with reconciliation expectations?
- [ ] Is this schema scoped to a clear purpose instead of acting as a catch-all model?
- [ ] Are inbound API/tool/integration payloads validated by Pydantic (or an explicitly approved equivalent) before use?
- [ ] Are persisted-record reads decoded/validated into a schema model before domain/service logic uses them?
- [ ] Are outbound integration payloads produced from validated schema models rather than hand-built dicts?

## Deterministic Checks

- Run `pyright` or `codebase-lsp get_diagnostics` to verify type consistency across schemas.
- Run `pytest tests/schemas/` (or equivalent) to verify validation, serialization, and backward-compatibility behavior.
- Run `ruff check .` to catch unused fields/imports and model-quality issues.