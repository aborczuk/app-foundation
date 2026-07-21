"""Structured callable contract for metric-definition API operations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from financial_tracker.identity.resolver import AuthorizationError, AuthorizationScope
from financial_tracker.metrics.registry import MetricDefinitionVersion
from financial_tracker.metrics.service import (
    MetricDryRunReport,
    MetricLifecycleRegistry,
    activate_metric,
    dry_run_metric,
)


@dataclass(frozen=True, slots=True)
class MetricDefinitionAPIResponse:
    """Bounded response shared by metric-definition clients and adapters."""

    metric_id: str
    valid: bool
    version: int | None
    content_hash: str | None
    state: str | None
    resolved_inputs: tuple[tuple[str, Decimal], ...]
    dependency_graph: tuple[tuple[str, tuple[str, ...]], ...]
    result: Decimal | None
    errors: tuple[str, ...]
    error_code: str | None
    correlation_id: str


class MetricDefinitionAPI:
    """Expose validation, activation, and history without owning domain state."""

    def __init__(self, registry: MetricLifecycleRegistry) -> None:
        """Bind the contract facade to an authorized lifecycle registry."""
        self._registry = registry

    def dry_run(
        self,
        *,
        metric_id: str,
        expression: str,
        approved_inputs: Mapping[str, str],
        input_values: Mapping[str, Decimal | int | float],
        output_unit: str,
        scope: AuthorizationScope,
        dependency_graph: Mapping[str, Sequence[str]] | None = None,
        correlation_id: str | None = None,
    ) -> MetricDefinitionAPIResponse:
        """Validate and evaluate a definition without persisting an active version."""
        report = dry_run_metric(
            self._registry,
            metric_id=metric_id,
            expression=expression,
            approved_inputs=approved_inputs,
            input_values=input_values,
            output_unit=output_unit,
            scope=scope,
            dependency_graph=dependency_graph,
        )
        return _report_response(report, correlation_id=correlation_id)

    def activate(
        self,
        *,
        metric_id: str,
        expression: str,
        approved_inputs: Mapping[str, str],
        input_values: Mapping[str, Decimal | int | float],
        output_unit: str,
        scope: AuthorizationScope,
        dependency_graph: Mapping[str, Sequence[str]] | None = None,
        created_at: datetime,
        correlation_id: str | None = None,
    ) -> MetricDefinitionAPIResponse:
        """Revalidate and activate one definition request through the contract boundary."""
        correlation = correlation_id or str(uuid4())
        report = dry_run_metric(
            self._registry,
            metric_id=metric_id,
            expression=expression,
            approved_inputs=approved_inputs,
            input_values=input_values,
            output_unit=output_unit,
            scope=scope,
            dependency_graph=dependency_graph,
        )
        if not report.valid:
            return _report_response(report, correlation_id=correlation)
        try:
            definition = activate_metric(
                self._registry,
                report,
                scope=scope,
                created_at=created_at,
            )
        except AuthorizationError:
            return _error_response(report.metric_id, "forbidden", correlation)
        except ValueError:
            return _error_response(report.metric_id, "invalid_definition", correlation)
        return _definition_response(definition, correlation)

    def history(self, metric_id: str, *, scope: AuthorizationScope) -> tuple[MetricDefinitionVersion, ...]:
        """Return immutable tenant-scoped definition history in version order."""
        return self._registry.versions(metric_id, scope=scope)


def _report_response(report: MetricDryRunReport, *, correlation_id: str | None) -> MetricDefinitionAPIResponse:
    """Map a bounded dry-run report to the public response contract."""
    return MetricDefinitionAPIResponse(
        metric_id=report.metric_id,
        valid=report.valid,
        version=report.proposed_version,
        content_hash=report.content_hash or None,
        state=None,
        resolved_inputs=report.resolved_inputs,
        dependency_graph=report.dependency_graph,
        result=report.result,
        errors=report.errors,
        error_code=None if report.valid else "invalid_definition",
        correlation_id=correlation_id or str(uuid4()),
    )


def _definition_response(
    definition: MetricDefinitionVersion,
    correlation_id: str,
) -> MetricDefinitionAPIResponse:
    """Map an activated immutable definition to the public response contract."""
    return MetricDefinitionAPIResponse(
        metric_id=definition.metric_id,
        valid=True,
        version=definition.version,
        content_hash=definition.content_hash,
        state=definition.state,
        resolved_inputs=(),
        dependency_graph=(),
        result=None,
        errors=(),
        error_code=None,
        correlation_id=correlation_id,
    )


def _error_response(metric_id: str, error_code: str, correlation_id: str) -> MetricDefinitionAPIResponse:
    """Return a bounded structured failure without exposing internal details."""
    return MetricDefinitionAPIResponse(
        metric_id=metric_id,
        valid=False,
        version=None,
        content_hash=None,
        state=None,
        resolved_inputs=(),
        dependency_graph=(),
        result=None,
        errors=(),
        error_code=error_code,
        correlation_id=correlation_id,
    )
