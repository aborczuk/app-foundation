"""Live PostgreSQL coverage for immutable metric-definition persistence."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from financial_tracker.calculation.observations import MetricObservation
from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.metrics.registry import (
    MetricDefinitionVersion,
    PostgresMetricRegistry,
)
from financial_tracker.persistence.models import Provenance, QualityState
from financial_tracker.recalculation.metric_runs import select_versioned_observation

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "financial_tracker"
    / "persistence"
    / "migrations"
)


def _require_database_url() -> str:
    """Return the configured live-test database URL or skip explicitly."""
    database_url = os.getenv("FINANCIAL_TRACKER_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set FINANCIAL_TRACKER_TEST_DATABASE_URL to run live PostgreSQL tests")
    return database_url


def _load_psycopg():
    """Load psycopg only when the live integration path is requested."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required when live PostgreSQL tests are enabled") from exc
    return psycopg


@pytest.fixture()
def postgres_connection():
    """Yield one real PostgreSQL connection for the registry scenario."""
    psycopg = _load_psycopg()
    with psycopg.connect(_require_database_url(), connect_timeout=5) as connection:
        yield connection


def _reset_schema(connection) -> None:
    """Reset the disposable live schema and apply all current migrations."""
    with connection.cursor() as cursor:
        cursor.execute("DROP SCHEMA IF EXISTS financial_tracker CASCADE")
        for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            cursor.execute(migration_path.read_text(encoding="utf-8"))
    connection.commit()


def test_metric_definition_persists_and_enforces_owner_scope(postgres_connection) -> None:
    """A fresh registry reads persisted content, honors scope, and selects active history."""
    _reset_schema(postgres_connection)
    now = datetime(2025, 5, 1, tzinfo=timezone.utc)
    owner_id = uuid4()
    peer_id = uuid4()
    tenant_id = "tenant-metric-live"
    with postgres_connection.cursor() as cursor:
        for user_id, subject_id in ((owner_id, "owner"), (peer_id, "peer")):
            cursor.execute(
                """
                INSERT INTO financial_tracker.users (id, tenant_id, subject_id, role, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, tenant_id, subject_id, "analyst", now),
            )
    postgres_connection.commit()

    definition = MetricDefinitionVersion(
        metric_id="custom_margin",
        tenant_id=tenant_id,
        version=1,
        expression="revenue / operating_income",
        content_hash="custom-margin-live-v1",
        output_unit="ratio",
        state="draft",
        created_by=owner_id,
        created_at=now,
    )
    owner_scope = AuthorizationScope(owner_id, tenant_id, "owner", frozenset(), frozenset())
    peer_scope = AuthorizationScope(peer_id, tenant_id, "peer", frozenset(), frozenset())
    with pytest.raises(AuthorizationError):
        PostgresMetricRegistry(postgres_connection).add_and_activate(
            definition, scope=peer_scope
        )

    registry = PostgresMetricRegistry(postgres_connection)
    registry.add_and_activate(definition, scope=owner_scope)
    persisted = PostgresMetricRegistry(postgres_connection).get_version(
        "custom_margin", version=1, scope=owner_scope
    )
    assert persisted.content_hash == definition.content_hash
    assert persisted.state == "active"
    issuer_id = uuid4()
    fiscal_period_id = uuid4()
    analysis_run_id = uuid4()
    observation = MetricObservation(
        id=uuid4(),
        tenant_id=tenant_id,
        issuer_id=issuer_id,
        fiscal_period_id=fiscal_period_id,
        metric_id="custom_margin",
        definition_version="1",
        definition_hash=definition.content_hash,
        definition_state="active",
        calculation_version="calc-1",
        source_snapshot_hash="snapshot-live-v1",
        analysis_run_id=analysis_run_id,
        value=Decimal("0.20"),
        quality_state=QualityState.VERIFIED,
        freshness="current",
        provenance=(
            Provenance(
                uuid4(),
                uuid4(),
                "000001-25-000001",
                "https://sec.test/source",
                "Revenue",
                now,
            ),
        ),
        calculated_at=now,
    )
    selected = select_versioned_observation(
        PostgresMetricRegistry(postgres_connection),
        (observation,),
        metric_id="custom_margin",
        scope=AuthorizationScope(
            owner_id,
            tenant_id,
            "owner",
            frozenset(),
            frozenset({issuer_id}),
        ),
        issuer_id=issuer_id,
        fiscal_period_id=fiscal_period_id,
        analysis_run_id=analysis_run_id,
    )
    assert selected is observation
