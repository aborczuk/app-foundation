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


def _scope(*, user_id, tenant_id: str = "tenant-a") -> AuthorizationScope:
    """Build a server-derived scope for registry authorization tests."""
    return AuthorizationScope(user_id, tenant_id, "subject-a", frozenset(), frozenset())


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
    registry.add_version(version_one)
    registry.activate("custom_margin", version=1, scope=_scope(user_id=owner_id))
    registry.add_version(_definition(version=2, owner_id=owner_id))
    registry.activate("custom_margin", version=2, scope=_scope(user_id=owner_id))

    assert registry.active_version("custom_margin").version == 2
    assert registry.get_version("custom_margin", version=1).expression == "revenue / operating_income"
    assert registry.get_version("custom_margin", version=1).content_hash == version_one.content_hash
    assert registry.get_version("custom_margin", version=1).state == "active"
    with pytest.raises(ValueError):
        registry.add_version(replace(version_one, content_hash="tampered"))


def test_rejects_activation_outside_tenant_scope() -> None:
    """A caller cannot activate another tenant's metric definition."""
    owner_id = uuid4()
    registry = MetricRegistry()
    registry.add_version(_definition(version=1, owner_id=owner_id, tenant_id="tenant-b"))

    with pytest.raises(AuthorizationError):
        registry.activate("custom_margin", version=1, scope=_scope(user_id=owner_id))


def test_retirement_preserves_definition_history_and_observation_selection() -> None:
    """Retiring a definition changes lifecycle state but does not erase historical results."""
    owner_id = uuid4()
    registry = MetricRegistry()
    registry.add_version(_definition(version=1, owner_id=owner_id))
    registry.activate("custom_margin", version=1, scope=_scope(user_id=owner_id))
    registry.retire("custom_margin", scope=_scope(user_id=owner_id))
    observations = (_observation("1"), _observation("2"))

    assert registry.active_version("custom_margin") is None
    assert registry.get_version("custom_margin", version=1).state == "retired"
    with pytest.raises(ValueError):
        registry.activate("custom_margin", version=1, scope=_scope(user_id=owner_id))
    assert select_observation(observations, metric_id="custom_margin", definition_version="1") is observations[0]
