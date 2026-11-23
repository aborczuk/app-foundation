"""Route-contract tests for the filing-backed local application boundary."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from fastapi.testclient import TestClient

from financial_tracker.app import create_app
from financial_tracker.runtime import FinancialTrackerRuntime, RefreshSummary


class FakeRuntime:
    """Provide deterministic route responses without replacing persistence tests."""

    def health(self) -> dict[str, str]:
        """Return the readiness payload used by the health route."""
        return {"status": "ok", "database": "ready", "sec_identity": "configured"}

    def refresh(self, ticker: str) -> RefreshSummary:
        """Return a representative explicit refresh result."""
        return RefreshSummary(
            ticker=ticker.upper(),
            cik="0000320193",
            accession="0000320193-26-000001",
            metric_id="revenue",
            value="1000000",
            unit="USD",
            fiscal_period="FY2025",
            filed_at="2026-01-30",
            source_url="https://www.sec.gov/Archives/edgar/data/320193/example.htm",
            status="persisted",
        )

    def dashboard(self, ticker: str | None = None) -> list[dict[str, str | None]]:
        """Return the latest persisted filing-backed row."""
        return [
            {
                "ticker": ticker or "AAPL",
                "company": "Apple Inc.",
                "metric_id": "revenue",
                "value": "1000000",
                "unit": "USD",
                "quality_state": "reported",
                "accession": "0000320193-26-000001",
            }
        ]

    def history(self, ticker: str) -> list[dict[str, str]]:
        """Return two filing-backed observations for the selected ticker."""
        return [
            {"ticker": ticker.upper(), "fiscal_period": "FY2024", "value": "900000"},
            {"ticker": ticker.upper(), "fiscal_period": "FY2025", "value": "1000000"},
        ]

    def universes(self) -> list[dict[str, str | int]]:
        """Return the local watchlist and portfolio summary."""
        return [{"name": "MVP Portfolio", "ticker_count": 1, "holding_count": 1}]

    def metric_api(self) -> tuple["FakeMetricAPI", "FakeConnection"]:
        """Return the metric facade used by the lifecycle route contract."""
        return FakeMetricAPI(), FakeConnection()

    def scope(self) -> object:
        """Return the server-owned scope placeholder for route testing."""
        return object()


class FakeConnection:
    """Track the connection close contract without opening PostgreSQL."""

    def close(self) -> None:
        """Close the fake connection."""


class FakeMetricAPI:
    """Return a JSON-shaped retirement response for the route seam."""

    def retire(self, metric_id: str, *, scope: object) -> SimpleNamespace:
        """Return the retired metric response shape."""
        del scope
        return SimpleNamespace(
            metric_id=metric_id,
            valid=True,
            version=1,
            content_hash="hash",
            state="retired",
            resolved_inputs=(),
            dependency_graph=(),
            result=None,
            errors=(),
            error_code=None,
            correlation_id="test-correlation",
        )


def test_application_read_and_refresh_routes_share_filing_contract() -> None:
    """Verify the browser-facing routes expose one coherent filing-backed seam."""
    client = TestClient(create_app(cast(FinancialTrackerRuntime, FakeRuntime())))

    assert client.get("/health").json()["status"] == "ok"

    refresh = client.post("/api/v1/refresh/AAPL")
    assert refresh.status_code == 200
    assert refresh.json()["accession"] == "0000320193-26-000001"

    dashboard = client.get("/api/v1/dashboard?ticker=AAPL")
    assert dashboard.status_code == 200
    assert dashboard.json()[0]["quality_state"] == "reported"

    history = client.get("/api/v1/companies/AAPL/history")
    assert history.json()[-1]["fiscal_period"] == "FY2025"

    universes = client.get("/api/v1/universes")
    assert universes.json()[0]["holding_count"] == 1

    retired = client.delete("/api/v1/metric-definitions/revenue")
    assert retired.status_code == 200
    assert retired.json()["state"] == "retired"
