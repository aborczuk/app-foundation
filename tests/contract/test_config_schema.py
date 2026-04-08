"""T005: Contract test — validate config-example.yaml against Pydantic config model.

This test loads the checked-in example config and verifies it parses correctly.
If this test fails, the example config and the schema model are out of sync.
"""

from pathlib import Path

import yaml

from csp_trader.config import AppConfig

EXAMPLE_CONFIG_PATH = (
    Path(__file__).parents[2] / "specs" / "001-auto-options-trader" / "contracts" / "config-example.yaml"
)


def test_example_config_loads_and_validates():
    """config-example.yaml must parse and validate against AppConfig without errors."""
    assert EXAMPLE_CONFIG_PATH.exists(), f"Example config not found: {EXAMPLE_CONFIG_PATH}"

    with open(EXAMPLE_CONFIG_PATH) as f:
        raw = yaml.safe_load(f)

    # Must not raise
    cfg = AppConfig.model_validate(raw)

    assert len(cfg.watchlist) > 0, "Example config must contain at least one watchlist entry"
    assert cfg.rules.annualized_return_floor_pct > 0
    assert cfg.rules.min_dte >= 1
