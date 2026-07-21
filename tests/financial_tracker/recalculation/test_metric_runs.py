"""Contract coverage for dependency-aware targeted recalculation enqueueing."""

from dataclasses import replace
from uuid import uuid4

import pytest

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.recalculation.metric_runs import (
    InMemoryMetricRunQueue,
    MetricRecalculationRequest,
    enqueue_targeted_recalculation,
    plan_recalculation_targets,
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
