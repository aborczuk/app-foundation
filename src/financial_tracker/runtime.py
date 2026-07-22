"""Small local runtime that connects the existing tracker seams to the MVP app."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import httpx

from financial_tracker.api.metric_definitions import MetricDefinitionAPI
from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.metrics.registry import PostgresMetricRegistry
from financial_tracker.persistence.models import Filing, FinancialFact, QualityState
from financial_tracker.sec.adapter import SECDiscoveryAdapter, SECRequestPolicy
from financial_tracker.sec.companyfacts import CompanyFactPoint, select_latest_revenue
from financial_tracker.sec.refresh import FilingRefreshCoordinator, FilingRefreshRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIR = Path(__file__).resolve().parent / "persistence" / "migrations"
AAPL_CIK = "0000320193"
AAPL_TICKER = "AAPL"
AAPL_NAME = "Apple Inc."
TENANT_ID = "local"
SUBJECT_ID = "andreborczuk"
USER_ID = uuid5(NAMESPACE_URL, "financial-tracker:local:user")
ISSUER_ID = uuid5(NAMESPACE_URL, f"financial-tracker:issuer:{AAPL_CIK}")
PORTFOLIO_ID = uuid5(NAMESPACE_URL, "financial-tracker:local:portfolio")


@dataclass(frozen=True, slots=True)
class RefreshSummary:
    """Bounded response for one explicit issuer refresh."""

    ticker: str
    cik: str
    accession: str
    metric_id: str
    value: str
    unit: str
    fiscal_period: str
    filed_at: str
    source_url: str
    status: str


class FinancialTrackerRuntime:
    """Own database setup, SEC access, and application read contracts."""

    def __init__(
        self,
        *,
        database_url: str,
        sec_identity: str,
        http_client: Any | None = None,
    ) -> None:
        """Bind local persistence and the configured SEC identity."""
        self.database_url = database_url
        self.sec_identity = sec_identity
        self._http_client = http_client
        self._bootstrap_lock = Lock()
        self._bootstrapped = False

    @classmethod
    def from_environment(cls) -> "FinancialTrackerRuntime":
        """Build the local runtime from explicit environment settings."""
        return cls(
            database_url=os.getenv(
                "FINANCIAL_TRACKER_DATABASE_URL",
                os.getenv(
                    "FINANCIAL_TRACKER_TEST_DATABASE_URL",
                    "postgresql://financial_tracker:financial_tracker_dev@localhost:55432/financial_tracker",
                ),
            ),
            sec_identity=os.getenv(
                "FINANCIAL_TRACKER_SEC_IDENTITY",
                "Financial Tracker aborczuk@gmail.com",
            ),
        )

    def health(self) -> dict[str, str]:
        """Verify database connectivity and return a bounded readiness payload."""
        with self._connect() as connection:
            self._ensure_bootstrapped(connection)
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        return {"status": "ok", "database": "ready", "sec_identity": "configured"}

    def refresh(self, ticker: str = AAPL_TICKER) -> RefreshSummary:
        """Fetch one issuer's latest SEC revenue fact and persist its provenance."""
        normalized_ticker = ticker.strip().upper()
        if normalized_ticker != AAPL_TICKER:
            raise ValueError("MVP refresh currently supports AAPL only")
        adapter = SECDiscoveryAdapter(
            policy=SECRequestPolicy(user_agent=self.sec_identity),
            http_client=self._http_client or httpx.Client(),
        )
        submissions = adapter.fetch_submissions(AAPL_CIK)
        point = select_latest_revenue(adapter.fetch_companyfacts(AAPL_CIK))
        metadata = _submission_metadata(submissions, point)
        with self._connect() as connection:
            self._ensure_bootstrapped(connection)
            summary = self._persist_point(connection, point, metadata)
        return summary

    def dashboard(self, ticker: str | None = None) -> list[dict[str, Any]]:
        """Return the latest filing-backed revenue row for each tracked issuer."""
        with self._connect() as connection:
            self._ensure_bootstrapped(connection)
            query = """
                SELECT DISTINCT ON (i.id)
                    i.cik, i.legal_name, COALESCE(t.ticker, ''),
                    fp.fiscal_year, fp.fiscal_quarter, fp.end_date,
                    ff.value, ff.unit, ff.quality_state,
                    f.accession, f.form_type, f.filed_at, f.source_url
                FROM financial_tracker.issuers i
                LEFT JOIN financial_tracker.issuer_tickers t ON t.issuer_id = i.id
                JOIN financial_tracker.financial_facts ff ON ff.issuer_id = i.id
                    AND ff.concept = 'revenue'
                JOIN financial_tracker.filings f ON f.id = ff.filing_id
                LEFT JOIN financial_tracker.fiscal_periods fp ON fp.id = ff.fiscal_period_id
                WHERE (%s::text IS NULL OR t.ticker = %s::text)
                ORDER BY i.id, fp.end_date DESC NULLS LAST, f.filed_at DESC
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (ticker.upper() if ticker else None, ticker.upper() if ticker else None))
                rows = cursor.fetchall()
        return [_dashboard_row(row) for row in rows]

    def history(self, ticker: str = AAPL_TICKER) -> list[dict[str, Any]]:
        """Return quarter-aligned filing-backed revenue history for one ticker."""
        normalized_ticker = ticker.strip().upper()
        with self._connect() as connection:
            self._ensure_bootstrapped(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.ticker, fp.fiscal_year, fp.fiscal_quarter, fp.end_date,
                           ff.value, ff.unit, ff.quality_state, f.accession,
                           f.form_type, f.filed_at, f.source_url
                    FROM financial_tracker.issuer_tickers t
                    JOIN financial_tracker.financial_facts ff ON ff.issuer_id = t.issuer_id
                        AND ff.concept = 'revenue'
                    JOIN financial_tracker.filings f ON f.id = ff.filing_id
                    LEFT JOIN financial_tracker.fiscal_periods fp ON fp.id = ff.fiscal_period_id
                    WHERE t.ticker = %s
                    ORDER BY fp.end_date ASC NULLS LAST, f.filed_at ASC
                    """,
                    (normalized_ticker,),
                )
                rows = cursor.fetchall()
        return [_history_row(row) for row in rows]

    def universes(self) -> list[dict[str, Any]]:
        """Return saved local watchlist and portfolio membership summaries."""
        with self._connect() as connection:
            self._ensure_bootstrapped(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT p.id, p.name, p.kind, COUNT(pm.issuer_id)
                    FROM financial_tracker.portfolios p
                    LEFT JOIN financial_tracker.portfolio_memberships pm ON pm.portfolio_id = p.id
                    WHERE p.owner_id = %s
                    GROUP BY p.id, p.name, p.kind
                    ORDER BY p.name
                    """,
                    (USER_ID,),
                )
                rows = cursor.fetchall()
        return [
            {"id": str(row[0]), "name": row[1], "kind": row[2], "member_count": row[3]}
            for row in rows
        ]

    def metric_api(self) -> tuple[MetricDefinitionAPI, Any]:
        """Open a PostgreSQL metric-definition facade and its connection."""
        connection = self._connect()
        connection.__enter__()
        self._ensure_bootstrapped(connection)
        return MetricDefinitionAPI(PostgresMetricRegistry(connection)), connection

    def scope(self) -> AuthorizationScope:
        """Return the local server-derived scope for the configured user."""
        return AuthorizationScope(
            user_id=USER_ID,
            tenant_id=TENANT_ID,
            subject_id=SUBJECT_ID,
            portfolio_ids=frozenset({PORTFOLIO_ID}),
            issuer_ids=frozenset({ISSUER_ID}),
        )

    def _persist_point(
        self,
        connection: Any,
        point: CompanyFactPoint,
        metadata: Mapping[str, str],
    ) -> RefreshSummary:
        """Persist period, filing, fact, provenance, and refresh work atomically."""
        period_id = uuid5(
            NAMESPACE_URL,
            f"financial-tracker:period:{AAPL_CIK}:{point.start_date}:{point.end_date}:{point.fiscal_period}",
        )
        filing_id = uuid5(NAMESPACE_URL, f"financial-tracker:filing:{point.accession}")
        fact_id = uuid5(NAMESPACE_URL, f"financial-tracker:fact:{point.accession}:revenue")
        provenance_id = uuid5(NAMESPACE_URL, f"financial-tracker:provenance:{point.accession}:revenue")
        now = datetime.now(timezone.utc)
        fiscal_quarter = 4 if point.fiscal_period == "FY" else int(point.fiscal_period[1:])
        filing = Filing(
            id=filing_id,
            issuer_id=ISSUER_ID,
            authority="sec",
            accession=point.accession,
            form_type=point.form_type,
            filed_at=datetime.combine(point.filed_at, time.min, tzinfo=timezone.utc),
            accepted_at=_parse_datetime(metadata.get("acceptanceDateTime")),
            fiscal_period_id=period_id,
            is_amendment=point.form_type.endswith("/A"),
            source_url=metadata["source_url"],
        )
        fact = FinancialFact(
            id=fact_id,
            issuer_id=ISSUER_ID,
            filing_id=filing_id,
            fiscal_period_id=period_id,
            concept="revenue",
            value=point.value,
            unit=point.unit,
            quality_state=QualityState.VERIFIED,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO financial_tracker.fiscal_periods
                    (id, issuer_id, start_date, end_date, fiscal_year, fiscal_quarter, period_kind)
                VALUES (%s, %s, %s, %s, %s, %s, 'quarter')
                ON CONFLICT (issuer_id, start_date, end_date, period_kind) DO NOTHING
                """,
                (period_id, ISSUER_ID, point.start_date, point.end_date, point.fiscal_year, fiscal_quarter),
            )
        FilingRefreshCoordinator(connection).process(
            FilingRefreshRequest(
                tenant_id=TENANT_ID,
                filing=filing,
                facts=(fact,),
                source_snapshot_hash=_snapshot_hash(point),
                changed_concepts=("revenue",),
                tracked_metric_ids=("revenue",),
                metric_dependencies={},
                change_kind="amendment" if filing.is_amendment else "new",
            )
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO financial_tracker.provenance
                    (id, filing_id, accession, source_url, selector, captured_at, source_fact_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (filing_id, selector, source_fact_id) DO NOTHING
                """,
                (provenance_id, filing_id, point.accession, filing.source_url, point.concept, now, fact_id),
            )
        connection.commit()
        return RefreshSummary(
            ticker=AAPL_TICKER,
            cik=AAPL_CIK,
            accession=point.accession,
            metric_id="revenue",
            value=str(point.value),
            unit=point.unit,
            fiscal_period=f"{point.fiscal_year} {point.fiscal_period}",
            filed_at=point.filed_at.isoformat(),
            source_url=filing.source_url,
            status="queued",
        )

    def _connect(self) -> Any:
        """Open one caller-owned PostgreSQL connection."""
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("psycopg is required for the financial tracker app") from exc
        return psycopg.connect(self.database_url, connect_timeout=5)

    def _ensure_bootstrapped(self, connection: Any) -> None:
        """Apply migrations and seed data once before concurrent route reads."""
        if self._bootstrapped:
            return
        with self._bootstrap_lock:
            if not self._bootstrapped:
                self._bootstrap(connection)
                self._bootstrapped = True

    @staticmethod
    def _bootstrap(connection: Any) -> None:
        """Apply idempotent migrations and seed the local AAPL universe."""
        for migration in sorted(MIGRATION_DIR.glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO financial_tracker.users (id, tenant_id, subject_id, role, created_at)
                VALUES (%s, %s, %s, 'analyst', %s)
                ON CONFLICT (tenant_id, subject_id) DO NOTHING
                """,
                (USER_ID, TENANT_ID, SUBJECT_ID, now),
            )
            cursor.execute(
                """
                INSERT INTO financial_tracker.issuers (id, cik, legal_name, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (cik) DO NOTHING
                """,
                (ISSUER_ID, AAPL_CIK, AAPL_NAME, now),
            )
            cursor.execute(
                """
                INSERT INTO financial_tracker.issuer_tickers (issuer_id, ticker, exchange, valid_from)
                VALUES (%s, %s, 'NASDAQ', %s)
                ON CONFLICT (issuer_id, ticker, valid_from) DO NOTHING
                """,
                (ISSUER_ID, AAPL_TICKER, date(1980, 1, 1)),
            )
            cursor.execute(
                """
                INSERT INTO financial_tracker.portfolios (id, owner_id, name, kind, created_at)
                VALUES (%s, %s, 'MVP Portfolio', 'portfolio', %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (PORTFOLIO_ID, USER_ID, now),
            )
            cursor.execute(
                """
                INSERT INTO financial_tracker.portfolio_memberships (portfolio_id, issuer_id, added_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (portfolio_id, issuer_id) DO NOTHING
                """,
                (PORTFOLIO_ID, ISSUER_ID, now),
            )
        connection.commit()


def _submission_metadata(submissions: Mapping[str, Any], point: CompanyFactPoint) -> dict[str, str]:
    """Resolve filing metadata for a company-facts accession."""
    recent = submissions.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", []) if isinstance(recent, Mapping) else []
    index = next((index for index, value in enumerate(accessions) if value == point.accession), None)
    if index is None:
        return {"source_url": _archive_url(point.accession, "")}
    documents = recent.get("primaryDocument", [])
    document = documents[index] if index < len(documents) else ""
    accepted = recent.get("acceptanceDateTime", [])
    acceptance = accepted[index] if index < len(accepted) else ""
    return {"source_url": _archive_url(point.accession, document), "acceptanceDateTime": acceptance}


def _archive_url(accession: str, document: str) -> str:
    """Build the SEC archive URL without exposing raw provider payloads."""
    accession_path = accession.replace("-", "")
    suffix = f"/{document}" if document else ""
    return f"https://www.sec.gov/Archives/edgar/data/320193/{accession_path}{suffix}"


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an SEC acceptance timestamp into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _snapshot_hash(point: CompanyFactPoint) -> str:
    """Create a stable source snapshot identity for one selected fact."""
    payload = json.dumps(
        {
            "accession": point.accession,
            "concept": point.concept,
            "value": str(point.value),
            "start": point.start_date.isoformat(),
            "end": point.end_date.isoformat(),
        },
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dashboard_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """Map one latest dashboard SQL row to a browser-safe response."""
    return {
        "cik": row[0],
        "company_name": row[1],
        "ticker": row[2],
        "fiscal_year": row[3],
        "fiscal_quarter": row[4],
        "period_end": row[5].isoformat() if row[5] else None,
        "metric_id": "revenue",
        "value": str(row[6]),
        "unit": row[7],
        "quality_state": row[8],
        "accession": row[9],
        "form_type": row[10],
        "filed_at": row[11].isoformat() if row[11] else None,
        "source_url": row[12],
        "freshness": "filing-current",
    }


def _history_row(row: tuple[Any, ...]) -> dict[str, Any]:
    """Map one historical revenue SQL row to a browser-safe response."""
    return {
        "ticker": row[0],
        "fiscal_year": row[1],
        "fiscal_quarter": row[2],
        "period_end": row[3].isoformat() if row[3] else None,
        "metric_id": "revenue",
        "value": str(row[4]),
        "unit": row[5],
        "quality_state": row[6],
        "accession": row[7],
        "form_type": row[8],
        "filed_at": row[9].isoformat() if row[9] else None,
        "source_url": row[10],
    }
