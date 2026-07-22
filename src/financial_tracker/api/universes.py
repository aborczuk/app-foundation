"""Authorized watchlist and portfolio lifecycle operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from financial_tracker.identity.resolver import (
    AuthorizationError,
    AuthorizationScope,
    require_issuer_access,
    require_portfolio_access,
)
from financial_tracker.persistence.models import Issuer, PortfolioKind

MAX_UNIVERSE_NAME = 200


@dataclass(frozen=True, slots=True)
class Universe:
    """Tenant- and owner-bound watchlist or portfolio projection."""

    id: UUID
    tenant_id: str
    owner_id: UUID
    name: str
    kind: PortfolioKind
    created_at: datetime
    archived: bool = False


class UniverseAPI:
    """Expose owner-authorized universe lifecycle and membership operations."""

    def __init__(
        self,
        *,
        issuers: Iterable[Issuer],
        universes: Iterable[Universe] = (),
        memberships: Mapping[UUID, Iterable[UUID]] | None = None,
    ) -> None:
        """Bind issuer identities and server-owned universe membership state."""
        self._issuers = tuple(sorted(issuers, key=lambda issuer: (issuer.legal_name, str(issuer.id))))
        self._issuer_by_id = {issuer.id: issuer for issuer in self._issuers}
        self._universes = {universe.id: universe for universe in universes}
        self._memberships = {
            universe_id: set(issuer_ids)
            for universe_id, issuer_ids in (memberships or {}).items()
        }

    def create(
        self,
        scope: AuthorizationScope,
        *,
        name: str,
        kind: PortfolioKind,
        created_at: datetime | None = None,
    ) -> Universe:
        """Create a universe using owner and tenant identity from the server scope."""
        normalized_name = _universe_name(name)
        if not isinstance(kind, PortfolioKind):
            raise ValueError("kind must be a supported portfolio kind")
        universe = Universe(
            id=uuid4(),
            tenant_id=scope.tenant_id,
            owner_id=scope.user_id,
            name=normalized_name,
            kind=kind,
            created_at=_utc_datetime(created_at or datetime.now(timezone.utc), "created_at"),
        )
        self._universes[universe.id] = universe
        self._memberships[universe.id] = set()
        return universe

    def list(
        self,
        scope: AuthorizationScope,
        *,
        kind: PortfolioKind | None = None,
        include_archived: bool = False,
    ) -> tuple[Universe, ...]:
        """Return only caller-owned universes in the server-derived portfolio scope."""
        return tuple(
            sorted(
                (
                    universe
                    for universe in self._universes.values()
                    if universe.id in scope.portfolio_ids
                    and universe.tenant_id == scope.tenant_id
                    and universe.owner_id == scope.user_id
                    and (kind is None or universe.kind is kind)
                    and (include_archived or not universe.archived)
                ),
                key=lambda universe: (universe.name, str(universe.id)),
            )
        )

    def get(self, scope: AuthorizationScope, universe_id: UUID) -> Universe:
        """Return one universe only after server-derived owner authorization."""
        return self._require_owned(scope, universe_id)

    def rename(self, scope: AuthorizationScope, universe_id: UUID, *, name: str) -> Universe:
        """Rename an active owner-authorized universe without changing its identity."""
        universe = self._require_active(scope, universe_id)
        renamed = replace(universe, name=_universe_name(name))
        self._universes[universe_id] = renamed
        return renamed

    def add_member(
        self,
        scope: AuthorizationScope,
        universe_id: UUID,
        issuer_id: UUID,
    ) -> tuple[UUID, ...]:
        """Add one reachable issuer after owner, tenant, and duplicate validation."""
        self._require_active(scope, universe_id)
        require_issuer_access(scope, issuer_id)
        if issuer_id not in self._issuer_by_id:
            raise KeyError(f"issuer {issuer_id} does not exist")
        members = self._memberships.setdefault(universe_id, set())
        if issuer_id in members:
            raise ValueError("issuer is already a member")
        members.add(issuer_id)
        return _sorted_member_ids(members)

    def remove_member(
        self,
        scope: AuthorizationScope,
        universe_id: UUID,
        issuer_id: UUID,
    ) -> tuple[UUID, ...]:
        """Remove one reachable issuer while preserving the universe identity."""
        self._require_active(scope, universe_id)
        require_issuer_access(scope, issuer_id)
        members = self._memberships.setdefault(universe_id, set())
        if issuer_id not in members:
            raise ValueError("issuer is not a member")
        members.remove(issuer_id)
        return _sorted_member_ids(members)

    def members(self, scope: AuthorizationScope, universe_id: UUID) -> tuple[Issuer, ...]:
        """Return authorized, known members in deterministic company order."""
        self._require_owned(scope, universe_id)
        return tuple(
            sorted(
                (
                    self._issuer_by_id[issuer_id]
                    for issuer_id in self._memberships.get(universe_id, set())
                    if issuer_id in scope.issuer_ids and issuer_id in self._issuer_by_id
                ),
                key=lambda issuer: (issuer.legal_name, str(issuer.id)),
            )
        )

    def archive(self, scope: AuthorizationScope, universe_id: UUID) -> Universe:
        """Archive an owner-authorized universe while retaining its memberships."""
        universe = self._require_owned(scope, universe_id)
        archived = replace(universe, archived=True)
        self._universes[universe_id] = archived
        return archived

    def _require_owned(self, scope: AuthorizationScope, universe_id: UUID) -> Universe:
        """Resolve a universe only within the caller's server-derived owner scope."""
        require_portfolio_access(scope, universe_id)
        universe = self._universes.get(universe_id)
        if universe is None or universe.tenant_id != scope.tenant_id or universe.owner_id != scope.user_id:
            raise AuthorizationError("universe is outside the authenticated user's scope")
        return universe

    def _require_active(self, scope: AuthorizationScope, universe_id: UUID) -> Universe:
        """Reject membership and rename mutations after archive."""
        universe = self._require_owned(scope, universe_id)
        if universe.archived:
            raise ValueError("archived universes cannot be mutated")
        return universe


def _universe_name(value: str) -> str:
    """Normalize and bound a user-visible universe name."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("universe name must be non-empty")
    if len(normalized) > MAX_UNIVERSE_NAME:
        raise ValueError("universe name is too long")
    return normalized


def _utc_datetime(value: datetime, field_name: str) -> datetime:
    """Normalize aware timestamps to UTC and reject ambiguous naive values."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _sorted_member_ids(members: Iterable[UUID]) -> tuple[UUID, ...]:
    """Return membership IDs in deterministic order."""
    return tuple(sorted(members, key=str))
