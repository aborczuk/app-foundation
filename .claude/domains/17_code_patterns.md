# Domain: Code patterns

> How code is structured, named, and called across implementation phases

## Module & File Layout Rules

- **One public symbol family per module**: Each module should export a cohesive set of related functions or a single class with its supporting types. Avoid god-modules that export unrelated functionality.
- **Layered placement**: New modules must belong to exactly one of the three layers: `domain/` (business logic), `service/` (orchestration), or `adapter/` (external IO). Cross-layer placement is prohibited.
- **Dependency direction**: Dependencies flow inward only: `adapter` → `service` → `domain`. Circular imports are prohibited.
  - **Clarification**: Adapters MAY import service/domain types only when required to satisfy interfaces and contracts; services MAY import domain types. What is prohibited is reversing dependency direction (domain/service depending on adapters) and creating cycles.
- **Public vs. private**: All public symbols (classes, functions, constants) must document their contract at the module level. Private symbols (prefixed `_`) must not appear in public signatures.

## Naming Conventions

- **Classes**: PascalCase, noun-oriented. Example: `ConnectionPool`, `TradeStateManager`, `VenueAdapter`.
- **Functions/methods**: snake_case, verb-oriented. Example: `fetch_instruments()`, `validate_order()`, `apply_margin_rule()`.
- **Constants**: SCREAMING_SNAKE_CASE. Example: `MAX_RETRIES`, `DEFAULT_TIMEOUT_SECS`.
- **No abbreviations in public symbols**: Use `connection_timeout`, not `conn_to`. Use `current_position`, not `curr_pos`. Clarity over brevity.
- **Test files mirror source**: `src/foo/bar.py` → `tests/foo/test_bar.py`. Test functions: `test_<scenario>_<expected>()`. Example: `test_fetch_with_expired_token_raises_auth_error()`.
- **Async naming**: Async functions (coroutines) have no special prefix. The `async def` keyword is the signal. Do not use `async_` prefix.

## LLD Phase Rules (MANDATORY for every sketch that creates or restructures symbols)

- **Signatures first**: Every new public symbol (class definition, function signature, constant declaration) must appear in the sketch's "Create" or "Modify" field with its exact signature **before tasks are generated**. Signatures are the contract; implementation is secondary.
- **Composition over inheritance**: Prefer constructor injection of dependencies over inheritance hierarchies. A class should accept its collaborators as constructor arguments (Dependency Injection pattern), not subclass to override behavior.
- **No business logic in adapters or IO layers**: The `adapter/` package is for external service calls, database queries, and file I/O only. All decision logic must be in `service/` or `domain/`. If you find an `if/else` in an adapter, it belongs in service.
- **No IO in domain or service layers**: The `domain/` and `service/` layers are pure computation. They must never call external services, databases, or file systems directly. All IO must be injected or called through adapter functions.
- **Async end-to-end**: If a function is declared `async`, every function in its call chain must also be `async`. Do not use `asyncio.run()` inside a coroutine — that blocks the event loop. Async functions must delegate to other async functions, never spawn threads or call sync-only code.
- **Function length cap**: A single function should not exceed 40 lines. If a sketch shows a single function that is longer, break it into sub-tasks first. Long functions are hard to test, reason about, and compose.
- **Explicit type hints required**: All public functions must have complete type hints (parameters and return type). Use `-> None` for functions with no return value. Use `-> <Type> | None` for optional returns. Unannotated functions are a domain violation.
- **Explicit state transitions**: State changes MUST occur through named operations with clear before/after semantics; hidden mutation across helpers is prohibited.
- **Side-effect isolation**: Decision logic MUST be separable from side effects; orchestration coordinates effects but decisions must be computable without IO.
- **Intentional error types**: Public APIs MUST represent meaningful failure classes (typed errors/results), not generic exceptions as contracts.
- **Public API documentation**: Public-facing functions/classes MUST have docstrings describing inputs/outputs/errors and at least one usage example for non-trivial APIs.
- **Formatting and linting are enforced**: Formatting/lint rules MUST be enforced automatically (CI) to prevent style drift.

## Best Practices

- **Explicit imports only**: Never use `from module import *`. Always name what you import. This makes call chains and dependencies visible.
- **Shallow call depth**: A public entry-point (e.g., a service method called by a sketch) should reach its leaf IO (database, external API, file system) in 3 hops or fewer. Deeper call stacks are harder to test and reason about.
- **Typed return values**: Service-layer functions must return typed objects (Pydantic models, dataclasses, or TypedDicts), never raw dicts. Raw dicts lose type information and are error-prone.
- **Single responsibility per module**: If a module is responsible for both database queries and API calls, split it. If a class does validation and state management, consider if one belongs in domain and one in service.
- **Immutability where possible**: Prefer dataclasses with `frozen=True` and Pydantic `BaseModel`s configured as immutable over mutable classes. Immutable objects are easier to reason about in async code.
- **Consistent error handling within a module**: Within a module boundary, use one primary error-handling convention (typed result vs typed exception). Mixed conventions require explicit documentation.

## Subchecklists

- [ ] Does every new public symbol have its signature (not just a comment) defined in the sketch before the task is implemented?
- [ ] Are all new modules placed in the correct layer (domain, service, or adapter)? No cross-layer placement?
- [ ] Does any single function in the sketch exceed 40 lines? If yes, split into smaller sub-tasks first.
- [ ] Are there any circular imports introduced by this sketch?
- [ ] Is any business logic (conditionals, decision-making) present in an adapter or file-IO layer? (prohibited)
- [ ] Is any external IO (database, API, file system) called from domain or service layers? (prohibited)
- [ ] Do all public functions have complete type hints (parameters and return type)?
- [ ] Do all service-layer functions return typed objects, not raw dicts or tuples?
- [ ] Are state transitions explicit and confined to named operations?
- [ ] Are side effects isolated from decision logic?
- [ ] Are public failure modes represented with meaningful typed errors/results?
- [ ] Are public symbols documented (docstrings with inputs/outputs/errors and examples where non-trivial)?
- [ ] Is formatting/lint enforcement configured as a gate (not advisory)?
- [ ] Are error-handling conventions consistent within a module boundary (or explicitly documented if mixed)?

## Deterministic Checks

- `ruff check src/` — catches import order violations, naming style inconsistencies, and unused imports.
- `ruff format src/` (or equivalent) — enforces formatting; CI MUST fail if formatting differs.
- `pyright src/` or `codebase-lsp get_diagnostics` — catches missing type hints, type mismatches, and circular imports.
- `pytest tests/ --tb=short` — verifies behavior and makes layering/testability failures visible.
- `python -m py_compile src/` — catches import cycles at parse time.