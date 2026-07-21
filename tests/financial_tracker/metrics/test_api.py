"""Contract coverage for validation, authorization, dry runs, and version history."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_tracker.api.metric_definitions import MetricDefinitionAPI
from financial_tracker.identity.resolver import AuthorizationScope
from financial_tracker.metrics.registry import MetricRegistry


def _scope(user_id, tenant_id: str = "tenant-a") -> AuthorizationScope:
    """Build a server-derived scope for API contract tests."""
    return AuthorizationScope(user_id, tenant_id, "subject-a", frozenset(), frozenset())


def _api() -> tuple[MetricDefinitionAPI, AuthorizationScope]:
    """Build one isolated metric-definition API boundary and owner scope."""
    owner_id = uuid4()
    return MetricDefinitionAPI(MetricRegistry()), _scope(owner_id)


def _dry_run(api: MetricDefinitionAPI, scope: AuthorizationScope):
    """Build one valid API dry-run response."""
    return api.dry_run(
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=scope,
        correlation_id="corr-dry-run",
    )


def test_dry_run_returns_bounded_contract_response_without_persistence() -> None:
    """Valid dry runs expose result/version/hash and do not create history."""
    api, scope = _api()

    response = _dry_run(api, scope)

    assert response.valid is True
    assert response.version == 1
    assert response.content_hash
    assert response.result == Decimal("2.5")
    assert response.error_code is None
    assert response.correlation_id == "corr-dry-run"
    assert api.history("custom_margin", scope=scope) == ()


def test_invalid_definition_returns_structured_error_without_side_effect() -> None:
    """Unsupported expressions map to invalid_definition and remain unpersisted."""
    api, scope = _api()

    response = api.dry_run(
        metric_id="custom_margin",
        expression="__import__('os')",
        approved_inputs={},
        input_values={},
        output_unit="ratio",
        scope=scope,
    )

    assert response.valid is False
    assert response.error_code == "invalid_definition"
    assert api.history("custom_margin", scope=scope) == ()


def test_activation_is_tenant_scoped_and_history_is_immutable() -> None:
    """Owner activation succeeds while a different tenant receives isolated history."""
    api, owner_scope = _api()
    activated = api.activate(
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=owner_scope,
        created_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
        correlation_id="corr-activate",
    )

    assert activated.valid is True
    assert activated.state == "active"
    assert activated.correlation_id == "corr-activate"
    assert [item.version for item in api.history("custom_margin", scope=owner_scope)] == [1]

    peer_scope = _scope(uuid4())
    peer_response = api.activate(
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=peer_scope,
        created_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
    )
    assert peer_response.valid is False
    assert peer_response.error_code == "forbidden"
    second = api.activate(
        metric_id="custom_margin",
        expression="revenue / operating_income",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=owner_scope,
        created_at=datetime(2025, 5, 2, tzinfo=timezone.utc),
    )
    assert second.valid is True
    assert second.version == 2
    assert [item.version for item in api.history("custom_margin", scope=owner_scope)] == [1, 2]


def test_retirement_is_owner_authorized_and_preserves_history() -> None:
    """Retirement is owner-only while all immutable versions remain queryable."""
    api, owner_scope = _api()
    for day in (1, 2):
        api.activate(
            metric_id="custom_margin",
            expression="revenue / operating_income",
            approved_inputs={"revenue": "USD", "operating_income": "USD"},
            input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
            output_unit="ratio",
            scope=owner_scope,
            created_at=datetime(2025, 5, day, tzinfo=timezone.utc),
        )

    peer_response = api.retire("custom_margin", scope=_scope(uuid4()))
    assert peer_response.valid is False
    assert peer_response.error_code == "forbidden"

    response = api.retire("custom_margin", scope=owner_scope, correlation_id="corr-retire")

    assert response.valid is True
    assert response.state == "retired"
    assert response.version == 2
    assert response.correlation_id == "corr-retire"
    assert [item.state for item in api.history("custom_margin", scope=owner_scope)] == ["retired", "retired"]


@pytest.mark.parametrize("expression", ["revenue + operating_income", "revenue / 0"])
def test_api_contract_rejects_unsafe_or_invalid_calculations(expression: str) -> None:
    """API validation keeps unsupported operations bounded and non-persisting."""
    api, scope = _api()
    response = api.dry_run(
        metric_id="custom_margin",
        expression=expression,
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        input_values={"revenue": Decimal("100"), "operating_income": Decimal("40")},
        output_unit="ratio",
        scope=scope,
    )

    assert response.valid is False
    assert response.error_code == "invalid_definition"
