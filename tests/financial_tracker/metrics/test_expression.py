"""Red fixture coverage for restricted metric expressions."""

from financial_tracker.metrics.expression import validate_expression


def test_accepts_allowlisted_arithmetic_over_approved_inputs() -> None:
    """A bounded expression returns canonical dependencies and no validation errors."""
    report = validate_expression(
        "revenue / operating_income",
        metric_id="operating_margin",
        approved_inputs={"revenue": "USD", "operating_income": "USD"},
        output_unit="ratio",
    )

    assert report.valid is True
    assert report.dependencies == ("operating_income", "revenue")
    assert report.errors == ()


def test_rejects_unit_mismatch_and_unknown_symbols() -> None:
    """Addition cannot combine incompatible units or silently map unknown concepts."""
    mismatch = validate_expression(
        "revenue + margin",
        metric_id="bad_metric",
        approved_inputs={"revenue": "USD", "margin": "ratio"},
        output_unit="USD",
    )
    unknown = validate_expression(
        "revenue + unknown_metric",
        metric_id="unknown_metric",
        approved_inputs={"revenue": "USD"},
        output_unit="USD",
    )

    assert mismatch.valid is False
    assert "unit_mismatch" in mismatch.errors
    assert unknown.valid is False
    assert "unknown_symbol:unknown_metric" in unknown.errors


def test_rejects_unsafe_syntax_without_executing_user_code(tmp_path) -> None:
    """Calls, attributes, and import-like expressions are outside the grammar."""
    target = tmp_path / "should-not-exist"
    report = validate_expression(
        f"__import__('pathlib').Path({str(target)!r}).touch()",
        metric_id="unsafe",
        approved_inputs={},
        output_unit="ratio",
    )

    assert report.valid is False
    assert "unsafe_syntax" in report.errors
    assert not target.exists()


def test_rejects_dependency_cycles_before_activation() -> None:
    """A metric cannot depend on a chain that returns to itself."""
    report = validate_expression(
        "margin + revenue",
        metric_id="margin",
        approved_inputs={"revenue": "USD"},
        output_unit="USD",
        dependency_graph={"margin": ("acceleration",), "acceleration": ("margin",)},
    )

    assert report.valid is False
    assert "dependency_cycle" in report.errors
