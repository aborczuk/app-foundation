"""Red fixture coverage for metric-definition lifecycle and history."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.metrics.registry import MetricDefinitionVersion, MetricRegistry, select_observation
from financial_tracker.persistence.models import Provenance, QualityState


def _definition(*, version: int, owner_id, tenant_id: str = "tenant-a") -> MetricDefinitionVersion:
    """Build an immutable user metric version fixture."""
    return MetricDefinitionVersion(
        metric_id="custom_margin",
        tenant_id=tenant_id,
        version=version,
        expression="revenue / operating_income",
        content_hash=f"custom-margin-v{version}",
        output_unit="ratio",
        state="draft",
        created_by=owner_id,
        created_at=datetime(2025, version, 1, tzinfo=timezone.utc),
    )


def _scope(
    *,
    user_id,
    tenant_id: str = "tenant-a",
    issuer_ids: frozenset | None = None,
) -> AuthorizationScope:
    """Build a server-derived scope for registry authorization tests."""
    return AuthorizationScope(user_id, tenant_id, "subject-a", frozenset(), issuer_ids or frozenset())


def _observation(version: str) -> MetricObservation:
    """Build one historical observation pinned to a definition version."""
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=uuid4(),
        fiscal_period_id=uuid4(),
        metric_id="custom_margin",
        definition_version=version,
        definition_hash=f"custom-margin-v{version}",
        definition_state="active",
        calculation_version="calc-1",
        source_snapshot_hash=f"snapshot-{version}",
        analysis_run_id=uuid4(),
        value=Decimal("0.20"),
        quality_state=QualityState.VERIFIED,
        freshness="current",
        provenance=(Provenance(uuid4(), uuid4(), "000001-25-000001", "https://sec.test/source", "Revenue", datetime(2025, 5, 1, tzinfo=timezone.utc)),),
        calculated_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
    )


def test_activates_new_versions_without_rewriting_prior_definition() -> None:
    """Activating version two leaves version one immutable and selectable."""
    owner_id = uuid4()
    registry = MetricRegistry()
    version_one = _definition(version=1, owner_id=owner_id)
    scope = _scope(user_id=owner_id)
    registry.add_version(version_one, scope=scope)
    registry.activate("custom_margin", version=1, scope=scope)
    registry.add_version(_definition(version=2, owner_id=owner_id), scope=scope)
    registry.activate("custom_margin", version=2, scope=scope)

    active = registry.active_version("custom_margin", scope=scope)
    assert active is not None
    assert active.version == 2
    assert registry.get_version("custom_margin", version=1, scope=scope).expression == "revenue / operating_income"
    assert registry.get_version("custom_margin", version=1, scope=scope).content_hash == version_one.content_hash
    assert registry.get_version("custom_margin", version=1, scope=scope).state == "active"
    with pytest.raises(ValueError):
        registry.add_version(replace(version_one, content_hash="tampered"), scope=scope)
    with pytest.raises(ValueError):
        registry.add_version(replace(version_one, version=3, state="active"), scope=scope)


def test_rejects_activation_outside_tenant_scope() -> None:
    """A caller cannot activate another tenant's metric definition."""
    owner_id = uuid4()
    registry = MetricRegistry()
    foreign_scope = _scope(user_id=owner_id, tenant_id="tenant-b")
    registry.add_version(
        _definition(version=1, owner_id=owner_id, tenant_id="tenant-b"),
        scope=foreign_scope,
    )

    with pytest.raises(AuthorizationError):
        registry.activate("custom_margin", version=1, scope=_scope(user_id=owner_id))


def test_retirement_preserves_definition_history_and_observation_selection() -> None:
    """Retiring a definition changes lifecycle state but does not erase historical results."""
    owner_id = uuid4()
    registry = MetricRegistry()
    scope = _scope(user_id=owner_id)
    registry.add_version(_definition(version=1, owner_id=owner_id), scope=scope)
    registry.add_version(_definition(version=2, owner_id=owner_id), scope=scope)
    registry.activate("custom_margin", version=1, scope=scope)
    registry.retire("custom_margin", scope=scope)
    observations = (_observation("1"), _observation("2"))

    assert registry.active_version("custom_margin", scope=scope) is None
    assert registry.get_version("custom_margin", version=1, scope=scope).state == "retired"
    assert registry.get_version("custom_margin", version=2, scope=scope).state == "retired"
    with pytest.raises(ValueError):
        registry.activate("custom_margin", version=1, scope=scope)
    with pytest.raises(ValueError):
        registry.activate("custom_margin", version=2, scope=scope)
    scope = _scope(user_id=owner_id, issuer_ids=frozenset({observations[0].issuer_id}))
    assert (
        select_observation(
            observations,
            metric_id="custom_margin",
            definition_version="1",
            scope=scope,
            issuer_id=observations[0].issuer_id,
            fiscal_period_id=observations[0].fiscal_period_id,
            analysis_run_id=observations[0].analysis_run_id,
        )
        is observations[0]
    )


def test_rejects_same_tenant_non_owner_lifecycle_changes() -> None:
    """A tenant peer cannot activate or retire another user's definition."""
    owner_id = uuid4()
    registry = MetricRegistry()
    registry.add_version(_definition(version=1, owner_id=owner_id), scope=_scope(user_id=owner_id))
    peer_scope = _scope(user_id=uuid4())

    with pytest.raises(AuthorizationError):
        registry.activate("custom_margin", version=1, scope=peer_scope)


def test_reads_are_isolated_when_tenants_reuse_metric_identity() -> None:
    """Tenant-scoped reads select the matching definition when IDs overlap."""
    owner_a = uuid4()
    owner_b = uuid4()
    scope_a = _scope(user_id=owner_a, tenant_id="tenant-a")
    scope_b = _scope(user_id=owner_b, tenant_id="tenant-b")
    registry = MetricRegistry()
    registry.add_version(
        _definition(version=1, owner_id=owner_a, tenant_id="tenant-a"),
        scope=scope_a,
    )
    registry.add_version(
        _definition(version=1, owner_id=owner_b, tenant_id="tenant-b"),
        scope=scope_b,
    )

    registry.activate("custom_margin", version=1, scope=scope_a)
    registry.activate("custom_margin", version=1, scope=scope_b)

    active_a = registry.active_version("custom_margin", scope=scope_a)
    active_b = registry.active_version("custom_margin", scope=scope_b)
    assert active_a is not None
    assert active_b is not None
    assert active_a.tenant_id == "tenant-a"
    assert active_b.tenant_id == "tenant-b"
