"""Contract coverage for metric dry-run validation and bounded reports."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.metrics.registry import MetricDefinitionVersion, MetricRegistry
from financial_tracker.metrics.service import dry_run_metric


def _scope(user_id) -> AuthorizationScope:
    """Build a tenant scope for dry-run service tests."""
    return AuthorizationScope(user_id, "tenant-a", "subject-a", frozenset(), frozenset())


def test_dry_run_returns_decimal_result_without_persisting_definition() -> None:
    """A valid expression resolves inputs, computes safely, and remains a dry run."""
    owner_id = uuid4()
    registry = MetricRegistry()
    scope = _scope(owner_id)

    report = dry_run_metric(
        registry,
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=scope,
    )

    assert report.valid is True
    assert report.result == Decimal("2.5")
    assert report.proposed_version == 1
    assert report.errors == ()
    assert report.resolved_inputs == (
        ("operating_income", Decimal("40")),
        ("revenue", Decimal("100")),
    )
    assert registry.versions("custom_margin", scope=scope) == ()


def test_dry_run_reports_missing_inputs_and_caps_errors() -> None:
    """Invalid input resolution returns bounded errors instead of evaluating partially."""
    owner_id = uuid4()
    report = dry_run_metric(
        MetricRegistry(),
        metric_id="custom_metric",
        expression="revenue + unknown_metric + missing_metric",
        approved_inputs={"revenue": "USD"},
        input_values={"revenue": Decimal("100")},
        output_unit="USD",
        scope=_scope(owner_id),
        max_errors=2,
    )

    assert report.valid is False
    assert report.result is None
    assert len(report.errors) == 2
    assert all(error.startswith("unknown_symbol:") for error in report.errors)


def test_dry_run_proposes_next_version_without_mutating_history() -> None:
    """Existing history advances the proposed version while remaining unchanged."""
    owner_id = uuid4()
    scope = _scope(owner_id)
    registry = MetricRegistry()
    registry.add_version(
        MetricDefinitionVersion(
            metric_id="custom_margin",
            tenant_id="tenant-a",
            version=1,
            expression="revenue / operating_income",
            content_hash="v1",
            output_unit="ratio",
            state="draft",
            created_by=owner_id,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        scope=scope,
    )

    report = dry_run_metric(
        registry,
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=scope,
    )

    assert report.valid is True
    assert report.proposed_version == 2
    assert tuple(item.version for item in registry.versions("custom_margin", scope=scope)) == (1,)


def test_dry_run_evaluates_all_dependencies_beyond_report_cap() -> None:
    """Report truncation does not change evaluation or content identity inputs."""
    owner_id = uuid4()
    names = tuple(f"input_{index}" for index in range(65))
    expression = " + ".join(names)
    units = {name: "USD" for name in names}
    values = {name: Decimal("1") for name in names}

    report = dry_run_metric(
        MetricRegistry(),
        metric_id="wide_metric",
        expression=expression,
        approved_inputs=units,
        input_values=values,
        output_unit="USD",
        scope=_scope(owner_id),
    )

    assert report.valid is True
    assert report.result == Decimal("65")
    assert len(report.dependencies) == 64
    assert len(report.resolved_inputs) == 64


def test_dry_run_bounds_dependency_graph_projection() -> None:
    """A large dependency mapping produces a bounded report projection."""
    report = dry_run_metric(
        MetricRegistry(),
        metric_id="custom_metric",
        expression="revenue",
        approved_inputs={"revenue": "USD"},
        input_values={"revenue": Decimal("100")},
        output_unit="USD",
        scope=_scope(uuid4()),
        dependency_graph={f"metric_{index}": ("revenue",) for index in range(128)},
    )

    assert report.valid is True
    assert len(report.dependency_graph) == 64
