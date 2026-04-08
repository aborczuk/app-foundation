"""Unit tests for valuation runtime config projection."""

from __future__ import annotations

from pathlib import Path

from csp_trader.config import load_config
from csp_trader.target_price.runtime_config import (
    derive_valuation_runtime_config,
    load_valuation_runtime_config,
)

EXAMPLE_CONFIG_PATH = (
    Path(__file__).parents[2] / "specs" / "001-auto-options-trader" / "contracts" / "config-example.yaml"
)


def test_derive_valuation_runtime_config_projects_subset() -> None:
    """Test the expected behavior."""
    app_config = load_config(EXAMPLE_CONFIG_PATH)

    valuation_config = derive_valuation_runtime_config(
        app_config,
        source_config_path=EXAMPLE_CONFIG_PATH,
    )

    assert valuation_config.source_config_path.endswith("config-example.yaml")
    assert valuation_config.storage.db_path == app_config.storage.db_path
    assert valuation_config.storage.valuation_db_path == app_config.storage.valuation_db_path
    assert len(valuation_config.watchlist) == len(app_config.watchlist)


def test_load_valuation_runtime_config_loads_from_yaml() -> None:
    """Test the expected behavior."""
    valuation_config = load_valuation_runtime_config(EXAMPLE_CONFIG_PATH)

    assert valuation_config.rules.min_dte >= 1
    assert valuation_config.watchlist[0].ticker
