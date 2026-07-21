"""Dependency-aware metric recalculation work planning and enqueueing."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationScope, require_issuer_access
from financial_tracker.metrics.registry import MetricDefinitionVersion
from financial_tracker.work.state import WorkItem

_MAX_DEPENDENCY_NODES = 1024
RECALCULATION_WORK_KIND = "metric_recalculation"


class RecalculationQueue(Protocol):
    """Minimal queue boundary consumed by the targeted planner."""

    def enqueue(self, target: "MetricRecalculationTarget") -> WorkItem:
        """Enqueue one target and return its durable work-item projection."""
        ...


class DefinitionSelectionSource(Protocol):
    """Registry read boundary required for versioned observation selection."""

    def active_version(
        self,
        metric_id: str,
        *,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion | None:
        """Return the current active definition for one authorized metric."""
        ...

    def get_version(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Return one explicitly requested definition version."""
        ...


@dataclass(frozen=True, slots=True)
class MetricRecalculationRequest:
    """One source or definition change to recalculate for selected entities."""

    scope: AuthorizationScope
    root_metric_id: str
    definition_identities: Mapping[str, tuple[str, str]]
    issuer_ids: tuple[UUID, ...]
    fiscal_period_ids: tuple[UUID, ...]
    source_snapshot_hash: str
    as_of_policy: str = "latest"

    def __post_init__(self) -> None:
        """Reject requests that cannot produce stable work identities."""
        for field_name in (
            "root_metric_id",
            "source_snapshot_hash",
            "as_of_policy",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")
        if self.root_metric_id not in self.definition_identities:
            raise ValueError("definition_identities must include root_metric_id")
        if any(
            not isinstance(metric_id, str)
            or not metric_id.strip()
            or not isinstance(identity, tuple)
            or len(identity) != 2
            or any(not isinstance(value, str) or not value.strip() for value in identity)
            for metric_id, identity in self.definition_identities.items()
        ):
            raise ValueError("definition_identities must map metrics to (version, hash)")
        if not self.issuer_ids or not self.fiscal_period_ids:
            raise ValueError("recalculation request requires issuers and fiscal periods")
        if len(set(self.issuer_ids)) != len(self.issuer_ids):
            raise ValueError("issuer_ids must be unique")
        if len(set(self.fiscal_period_ids)) != len(self.fiscal_period_ids):
            raise ValueError("fiscal_period_ids must be unique")


@dataclass(frozen=True, slots=True)
class MetricRecalculationTarget:
    """One metric/entity/period calculation with a stable retry identity."""

    tenant_id: str
    issuer_id: UUID
    fiscal_period_id: UUID
    metric_id: str
    definition_version: str
    definition_hash: str
    source_snapshot_hash: str
    as_of_policy: str

    def __post_init__(self) -> None:
        """Reject target fields that would make retries ambiguous."""
        for field_name in (
            "tenant_id",
            "metric_id",
            "definition_version",
            "definition_hash",
            "source_snapshot_hash",
            "as_of_policy",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be non-empty")

    @property
    def idempotency_key(self) -> str:
        """Return the calculation identity used by the durable work table."""
        fields = (
            self.issuer_id,
            self.fiscal_period_id,
            self.metric_id,
            self.definition_version,
            self.definition_hash,
            self.source_snapshot_hash,
            self.as_of_policy,
        )
        serialized = json.dumps(
            [str(field) for field in fields],
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return "metric-recalculation:" + serialized


def plan_recalculation_targets(
    request: MetricRecalculationRequest,
    dependency_graph: Mapping[str, Sequence[str]],
) -> tuple[MetricRecalculationTarget, ...]:
    """Plan the root metric and every transitively affected dependent metric."""
    for issuer_id in request.issuer_ids:
        require_issuer_access(request.scope, issuer_id)
    affected_metrics = _affected_metrics(request.root_metric_id, dependency_graph)
    missing_identities = affected_metrics.difference(request.definition_identities)
    if missing_identities:
        raise ValueError("definition_identities must cover every affected metric")
    ordered_metrics = _dependency_order(affected_metrics, dependency_graph)
    return tuple(
        MetricRecalculationTarget(
            tenant_id=request.scope.tenant_id,
            issuer_id=issuer_id,
            fiscal_period_id=fiscal_period_id,
            metric_id=metric_id,
            definition_version=request.definition_identities[metric_id][0],
            definition_hash=request.definition_identities[metric_id][1],
            source_snapshot_hash=request.source_snapshot_hash,
            as_of_policy=request.as_of_policy,
        )
        for issuer_id in sorted(request.issuer_ids, key=str)
        for fiscal_period_id in sorted(request.fiscal_period_ids, key=str)
        for metric_id in ordered_metrics
    )


def enqueue_targeted_recalculation(
    queue: RecalculationQueue,
    request: MetricRecalculationRequest,
    dependency_graph: Mapping[str, Sequence[str]],
) -> tuple[WorkItem, ...]:
    """Plan affected metrics and enqueue each target through the queue boundary."""
    return tuple(queue.enqueue(target) for target in plan_recalculation_targets(request, dependency_graph))


def select_versioned_observation(
    registry: DefinitionSelectionSource,
    observations: Iterable[MetricObservation],
    *,
    metric_id: str,
    scope: AuthorizationScope,
    issuer_id: UUID,
    fiscal_period_id: UUID,
    analysis_run_id: UUID,
    definition_version: int | str | float | None = None,
) -> MetricObservation | None:
    """Select active-default or explicit historical output without mixing versions."""
    require_issuer_access(scope, issuer_id)
    definition = _resolve_definition(
        registry,
        metric_id,
        scope=scope,
        definition_version=definition_version,
    )
    if definition is None:
        return None
    matches = tuple(
        observation
        for observation in observations
        if (
            observation.tenant_id == scope.tenant_id
            and observation.issuer_id == issuer_id
            and observation.fiscal_period_id == fiscal_period_id
            and observation.metric_id == metric_id
            and observation.definition_version == str(definition.version)
            and observation.analysis_run_id == analysis_run_id
        )
    )
    if not matches:
        return None
    first = matches[0]
    if any(item.definition_hash != definition.content_hash for item in matches):
        raise ValueError("observation definition hash does not match the selected version")
    if any(item.identity_key != first.identity_key for item in matches[1:]):
        raise ValueError("multiple observations conflict for one calculation identity")
    if any(item.content_key != first.content_key for item in matches[1:]):
        raise ValueError("multiple observations conflict for one calculation identity")
    return first


def _resolve_definition(
    registry: DefinitionSelectionSource,
    metric_id: str,
    *,
    scope: AuthorizationScope,
    definition_version: int | str | float | None,
) -> MetricDefinitionVersion | None:
    """Resolve either the authorized active definition or one historical version."""
    if definition_version is None:
        return registry.active_version(metric_id, scope=scope)
    if isinstance(definition_version, bool) or not isinstance(definition_version, (int, str)):
        raise ValueError("definition_version must be a positive integer")
    if isinstance(definition_version, str):
        candidate = definition_version.strip()
        if not candidate.isdecimal():
            raise ValueError("definition_version must be a positive integer")
        version = int(candidate)
    else:
        version = definition_version
    if version < 1:
        raise ValueError("definition_version must be a positive integer")
    return registry.get_version(metric_id, version=version, scope=scope)


class InMemoryMetricRunQueue:
    """Idempotent queue reference implementation used by unit and contract tests."""

    def __init__(self) -> None:
        """Create an empty queue projection keyed by tenant and work identity."""
        self._items: dict[tuple[str, str], WorkItem] = {}
        self._targets: dict[tuple[str, str], MetricRecalculationTarget] = {}

    def enqueue(self, target: MetricRecalculationTarget) -> WorkItem:
        """Return an existing item for a retry or create one queued work item."""
        key = (target.tenant_id, target.idempotency_key)
        existing = self._items.get(key)
        if existing is not None:
            if self._targets[key] != target:
                raise ValueError("recalculation idempotency key collision")
            return existing
        item = WorkItem(
            id=uuid4(),
            tenant_id=target.tenant_id,
            idempotency_key=target.idempotency_key,
            kind=RECALCULATION_WORK_KIND,
        )
        self._items[key] = item
        self._targets[key] = target
        return item

    def items(self) -> tuple[WorkItem, ...]:
        """Return queued work in deterministic idempotency-key order."""
        return tuple(self._items[key] for key in sorted(self._items))

    def target_for(self, item: WorkItem) -> MetricRecalculationTarget:
        """Return the target payload associated with one queued item."""
        key = (item.tenant_id, item.idempotency_key)
        return self._targets[key]


def _affected_metrics(root: str, graph: Mapping[str, Sequence[str]]) -> frozenset[str]:
    """Find the root and all metrics that depend on it without recursion."""
    reverse: dict[str, set[str]] = defaultdict(set)
    for metric_id, dependencies in graph.items():
        for dependency in _bounded_unique_dependencies(dependencies):
            reverse[dependency].add(metric_id)
    affected = {root}
    pending = deque([root])
    while pending:
        metric_id = pending.popleft()
        for dependent in sorted(reverse.get(metric_id, ())):
            if dependent not in affected:
                affected.add(dependent)
                if len(affected) > _MAX_DEPENDENCY_NODES:
                    raise ValueError("dependency graph is too large")
                pending.append(dependent)
    return frozenset(affected)


def _dependency_order(metrics: frozenset[str], graph: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """Return affected metrics in dependency-first order and reject cycles."""
    dependents: dict[str, set[str]] = defaultdict(set)
    indegree = {metric_id: 0 for metric_id in metrics}
    for metric_id in metrics:
        for dependency in _bounded_unique_dependencies(graph.get(metric_id, ())):
            if dependency in metrics:
                dependents[dependency].add(metric_id)
                indegree[metric_id] += 1
    pending = [metric_id for metric_id, degree in indegree.items() if degree == 0]
    pending.sort()
    ordered: list[str] = []
    while pending:
        metric_id = pending.pop(0)
        ordered.append(metric_id)
        for dependent in sorted(dependents.get(metric_id, ())):
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                pending.append(dependent)
                pending.sort()
    if len(ordered) != len(metrics):
        raise ValueError("dependency graph contains a cycle")
    return tuple(ordered)


def _bounded_unique_dependencies(dependencies: Sequence[str]) -> frozenset[str]:
    """Read at most the supported dependency edge budget from one metric."""
    iterator = iter(dependencies)
    unique: set[str] = set()
    for _ in range(_MAX_DEPENDENCY_NODES):
        try:
            unique.add(next(iterator))
        except StopIteration:
            return frozenset(unique)
    try:
        next(iterator)
    except StopIteration:
        return frozenset(unique)
    raise ValueError("dependency graph is too large")
