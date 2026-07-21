"""Transactional SEC filing refresh and targeted recalculation coordination."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from financial_tracker.persistence.models import Filing, FinancialFact


@dataclass(frozen=True, slots=True)
class FilingRefreshRequest:
    """One immutable filing delivery and its metric impact context."""

    tenant_id: str
    filing: Filing
    facts: tuple[FinancialFact, ...]
    source_snapshot_hash: str
    changed_concepts: tuple[str, ...]
    tracked_metric_ids: tuple[str, ...]
    metric_dependencies: Mapping[str, tuple[str, ...]]
    change_kind: str = "new"

    def __post_init__(self) -> None:
        """Reject refresh requests that cannot produce stable work identities."""
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if not self.source_snapshot_hash.strip():
            raise ValueError("source_snapshot_hash must be non-empty")
        if self.change_kind not in {"new", "amendment", "restatement"}:
            raise ValueError("change_kind must be new, amendment, or restatement")
        if len(set(self.tracked_metric_ids)) != len(self.tracked_metric_ids):
            raise ValueError("tracked_metric_ids must be unique")


@dataclass(frozen=True, slots=True)
class FilingRefreshResult:
    """Outcome of one filing delivery transaction."""

    status: str
    filing_id: UUID
    enqueued_metric_ids: tuple[str, ...]
    work_item_ids: tuple[UUID, ...]
    change_kind: str


class FilingRefreshCoordinator:
    """Persist filing data and enqueue only impacted metric work items."""

    def __init__(self, connection: Any) -> None:
        """Bind the caller-owned PostgreSQL connection for transactional work."""
        self._connection = connection

    def process(self, request: FilingRefreshRequest) -> FilingRefreshResult:
        """Apply one filing delivery atomically and return its durable outcome."""
        affected_metrics = _affected_metric_ids(
            request.changed_concepts,
            request.tracked_metric_ids,
            request.metric_dependencies,
        )
        work_keys = tuple(
            _work_item_key(request.filing.id, metric_id, request.source_snapshot_hash)
            for metric_id in affected_metrics
        )
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM financial_tracker.filings "
                    "WHERE authority = %s AND accession = %s",
                    (request.filing.authority, request.filing.accession),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    work_item_ids = _existing_work_item_ids(
                        cursor, request.tenant_id, work_keys
                    )
                    self._connection.commit()
                    return FilingRefreshResult(
                        status="duplicate",
                        filing_id=_as_uuid(existing[0]),
                        enqueued_metric_ids=affected_metrics,
                        work_item_ids=work_item_ids,
                        change_kind=request.change_kind,
                    )

                _insert_filing(cursor, request.filing)
                _insert_facts(cursor, request.facts)
                work_item_ids = _enqueue_work_items(
                    cursor,
                    request.tenant_id,
                    affected_metrics,
                    work_keys,
                )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return FilingRefreshResult(
            status="queued",
            filing_id=request.filing.id,
            enqueued_metric_ids=affected_metrics,
            work_item_ids=work_item_ids,
            change_kind=request.change_kind,
        )


def _affected_metric_ids(
    changed_concepts: Sequence[str],
    tracked_metric_ids: Sequence[str],
    dependencies: Mapping[str, Sequence[str]],
) -> tuple[str, ...]:
    """Return tracked metrics that directly or transitively depend on changed facts."""
    affected = {concept for concept in changed_concepts if concept}
    changed = True
    while changed:
        changed = False
        for metric_id, metric_dependencies in dependencies.items():
            if metric_id in affected:
                continue
            if any(dependency in affected for dependency in metric_dependencies):
                affected.add(metric_id)
                changed = True
    return tuple(dict.fromkeys(metric_id for metric_id in tracked_metric_ids if metric_id in affected))


def _insert_filing(cursor: Any, filing: Filing) -> None:
    """Insert one immutable filing snapshot with its amendment lineage."""
    cursor.execute(
        "INSERT INTO financial_tracker.filings "
        "(id, issuer_id, authority, accession, form_type, filed_at, accepted_at, "
        "fiscal_period_id, is_amendment, source_url, supersedes_filing_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            filing.id,
            filing.issuer_id,
            filing.authority,
            filing.accession,
            filing.form_type,
            filing.filed_at,
            filing.accepted_at,
            filing.fiscal_period_id,
            filing.is_amendment,
            filing.source_url,
            filing.supersedes_filing_id,
        ),
    )


def _insert_facts(cursor: Any, facts: Sequence[FinancialFact]) -> None:
    """Insert exact-decimal facts while preserving source filing identity."""
    for fact in facts:
        quality_state = getattr(fact.quality_state, "value", fact.quality_state)
        cursor.execute(
            "INSERT INTO financial_tracker.financial_facts "
            "(id, issuer_id, filing_id, fiscal_period_id, concept, value, unit, dimensions, quality_state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                fact.id,
                fact.issuer_id,
                fact.filing_id,
                fact.fiscal_period_id,
                fact.concept,
                fact.value,
                fact.unit,
                json.dumps(dict(fact.dimensions), sort_keys=True),
                quality_state,
            ),
        )


def _work_item_key(filing_id: UUID, metric_id: str, snapshot_hash: str) -> str:
    """Build the stable work identity for one filing and affected metric."""
    return f"filing-refresh:{filing_id}:{metric_id}:{snapshot_hash}"


def _enqueue_work_items(
    cursor: Any,
    tenant_id: str,
    metric_ids: Sequence[str],
    work_keys: Sequence[str],
) -> tuple[UUID, ...]:
    """Create or retrieve queued work items in deterministic metric order."""
    work_item_ids: list[UUID] = []
    for metric_id, work_key in zip(metric_ids, work_keys, strict=True):
        del metric_id
        item_id = uuid4()
        cursor.execute(
            "INSERT INTO financial_tracker.work_items "
            "(id, tenant_id, idempotency_key, kind, state, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING id",
            (item_id, tenant_id, work_key, "metric_recalculation", "queued", datetime.now(timezone.utc)),
        )
        inserted = cursor.fetchone()
        if inserted is None:
            cursor.execute(
                "SELECT id FROM financial_tracker.work_items "
                "WHERE tenant_id = %s AND idempotency_key = %s",
                (tenant_id, work_key),
            )
            inserted = cursor.fetchone()
        if inserted is None:
            raise RuntimeError("work item was not inserted or found")
        work_item_ids.append(_as_uuid(inserted[0]))
    return tuple(work_item_ids)


def _existing_work_item_ids(cursor: Any, tenant_id: str, work_keys: Sequence[str]) -> tuple[UUID, ...]:
    """Look up duplicate-delivery work IDs in the same deterministic order."""
    work_item_ids: list[UUID] = []
    for work_key in work_keys:
        cursor.execute(
            "SELECT id FROM financial_tracker.work_items "
            "WHERE tenant_id = %s AND idempotency_key = %s",
            (tenant_id, work_key),
        )
        row = cursor.fetchone()
        if row is not None:
            work_item_ids.append(_as_uuid(row[0]))
    return tuple(work_item_ids)


def _as_uuid(value: Any) -> UUID:
    """Normalize a PostgreSQL UUID value for the typed result contract."""
    return value if isinstance(value, UUID) else UUID(str(value))
