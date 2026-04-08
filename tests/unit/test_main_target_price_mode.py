"""Unit tests for target-price runtime mode isolation in main entrypoint."""

from __future__ import annotations

import argparse
import builtins

import pytest

from csp_trader import main as csp_main


@pytest.mark.asyncio
async def test_target_price_mode_never_imports_order_execution_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the expected behavior."""
    captured: dict[str, object] = {}

    async def _fake_run_target_price_mode(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return 0

    import csp_trader.target_price.runtime_adapter as runtime_adapter_module

    monkeypatch.setattr(runtime_adapter_module, "run_target_price_mode", _fake_run_target_price_mode)

    forbidden_imported = False
    original_import = builtins.__import__

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        nonlocal forbidden_imported
        if name.startswith("csp_trader.ibkr.orders"):
            forbidden_imported = True
            raise AssertionError("target-price mode must not import order-execution modules")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)

    args = argparse.Namespace(
        mode="target-price",
        config="config.yaml",
        dry_run=True,
        apply_curation=False,
        log_level="INFO",
    )
    exit_code = await csp_main._async_main(args)

    assert exit_code == 0
    assert captured["config_path"] == "config.yaml"
    assert captured["dry_run"] is True
    assert captured["apply_curation"] is False
    assert forbidden_imported is False


@pytest.mark.asyncio
async def test_target_price_mode_forwards_apply_curation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the expected behavior."""
    captured: dict[str, object] = {}

    async def _fake_run_target_price_mode(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return 0

    import csp_trader.target_price.runtime_adapter as runtime_adapter_module

    monkeypatch.setattr(runtime_adapter_module, "run_target_price_mode", _fake_run_target_price_mode)

    args = argparse.Namespace(
        mode="target-price",
        config="config.yaml",
        dry_run=False,
        apply_curation=True,
        log_level="INFO",
    )
    exit_code = await csp_main._async_main(args)

    assert exit_code == 0
    assert captured["apply_curation"] is True


def test_trade_execution_guard_fails_closed_for_non_trading_modes() -> None:
    """Test the expected behavior."""
    with pytest.raises(RuntimeError, match="disabled"):
        csp_main._ensure_trade_execution_allowed("target-price")
