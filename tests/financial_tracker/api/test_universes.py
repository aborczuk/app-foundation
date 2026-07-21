"""Contract coverage for authorized universe lifecycle and membership mutation."""

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.persistence.models import Issuer, PortfolioKind


def _scope(
    user_id: UUID,
    *,
    tenant_id: str = "tenant-a",
    portfolio_ids: frozenset[UUID] = frozenset(),
    issuer_ids: frozenset[UUID] = frozenset(),
) -> AuthorizationScope:
    """Build a server-derived scope for a universe contract test."""
    return AuthorizationScope(user_id, tenant_id, "subject-a", portfolio_ids, issuer_ids)


def _issuer(name: str = "Acme") -> Issuer:
    """Build one stable issuer fixture."""
    return Issuer(uuid4(), "0000000001", name, datetime(2025, 1, 1, tzinfo=timezone.utc))


def test_universe_lifecycle_uses_server_owner_and_validates_memberships() -> None:
    """Create, rename, membership mutation, and archive remain owner-scoped."""
    from financial_tracker.api.universes import UniverseAPI

    owner_id = uuid4()
    issuer = _issuer()
    api = UniverseAPI(issuers=[issuer])
    initial_scope = _scope(owner_id, issuer_ids=frozenset({issuer.id}))

    universe = api.create(
        initial_scope,
        name="Core holdings",
        kind=PortfolioKind.PORTFOLIO,
        created_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
    )
    scope = replace(initial_scope, portfolio_ids=frozenset({universe.id}))
    renamed = api.rename(scope, universe.id, name="Core holdings v2")
    added = api.add_member(scope, universe.id, issuer.id)

    assert universe.owner_id == owner_id
    assert universe.tenant_id == "tenant-a"
    assert renamed.name == "Core holdings v2"
    assert added == (issuer.id,)
    assert api.members(scope, universe.id) == (issuer,)
    assert api.remove_member(scope, universe.id, issuer.id) == ()
    archived = api.archive(scope, universe.id)
    assert archived.archived is True
    with pytest.raises(ValueError, match="archived"):
        api.add_member(scope, universe.id, issuer.id)


def test_foreign_scope_cannot_read_or_mutate_a_universe() -> None:
    """Tenant and owner checks reject access even when a foreign ID is supplied."""
    from financial_tracker.api.universes import UniverseAPI

    issuer = _issuer()
    owner_scope = _scope(uuid4(), issuer_ids=frozenset({issuer.id}))
    api = UniverseAPI(issuers=[issuer])
    universe = api.create(owner_scope, name="Private", kind=PortfolioKind.WATCHLIST)
    foreign_scope = _scope(
        uuid4(),
        tenant_id="tenant-b",
        portfolio_ids=frozenset({universe.id}),
        issuer_ids=frozenset({issuer.id}),
    )

    with pytest.raises(AuthorizationError):
        api.get(foreign_scope, universe.id)
    with pytest.raises(AuthorizationError):
        api.rename(foreign_scope, universe.id, name="leaked")
    with pytest.raises(AuthorizationError):
        api.add_member(foreign_scope, universe.id, issuer.id)


def test_membership_validation_rejects_out_of_scope_and_duplicate_issuers() -> None:
    """Membership mutation requires a reachable issuer and rejects duplicate additions."""
    from financial_tracker.api.universes import UniverseAPI

    owner_scope = _scope(uuid4())
    issuer = _issuer()
    api = UniverseAPI(issuers=[issuer])
    universe = api.create(owner_scope, name="Watch", kind=PortfolioKind.WATCHLIST)
    scope = replace(owner_scope, portfolio_ids=frozenset({universe.id}))

    with pytest.raises(AuthorizationError):
        api.add_member(scope, universe.id, issuer.id)

    reachable_scope = replace(scope, issuer_ids=frozenset({issuer.id}))
    api.add_member(reachable_scope, universe.id, issuer.id)
    with pytest.raises(ValueError, match="already a member"):
        api.add_member(reachable_scope, universe.id, issuer.id)
    with pytest.raises(AuthorizationError):
        api.add_member(reachable_scope, universe.id, uuid4())
