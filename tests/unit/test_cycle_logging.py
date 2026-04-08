"""B005: Cycle completion log emits event=cycle_end."""

from __future__ import annotations

import csp_trader.main as main_mod


def test_cycle_end_log_event(monkeypatch):
    """Test the expected behavior."""
    events = []

    def fake_info(_msg, extra=None, **_kwargs):
        if extra:
            events.append(extra.get("event"))

    monkeypatch.setattr(main_mod.logger, "info", fake_info)

    main_mod._log_cycle_end(
        open_positions=[{"id": "p1"}, {"id": "p2"}],
        close_orders_count=1,
        tickers_scanned=3,
        new_orders_count=2,
        market_open=True,
    )

    assert "cycle_end" in events
