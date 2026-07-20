"""Fixtures for financial tracker tests that require a real PostgreSQL backend."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

DATABASE_URL_ENV = "FINANCIAL_TRACKER_TEST_DATABASE_URL"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "src" / "financial_tracker" / "persistence" / "migrations"

pytestmark = pytest.mark.postgres


def pytest_configure(config: pytest.Config) -> None:
    """Register the marker used by tests that require live PostgreSQL."""
    config.addinivalue_line("markers", "postgres: requires a real PostgreSQL instance")


@pytest.fixture(scope="session")
def financial_tracker_database_url() -> str:
    """Return the configured PostgreSQL URL or skip live-backend tests explicitly."""
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        pytest.skip(f"set {DATABASE_URL_ENV} to run live PostgreSQL tests")
    return database_url


@pytest.fixture(scope="session")
def postgres_connection(financial_tracker_database_url: str) -> Iterator[Any]:
    """Yield one real PostgreSQL connection for the test session."""
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(financial_tracker_database_url, connect_timeout=5) as connection:
        yield connection


@pytest.fixture(scope="session")
def financial_tracker_migrations_dir() -> Path:
    """Return the canonical migration directory used by future integration tests."""
    return MIGRATIONS_DIR
