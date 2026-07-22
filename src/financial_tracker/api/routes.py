"""HTTP routes for the filing-backed financial tracker MVP."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from financial_tracker.runtime import FinancialTrackerRuntime


class MetricDefinitionRequest(BaseModel):
    """Request body for a restricted declarative metric definition."""

    metric_id: str = Field(min_length=1, max_length=100)
    expression: str = Field(min_length=1, max_length=500)
    approved_inputs: dict[str, str] = Field(default_factory=dict)
    input_values: dict[str, Decimal | int | float] = Field(default_factory=dict)
    output_unit: str = Field(min_length=1, max_length=20)


def build_router(runtime: FinancialTrackerRuntime) -> APIRouter:
    """Create routes bound to one server-owned runtime."""
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        """Return readiness only when the local database is reachable."""
        try:
            return runtime.health()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="financial tracker is not ready") from exc

    @router.post("/api/v1/refresh/{ticker}")
    def refresh(ticker: str) -> dict[str, Any]:
        """Run one explicit filing refresh; no background scheduler is implied."""
        try:
            return asdict(runtime.refresh(ticker))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail="SEC refresh failed") from exc

    @router.get("/api/v1/dashboard")
    def dashboard(ticker: str | None = Query(default=None, min_length=1, max_length=10)) -> list[dict[str, Any]]:
        """Return latest filing-backed results for the saved local universe."""
        try:
            return runtime.dashboard(ticker)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="dashboard data is unavailable") from exc

    @router.get("/api/v1/companies/{ticker}/history")
    def company_history(ticker: str) -> list[dict[str, Any]]:
        """Return quarter-aligned history with gaps and provenance labels intact."""
        try:
            return runtime.history(ticker)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="company history is unavailable") from exc

    @router.get("/api/v1/universes")
    def universes() -> list[dict[str, Any]]:
        """Return the saved filing-backed watchlist and portfolio summaries."""
        try:
            return runtime.universes()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="universe data is unavailable") from exc

    @router.post("/api/v1/metric-definitions/dry-run")
    def metric_dry_run(request: MetricDefinitionRequest) -> dict[str, Any]:
        """Validate and evaluate one user-defined metric without activation."""
        api, connection = runtime.metric_api()
        try:
            response = api.dry_run(
                metric_id=request.metric_id,
                expression=request.expression,
                approved_inputs=request.approved_inputs,
                input_values=request.input_values,
                output_unit=request.output_unit,
                scope=runtime.scope(),
            )
            return _metric_response(response)
        finally:
            connection.close()

    @router.post("/api/v1/metric-definitions/activate")
    def metric_activate(request: MetricDefinitionRequest) -> dict[str, Any]:
        """Validate and activate one user-defined metric version."""
        api, connection = runtime.metric_api()
        try:
            response = api.activate(
                metric_id=request.metric_id,
                expression=request.expression,
                approved_inputs=request.approved_inputs,
                input_values=request.input_values,
                output_unit=request.output_unit,
                scope=runtime.scope(),
                created_at=datetime.now(timezone.utc),
            )
            return _metric_response(response)
        finally:
            connection.close()

    @router.delete("/api/v1/metric-definitions/{metric_id}")
    def metric_retire(metric_id: str) -> dict[str, Any]:
        """Retire an authorized metric while preserving its version history."""
        api, connection = runtime.metric_api()
        try:
            return _metric_response(api.retire(metric_id, scope=runtime.scope()))
        finally:
            connection.close()

    @router.get("/api/v1/metric-definitions/{metric_id}/history")
    def metric_history(metric_id: str) -> list[dict[str, Any]]:
        """Return immutable metric-definition versions in ascending order."""
        api, connection = runtime.metric_api()
        try:
            return [
                {
                    "metric_id": item.metric_id,
                    "version": item.version,
                    "expression": item.expression,
                    "content_hash": item.content_hash,
                    "output_unit": item.output_unit,
                    "state": item.state,
                    "created_at": item.created_at.isoformat(),
                }
                for item in api.history(metric_id, scope=runtime.scope())
            ]
        finally:
            connection.close()

    return router


def _metric_response(response: Any) -> dict[str, Any]:
    """Map the bounded metric API response to JSON-safe values."""
    return {
        "metric_id": response.metric_id,
        "valid": response.valid,
        "version": response.version,
        "content_hash": response.content_hash,
        "state": response.state,
        "resolved_inputs": [[key, str(value)] for key, value in response.resolved_inputs],
        "dependency_graph": [[key, list(value)] for key, value in response.dependency_graph],
        "result": str(response.result) if response.result is not None else None,
        "errors": list(response.errors),
        "error_code": response.error_code,
        "correlation_id": response.correlation_id,
    }
