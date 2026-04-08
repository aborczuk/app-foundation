"""Cross-repo contract checks for extracted valuation interfaces."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

MATRIX_PATH = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "002-watchlist-research"
    / "contracts"
    / "valuation-compatibility-matrix.json"
)
MATRIX = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
MATRIX_ENTRY = MATRIX["ib_trading"]
PINNED_IB_VALUATION_REF = str(MATRIX_ENTRY["required_ib_valuation_ref"])
PINNED_IB_VALUATION_SHA = str(MATRIX_ENTRY["supported_ib_valuation_commits"][PINNED_IB_VALUATION_REF])
PINNED_IB_VALUATION_SPEC = (
    "ib-valuation @ "
    f"git+https://github.com/aborczuk/ib-valuation.git@{PINNED_IB_VALUATION_REF}"
)

VALUATION_MODULE_SYMBOLS: dict[str, tuple[str, ...]] = {
    "batch_scheduler": ("BatchWindow", "DailyBatchScheduler"),
    "comparable_engine": ("ComparableResult", "ComparableEngine"),
    "conversation_adapter": ("NormalizedAssumptions", "ConversationAdapter"),
    "dcf_engine": ("DcfAssumptions", "DcfEngine"),
    "ranking_engine": ("rank_entries",),
    "risk_engine": ("evaluate_fundamentals_gate",),
    "sheets_gateway": (
        "SheetsConfigurationError",
        "SheetsBootstrapConfig",
        "SheetsGateway",
        "build_valuation_row",
        "build_target_row",
        "build_ranking_row",
        "build_curation_action_row",
    ),
    "watchlist_gateway": (
        "WatchlistGatewayError",
        "WatchlistGateway",
    ),
}

PERSISTENCE_MODULE_SYMBOLS: dict[tuple[str, str], tuple[str, ...]] = {
    (
        "csp_trader.state.valuation_db",
        "ib_valuation.state.db",
    ): ("get_db_connection", "run_migrations"),
    (
        "csp_trader.state.valuation_repository",
        "ib_valuation.state.valuation_repository",
    ): ("ValuationRepository",),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _signature_shape(obj: Any) -> tuple[tuple[str, str, bool], ...]:
    signature = inspect.signature(obj)
    return tuple(
        (
            parameter.name,
            parameter.kind.name,
            parameter.default is not inspect.Signature.empty,
        )
        for parameter in signature.parameters.values()
    )


def _class_public_method_shapes(cls: type[Any]) -> dict[str, tuple[tuple[str, str, bool], ...]]:
    methods: dict[str, tuple[tuple[str, str, bool], ...]] = {}
    for name, member in cls.__dict__.items():
        if name.startswith("_"):
            continue

        function: Any | None = None
        if isinstance(member, staticmethod):
            function = member.__func__
        elif isinstance(member, classmethod):
            function = member.__func__
        elif inspect.isfunction(member):
            function = member

        if function is not None:
            methods[name] = _signature_shape(function)
    return methods


def _import_external_module(module_name: str) -> Any:
    fq_name = f"ib_valuation.valuation.{module_name}"
    return _import_external_fq_module(fq_name)


def _import_external_fq_module(fq_name: str) -> Any:
    try:
        return importlib.import_module(fq_name)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("ib_valuation"):
            pytest.skip("ib_valuation is not installed. Run `uv sync --group compat` to enable this test.")
        raise


def _installed_commit_id() -> str | None:
    for package_name in ("ib-valuation", "ib_valuation"):
        try:
            distribution = metadata.distribution(package_name)
        except metadata.PackageNotFoundError:
            continue

        direct_url_text = distribution.read_text("direct_url.json")
        if not direct_url_text:
            return None
        payload = json.loads(direct_url_text)
        vcs_info = payload.get("vcs_info", {})
        commit_id = vcs_info.get("commit_id")
        if isinstance(commit_id, str) and commit_id:
            return commit_id
        return None
    return None


def _assert_symbol_shape_matches(*, local_symbol: Any, external_symbol: Any, symbol_name: str) -> None:
    if inspect.isfunction(local_symbol):
        assert inspect.isfunction(external_symbol), f"{symbol_name} should be a function"
        assert _signature_shape(local_symbol) == _signature_shape(
            external_symbol
        ), f"{symbol_name} function signature shape differs"
        return

    if inspect.isclass(local_symbol):
        assert inspect.isclass(external_symbol), f"{symbol_name} should be a class"
        try:
            local_ctor_shape = _signature_shape(local_symbol)
            external_ctor_shape = _signature_shape(external_symbol)
        except (TypeError, ValueError):
            local_ctor_shape = None
            external_ctor_shape = None
        assert local_ctor_shape == external_ctor_shape, f"{symbol_name} constructor signature shape differs"
        assert _class_public_method_shapes(local_symbol) == _class_public_method_shapes(
            external_symbol
        ), f"{symbol_name} public method signatures differ"

        if dataclasses.is_dataclass(local_symbol):
            assert dataclasses.is_dataclass(external_symbol), f"{symbol_name} must remain a dataclass"
            assert [field.name for field in dataclasses.fields(local_symbol)] == [
                field.name for field in dataclasses.fields(external_symbol)
            ], f"{symbol_name} dataclass fields differ"
        return

    raise AssertionError(f"Unsupported symbol type for contract check: {symbol_name}")


def test_pyproject_pins_ib_valuation_commit() -> None:
    """Test the expected behavior."""
    pyproject = _repo_root() / "pyproject.toml"
    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    compat_group = payload["dependency-groups"]["compat"]
    assert PINNED_IB_VALUATION_SPEC in compat_group


def test_installed_ib_valuation_commit_matches_pin() -> None:
    """Test the expected behavior."""
    commit_id = _installed_commit_id()
    if commit_id is None:
        pytest.skip("ib_valuation is not installed from VCS. Run `uv sync --group compat` to verify commit pin.")
    assert commit_id == PINNED_IB_VALUATION_SHA


def test_extracted_modules_publish_required_symbols() -> None:
    """Test the expected behavior."""
    for module_name, symbol_names in VALUATION_MODULE_SYMBOLS.items():
        external_module = _import_external_module(module_name)
        for symbol_name in symbol_names:
            assert hasattr(external_module, symbol_name), f"External module missing {module_name}.{symbol_name}"


def test_local_persistence_interfaces_match_external_package() -> None:
    """Test the expected behavior."""
    for (local_module_name, external_module_name), symbol_names in PERSISTENCE_MODULE_SYMBOLS.items():
        local_module = importlib.import_module(local_module_name)
        external_module = _import_external_fq_module(external_module_name)

        for symbol_name in symbol_names:
            assert hasattr(local_module, symbol_name), f"Local module missing {symbol_name}"
            assert hasattr(external_module, symbol_name), f"External module missing {symbol_name}"
            _assert_symbol_shape_matches(
                local_symbol=getattr(local_module, symbol_name),
                external_symbol=getattr(external_module, symbol_name),
                symbol_name=f"{external_module_name}.{symbol_name}",
            )
