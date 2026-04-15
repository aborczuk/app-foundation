"""Local no-op telemetry client for Chroma."""

from __future__ import annotations

from chromadb.telemetry.product import ProductTelemetryClient, ProductTelemetryEvent
from overrides import override


class NoOpProductTelemetry(ProductTelemetryClient):
    """Suppress Chroma product telemetry without changing index behavior."""

    @override
    def capture(self, event: ProductTelemetryEvent) -> None:  # pragma: no cover - explicit no-op
        """Intentionally drop all Chroma telemetry events."""
        return None
