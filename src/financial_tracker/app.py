"""FastAPI entrypoint for the local financial tracker MVP."""

from __future__ import annotations

from fastapi import FastAPI

from financial_tracker.api.routes import build_router
from financial_tracker.runtime import FinancialTrackerRuntime


def create_app(runtime: FinancialTrackerRuntime | None = None) -> FastAPI:
    """Create the app with a replaceable runtime for seam-level testing."""
    bound_runtime = runtime or FinancialTrackerRuntime.from_environment()
    app = FastAPI(title="Financial Acceleration Tracker", version="0.1.0")
    app.include_router(build_router(bound_runtime))
    return app


app = create_app()
