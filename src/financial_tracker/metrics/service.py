"""Dry-run orchestration for validated user-defined metric expressions."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import islice
from typing import Protocol

from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.metrics.expression import validate_expression
from financial_tracker.metrics.registry import MetricDefinitionVersion

MAX_REPORT_ITEMS = 64


class DefinitionVersionSource(Protocol):
    """Minimal registry read contract required by dry-run orchestration."""

    def versions(self, metric_id: str, *, scope: AuthorizationScope) -> tuple[MetricDefinitionVersion, ...]:
        """Return the caller's existing definition versions."""
        ...


class MetricLifecycleRegistry(DefinitionVersionSource, Protocol):
    """Registry write contract required by activation and retirement orchestration."""

    def add_version(self, definition: MetricDefinitionVersion, *, scope: AuthorizationScope) -> None:
        """Persist one owner-authorized draft definition."""
        ...

    def add_and_activate(
        self,
        definition: MetricDefinitionVersion,
        *,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Persist and activate one definition in one transaction."""
        ...

    def activate(
        self,
        metric_id: str,
        *,
        version: int,
        scope: AuthorizationScope,
    ) -> MetricDefinitionVersion:
        """Activate one owner-authorized draft version."""
        ...

    def retire(self, metric_id: str, *, scope: AuthorizationScope) -> None:
        """Retire all lifecycle-eligible versions for one metric."""
        ...


@dataclass(frozen=True, slots=True)
class MetricDryRunReport:
    """Bounded, non-persisting result of one metric definition dry run."""

    valid: bool
    metric_id: str
    proposed_version: int
    canonical_expression: str
    output_unit: str
    content_hash: str
    dependencies: tuple[str, ...]
    resolved_inputs: tuple[tuple[str, Decimal], ...]
    dependency_graph: tuple[tuple[str, tuple[str, ...]], ...]
    result: Decimal | None
    errors: tuple[str, ...]


def dry_run_metric(
    registry: DefinitionVersionSource,
    *,
    metric_id: str,
    expression: str,
    approved_inputs: Mapping[str, str],
    input_values: Mapping[str, Decimal | int | float],
    output_unit: str,
    scope: AuthorizationScope,
    dependency_graph: Mapping[str, Sequence[str]] | None = None,
    max_errors: int = 8,
) -> MetricDryRunReport:
    """Validate and safely evaluate a metric without persisting a definition version."""
    if max_errors < 1:
        raise ValueError("max_errors must be positive")
    validation = validate_expression(
        expression,
        metric_id=metric_id,
        approved_inputs=approved_inputs,
        output_unit=output_unit,
        dependency_graph=dependency_graph,
    )
    all_dependencies = validation.dependencies
    dependencies = all_dependencies[:MAX_REPORT_ITEMS]
    errors = list(validation.errors)
    resolved_inputs: list[tuple[str, Decimal]] = []
    values: dict[str, Decimal] = {}
    for dependency in all_dependencies:
        if dependency not in input_values:
            errors.append(f"missing_input:{dependency}")
            continue
        try:
            value = _to_decimal(input_values[dependency])
        except (InvalidOperation, TypeError, ValueError):
            errors.append(f"invalid_input:{dependency}")
            continue
        values[dependency] = value
        if len(resolved_inputs) < MAX_REPORT_ITEMS:
            resolved_inputs.append((dependency, value))

    result: Decimal | None = None
    if not errors:
        try:
            result = _evaluate_expression(expression, values)
        except (ArithmeticError, InvalidOperation, TypeError, ValueError) as exc:
            errors.append("division_by_zero" if isinstance(exc, ZeroDivisionError) else "evaluation_failed")

    bounded_graph = _bound_dependency_graph(dependency_graph)
    bounded_errors = tuple(list(dict.fromkeys(errors))[:max_errors])
    versions = registry.versions(metric_id, scope=scope)
    proposed_version = max((item.version for item in versions), default=0) + 1
    content_hash = _content_hash(
        metric_id=metric_id,
        expression=validation.canonical_expression,
        output_unit=output_unit,
        approved_inputs=approved_inputs,
        dependencies=all_dependencies,
    )
    return MetricDryRunReport(
        valid=validation.valid and not bounded_errors,
        metric_id=metric_id,
        proposed_version=proposed_version,
        canonical_expression=validation.canonical_expression,
        output_unit=output_unit,
        content_hash=content_hash,
        dependencies=dependencies,
        resolved_inputs=tuple(resolved_inputs),
        dependency_graph=bounded_graph,
        result=result,
        errors=bounded_errors,
    )


def activate_metric(
    registry: MetricLifecycleRegistry,
    report: MetricDryRunReport,
    *,
    scope: AuthorizationScope,
    created_at: datetime,
) -> MetricDefinitionVersion:
    """Persist and activate exactly one current, valid dry-run definition."""
    if not report.valid:
        raise ValueError("invalid metric dry run cannot be activated")
    versions = registry.versions(report.metric_id, scope=scope)
    expected_version = max((item.version for item in versions), default=0) + 1
    if report.proposed_version != expected_version:
        raise ValueError("metric dry run is stale")
    definition = MetricDefinitionVersion(
        metric_id=report.metric_id,
        tenant_id=scope.tenant_id,
        version=report.proposed_version,
        expression=report.canonical_expression,
        content_hash=report.content_hash,
        output_unit=report.output_unit,
        state="draft",
        created_by=scope.user_id,
        created_at=created_at,
    )
    return registry.add_and_activate(definition, scope=scope)


def retire_metric(registry: MetricLifecycleRegistry, metric_id: str, *, scope: AuthorizationScope) -> None:
    """Retire a metric through the registry's owner and tenant authorization boundary."""
    registry.retire(metric_id, scope=scope)


def _to_decimal(value: Decimal | int | float) -> Decimal:
    """Convert one input to a finite exact decimal representation."""
    if isinstance(value, bool):
        raise TypeError("boolean inputs are not numeric")
    converted = value if isinstance(value, Decimal) else Decimal(str(value))
    if not converted.is_finite():
        raise ValueError("input must be finite")
    return converted


def _evaluate_expression(expression: str, values: Mapping[str, Decimal]) -> Decimal:
    """Evaluate only the validator's arithmetic AST nodes without executing code."""
    tree = ast.parse(expression, mode="eval")
    result = _evaluate_node(tree.body, values)
    if not result.is_finite():
        raise ValueError("result must be finite")
    return result


def _evaluate_node(node: ast.AST, values: Mapping[str, Decimal]) -> Decimal:
    """Evaluate one bounded arithmetic AST node recursively."""
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return Decimal(str(node.value))
    if not isinstance(node, ast.BinOp):
        raise ValueError("unsupported expression node")
    left = _evaluate_node(node.left, values)
    right = _evaluate_node(node.right, values)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        return left / right
    raise ValueError("unsupported expression operator")


def _bound_dependency_graph(
    dependency_graph: Mapping[str, Sequence[str]] | None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return a deterministic bounded dependency graph projection."""
    if dependency_graph is None:
        return ()
    items = islice(dependency_graph.items(), MAX_REPORT_ITEMS)
    return tuple(
        sorted((key, tuple(islice(dependencies, MAX_REPORT_ITEMS))) for key, dependencies in items)
    )


def _content_hash(
    *,
    metric_id: str,
    expression: str,
    output_unit: str,
    approved_inputs: Mapping[str, str],
    dependencies: Sequence[str],
) -> str:
    """Hash the canonical definition content that a later activation would persist."""
    payload = {
        "metric_id": metric_id,
        "expression": expression,
        "output_unit": output_unit,
        "approved_inputs": [(name, approved_inputs[name]) for name in dependencies if name in approved_inputs],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
