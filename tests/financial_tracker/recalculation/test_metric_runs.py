"""Contract coverage for dependency-aware targeted recalculation enqueueing."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.metrics.registry import MetricDefinitionVersion, MetricRegistry
from financial_tracker.persistence.models import Provenance, QualityState
from financial_tracker.recalculation.metric_runs import (
    InMemoryMetricRunQueue,
    MetricRecalculationRequest,
    enqueue_targeted_recalculation,
    plan_recalculation_targets,
    select_versioned_observation,
)
from financial_tracker.work.state import WorkState


def _request(**overrides) -> MetricRecalculationRequest:
    """Build one deterministic recalculation request for tests."""
    issuer_id = uuid4()
    values = {
        "scope": AuthorizationScope(uuid4(), "tenant-a", "subject-a", frozenset(), frozenset({issuer_id})),
        "root_metric_id": "margin",
        "definition_identities": {
            "margin": ("2", "hash-margin-2"),
            "streak": ("4", "hash-streak-4"),
            "acceleration": ("7", "hash-acceleration-7"),
        },
        "issuer_ids": (issuer_id,),
        "fiscal_period_ids": (uuid4(),),
        "source_snapshot_hash": "filing-2",
    }
    values.update(overrides)
    return MetricRecalculationRequest(**values)


def test_planner_selects_transitive_dependents_in_dependency_order() -> None:
    """A changed metric refreshes its dependent metrics after the root."""
    request = _request()
    targets = plan_recalculation_targets(
        request,
        {
            "streak": ("margin",),
            "acceleration": ("streak",),
            "margin": ("revenue",),
        },
    )

    assert [target.metric_id for target in targets] == ["margin", "streak", "acceleration"]
    assert [(target.definition_version, target.definition_hash) for target in targets] == [
        ("2", "hash-margin-2"),
        ("4", "hash-streak-4"),
        ("7", "hash-acceleration-7"),
    ]


def test_enqueue_is_idempotent_and_snapshot_changes_create_new_work() -> None:
    """Retries reuse queued work while a new filing snapshot is distinct work."""
    request = _request()
    graph = {"streak": ("margin",), "margin": ("revenue",)}
    queue = InMemoryMetricRunQueue()

    first = enqueue_targeted_recalculation(queue, request, graph)
    retry = enqueue_targeted_recalculation(queue, request, graph)
    changed = enqueue_targeted_recalculation(
        queue,
        _request(source_snapshot_hash="filing-3"),
        graph,
    )

    assert [item.id for item in retry] == [item.id for item in first]
    assert len(queue.items()) == 4
    assert all(item.state is WorkState.QUEUED for item in changed)


def test_planner_rejects_cycles_before_enqueueing() -> None:
    """A malformed dependency graph has no partial queue side effect."""
    request = _request()
    queue = InMemoryMetricRunQueue()

    with pytest.raises(ValueError, match="cycle"):
        enqueue_targeted_recalculation(queue, request, {"margin": ("streak",), "streak": ("margin",)})

    assert queue.items() == ()


def test_planner_requires_issuer_scope_and_canonicalizes_selection_order() -> None:
    """Only server-derived issuer scope is accepted and selection order is stable."""
    first_issuer, second_issuer = sorted((uuid4(), uuid4()), key=str)
    first_period, second_period = sorted((uuid4(), uuid4()), key=str)
    scope = AuthorizationScope(
        uuid4(),
        "tenant-a",
        "subject-a",
        frozenset(),
        frozenset({first_issuer, second_issuer}),
    )
    request = _request(
        scope=scope,
        issuer_ids=(second_issuer, first_issuer),
        fiscal_period_ids=(second_period, first_period),
    )
    targets = plan_recalculation_targets(request, {})

    assert [(target.issuer_id, target.fiscal_period_id) for target in targets] == [
        (first_issuer, first_period),
        (first_issuer, second_period),
        (second_issuer, first_period),
        (second_issuer, second_period),
    ]

    unauthorized = _request(issuer_ids=(uuid4(),))
    with pytest.raises(AuthorizationError):
        plan_recalculation_targets(unauthorized, {})


def test_planner_deduplicates_dependency_edges_and_bounds_graph_input() -> None:
    """Duplicate edges do not mimic cycles and one metric cannot provide unbounded edges."""
    request = _request()
    targets = plan_recalculation_targets(request, {"streak": ("margin", "margin")})
    assert [target.metric_id for target in targets] == ["margin", "streak"]

    oversized = {"streak": tuple(f"metric-{index}" for index in range(1025))}
    with pytest.raises(ValueError, match="too large"):
        plan_recalculation_targets(request, oversized)

    unrelated = {f"metric-{index}": () for index in range(1025)}
    assert [target.metric_id for target in plan_recalculation_targets(request, unrelated)] == ["margin"]


def test_planner_rejects_missing_dependent_definition_identity() -> None:
    """Every queued metric must carry its own version and content hash."""
    request = _request(definition_identities={"margin": ("2", "hash-margin-2")})

    with pytest.raises(ValueError, match="cover every affected metric"):
        plan_recalculation_targets(request, {"streak": ("margin",)})


def test_idempotency_key_encodes_fields_without_delimiter_collisions() -> None:
    """Colon-containing definition fields remain distinct calculation identities."""
    request = _request(
        definition_identities={"margin": ("2:3", "hash:2")},
        source_snapshot_hash="snapshot:2",
    )
    target = plan_recalculation_targets(request, {})[0]
    other = replace(target, definition_version="2", definition_hash="3:hash:2")

    assert target.idempotency_key != other.idempotency_key


def _historical_definition(version: int, owner_id) -> MetricDefinitionVersion:
    """Build one registry definition for historical-selection tests."""
    return MetricDefinitionVersion(
        metric_id="margin",
        tenant_id="tenant-a",
        version=version,
        expression="revenue / operating_income",
        content_hash=f"margin-hash-{version}",
        output_unit="ratio",
        state="draft",
        created_by=owner_id,
        created_at=datetime(2025, version, 1, tzinfo=timezone.utc),
    )


def _historical_observation(
    version: int,
    *,
    issuer_id,
    fiscal_period_id,
    analysis_run_id,
    value: str = "0.20",
) -> MetricObservation:
    """Build one observation pinned to a fixed version and calculation identity."""
    return MetricObservation(
        id=uuid4(),
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        fiscal_period_id=fiscal_period_id,
        metric_id="margin",
        definition_version=str(version),
        definition_hash=f"margin-hash-{version}",
        definition_state="active",
        calculation_version="calc-1",
        source_snapshot_hash=f"snapshot-{version}",
        analysis_run_id=analysis_run_id,
        value=Decimal(value),
        quality_state=QualityState.VERIFIED,
        freshness="current",
        provenance=(
            Provenance(
                uuid4(),
                uuid4(),
                "000001-25-000001",
                "https://sec.test/source",
                "Revenue",
                datetime(2025, 5, 1, tzinfo=timezone.utc),
            ),
        ),
        calculated_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
    )


def test_selects_active_default_and_explicit_historical_version() -> None:
    """Default reads use the newest active version while explicit reads preserve history."""
    owner_id = uuid4()
    issuer_id = uuid4()
    fiscal_period_id = uuid4()
    analysis_run_id = uuid4()
    scope = AuthorizationScope(owner_id, "tenant-a", "subject-a", frozenset(), frozenset({issuer_id}))
    registry = MetricRegistry()
    for version in (1, 2):
        registry.add_version(_historical_definition(version, owner_id), scope=scope)
        registry.activate("margin", version=version, scope=scope)
    observations = (
        _historical_observation(
            1,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        ),
        _historical_observation(
            2,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        ),
    )

    assert (
        select_versioned_observation(
            registry,
            observations,
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )
        is observations[1]
    )
    assert (
        select_versioned_observation(
            registry,
            observations,
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
            definition_version="1",
        )
        is observations[0]
    )


def test_rejects_hash_conflicts_and_unauthorized_historical_reads() -> None:
    """Versioned reads reject corrupt content and never bypass issuer scope."""
    owner_id = uuid4()
    issuer_id = uuid4()
    fiscal_period_id = uuid4()
    analysis_run_id = uuid4()
    scope = AuthorizationScope(owner_id, "tenant-a", "subject-a", frozenset(), frozenset({issuer_id}))
    registry = MetricRegistry()
    registry.add_version(_historical_definition(1, owner_id), scope=scope)
    registry.activate("margin", version=1, scope=scope)
    observation = _historical_observation(
        1,
        issuer_id=issuer_id,
        fiscal_period_id=fiscal_period_id,
        analysis_run_id=analysis_run_id,
    )
    with pytest.raises(ValueError, match="hash"):
        select_versioned_observation(
            registry,
            (replace(observation, definition_hash="tampered"),),
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )

    assert (
        select_versioned_observation(
            registry,
            (observation, observation),
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )
        is observation
    )
    with pytest.raises(ValueError, match="identity"):
        select_versioned_observation(
            registry,
            (observation, replace(observation, source_snapshot_hash="other")),
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )
    with pytest.raises(ValueError, match="calculation identity"):
        select_versioned_observation(
            registry,
            (observation, replace(observation, value=Decimal("0.21"))),
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )

    with pytest.raises(ValueError, match="positive integer"):
        select_versioned_observation(
            registry,
            (observation,),
            metric_id="margin",
            scope=scope,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
            definition_version=1.9,
        )

    with pytest.raises(AuthorizationError):
        select_versioned_observation(
            registry,
            (observation,),
            metric_id="margin",
            scope=scope,
            issuer_id=uuid4(),
            fiscal_period_id=fiscal_period_id,
            analysis_run_id=analysis_run_id,
        )
