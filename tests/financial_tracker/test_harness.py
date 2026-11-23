"""Live-backend smoke checks for the financial tracker test harness."""

from __future__ import annotations


def test_postgres_connection_is_live(postgres_connection) -> None:
    """Prove the configured fixture reaches a real PostgreSQL backend."""
    with postgres_connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
