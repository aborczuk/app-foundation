"""Unit tests for target-price runtime dependency checks."""

from __future__ import annotations

import pytest

from csp_trader.target_price import runtime_adapter


def test_require_ib_valuation_package_imports_required_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the expected behavior."""
    seen: list[str] = []

    def _ok_import(name: str):  # type: ignore[no-untyped-def]
        seen.append(name)
        return object()

    monkeypatch.setattr(runtime_adapter.importlib, "import_module", _ok_import)

    runtime_adapter._require_ib_valuation_package()

    assert seen == [
        "ib_valuation.valuation.batch_scheduler",
        "ib_valuation.valuation.comparable_engine",
        "ib_valuation.valuation.sheets_gateway",
        "ib_valuation.valuation.watchlist_gateway",
        "ib_valuation.valuation.dcf_engine",
        "ib_valuation.valuation.ranking_engine",
        "ib_valuation.valuation.risk_engine",
    ]


def test_require_ib_valuation_package_raises_actionable_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the expected behavior."""
    def _raise_import(name: str):  # type: ignore[no-untyped-def]
        if name == "ib_valuation.valuation.batch_scheduler":
            raise ModuleNotFoundError("missing ib_valuation", name="ib_valuation")
        return object()

    monkeypatch.setattr(runtime_adapter.importlib, "import_module", _raise_import)

    with pytest.raises(RuntimeError, match="requires ib_valuation"):
        runtime_adapter._require_ib_valuation_package()


def test_require_ib_valuation_package_reraises_transitive_module_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test the expected behavior."""
    def _raise_import(name: str):  # type: ignore[no-untyped-def]
        if name == "ib_valuation.valuation.batch_scheduler":
            raise ModuleNotFoundError("missing dependency", name="yaml")
        return object()

    monkeypatch.setattr(runtime_adapter.importlib, "import_module", _raise_import)

    with pytest.raises(ModuleNotFoundError, match="missing dependency"):
        runtime_adapter._require_ib_valuation_package()
