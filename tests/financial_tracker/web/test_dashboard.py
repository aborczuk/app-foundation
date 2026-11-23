"""Contract coverage for the authorized dashboard collection read model."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.persistence.models import QualityState

if TYPE_CHECKING:
    from financial_tracker.web.dashboard import DashboardRecord


def _scope(
    user_id: UUID,
    *,
    tenant_id: str = "tenant-a",
    issuer_ids: frozenset[UUID] = frozenset(),
    portfolio_ids: frozenset[UUID] = frozenset(),
) -> AuthorizationScope:
    """Build a server-derived authorization scope for dashboard tests."""
    return AuthorizationScope(user_id, tenant_id, "subject-a", portfolio_ids, issuer_ids)


def _record(
    *,
    tenant_id: str,
    issuer_id: UUID,
    portfolio_id: UUID,
    company_name: str,
    acceleration: str,
    metric_id: str = "operating_margin",
    fiscal_period: str = "2025-Q2",
    improvement_streak: int | None = 2,
    quality_state: QualityState = QualityState.VERIFIED,
) -> "DashboardRecord":
    """Build one dashboard collection record with visible provenance."""
    from financial_tracker.web.dashboard import DashboardRecord

    return DashboardRecord(
        tenant_id=tenant_id,
        issuer_id=issuer_id,
        portfolio_id=portfolio_id,
        company_name=company_name,
        ticker=company_name[:4].upper(),
        metric_id=metric_id,
        fiscal_period=fiscal_period,
        value=Decimal("0.25"),
        acceleration=Decimal(acceleration),
        improvement_streak=improvement_streak,
        quality_state=quality_state,
        freshness="current",
        source_accessions=("0001234567-25-000001",),
        definition_version="v1",
        definition_hash="definition-hash",
        definition_state="active",
        analysis_run_id=uuid4(),
        source_fact_selectors=("us-gaap:Revenue",),
        calculated_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        correlation_id="corr-1",
        history=(Decimal("0.10"), Decimal("0.20"), Decimal("0.25")),
    )


def test_dashboard_filters_sorts_and_preserves_chart_and_provenance_data() -> None:
    """Authorized rows support collection filters and deterministic sorting."""
    from financial_tracker.web.dashboard import DashboardState, render_dashboard

    owner_id = uuid4()
    issuer_a = uuid4()
    issuer_b = uuid4()
    portfolio_id = uuid4()
    scope = _scope(
        owner_id,
        issuer_ids=frozenset({issuer_a, issuer_b}),
        portfolio_ids=frozenset({portfolio_id}),
    )
    records = (
        _record(
            tenant_id="tenant-a",
            issuer_id=issuer_a,
            portfolio_id=portfolio_id,
            company_name="Alpha",
            acceleration="0.05",
        ),
        _record(
            tenant_id="tenant-a",
            issuer_id=issuer_b,
            portfolio_id=portfolio_id,
            company_name="Beta",
            acceleration="0.15",
            quality_state=QualityState.STALE,
        ),
    )

    view = render_dashboard(
        scope,
        records,
        search="a",
        quality_states={QualityState.VERIFIED},
        sort_by="acceleration",
        descending=True,
    )

    assert view.state is DashboardState.READY
    assert [row.company_name for row in view.rows] == ["Alpha"]
    assert view.rows[0].source_accessions == ("0001234567-25-000001",)
    assert view.rows[0].definition_version == "v1"
    assert view.rows[0].definition_hash == "definition-hash"
    assert view.rows[0].definition_state == "active"
    assert view.rows[0].source_fact_selectors == ("us-gaap:Revenue",)
    assert view.rows[0].calculated_at == datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert view.rows[0].correlation_id == "corr-1"
    assert view.rows[0].sparkline == (
        Decimal("0.10"),
        Decimal("0.20"),
        Decimal("0.25"),
    )
    assert view.table_adapter == "tanstack-table"
    assert view.chart_adapter == "recharts"


def test_dashboard_supports_structured_filters_and_canonical_tie_breaking() -> None:
    """Structured collection filters and equal-value sorting are stable."""
    from financial_tracker.web.dashboard import render_dashboard

    owner_id = uuid4()
    issuer_id = uuid4()
    first_portfolio = uuid4()
    second_portfolio = uuid4()
    scope = _scope(
        owner_id,
        issuer_ids=frozenset({issuer_id}),
        portfolio_ids=frozenset({first_portfolio, second_portfolio}),
    )
    first = _record(
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        portfolio_id=first_portfolio,
        company_name="Same Company",
        acceleration="0.10",
        metric_id="revenue_growth",
        fiscal_period="2025-Q1",
        improvement_streak=1,
    )
    second = _record(
        tenant_id="tenant-a",
        issuer_id=issuer_id,
        portfolio_id=second_portfolio,
        company_name="Same Company",
        acceleration="0.10",
        fiscal_period="2025-Q2",
        improvement_streak=2,
    )

    forward = render_dashboard(scope, (first, second), sort_by="acceleration")
    reversed_input = render_dashboard(scope, (second, first), sort_by="acceleration")
    filtered = render_dashboard(
        scope,
        (first, second),
        portfolio_ids={second_portfolio},
        metric_ids={"operating_margin"},
        fiscal_periods={"2025-Q2"},
        acceleration_min=Decimal("0.10"),
        acceleration_max=Decimal("0.10"),
        streak_min=2,
        streak_max=2,
    )

    forward_periods = [row.fiscal_period for row in forward.rows]
    assert forward_periods == [row.fiscal_period for row in reversed_input.rows]
    assert set(forward_periods) == {"2025-Q1", "2025-Q2"}
    assert [row.fiscal_period for row in filtered.rows] == ["2025-Q2"]


def test_dashboard_excludes_records_outside_server_scope() -> None:
    """Tenant and issuer scope prevent unauthorized collection leakage."""
    from financial_tracker.web.dashboard import render_dashboard

    owner_id = uuid4()
    allowed_issuer = uuid4()
    foreign_issuer = uuid4()
    portfolio_id = uuid4()
    scope = _scope(
        owner_id,
        issuer_ids=frozenset({allowed_issuer}),
        portfolio_ids=frozenset({portfolio_id}),
    )
    records = (
        _record(
            tenant_id="tenant-a",
            issuer_id=allowed_issuer,
            portfolio_id=portfolio_id,
            company_name="Allowed",
            acceleration="0.10",
        ),
        _record(
            tenant_id="tenant-b",
            issuer_id=foreign_issuer,
            portfolio_id=portfolio_id,
            company_name="Foreign",
            acceleration="0.90",
        ),
    )

    view = render_dashboard(scope, records)

    assert [row.company_name for row in view.rows] == ["Allowed"]


def test_dashboard_has_explicit_loading_empty_and_error_states() -> None:
    """Server-rendered state responses never masquerade as an empty success."""
    from financial_tracker.web.dashboard import DashboardState, render_dashboard

    scope = _scope(uuid4())

    loading = render_dashboard(scope, (), state=DashboardState.LOADING)
    empty = render_dashboard(scope, ())
    error = render_dashboard(
        scope,
        (),
        state=DashboardState.ERROR,
        error_message="SEC retrieval failed",
    )

    assert loading.state is DashboardState.LOADING
    assert loading.rows == ()
    assert empty.state is DashboardState.EMPTY
    assert empty.empty_message == "No authorized results"
    assert error.state is DashboardState.ERROR
    assert error.error_message == "SEC retrieval failed"
