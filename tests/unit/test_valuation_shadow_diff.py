"""Unit tests for valuation shadow diff tooling."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from csp_trader.state.valuation_db import get_db_connection, run_migrations
from csp_trader.state.valuation_repository import ValuationRepository


def _load_module():  # type: ignore[no-untyped-def]
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "valuation_shadow_diff.py"
    spec = importlib.util.spec_from_file_location("valuation_shadow_diff", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_snapshot(db_path: Path, *, target_price: float) -> None:
    async with get_db_connection(str(db_path)) as conn:
        await run_migrations(conn)
        repo = ValuationRepository(conn)

        await repo.upsert_stock_profile(ticker="NVDA", themes=["ai"], high_debt_flag=False)
        await repo.create_batch_run(
            batch_id="batch-1",
            scheduled_for="2026-03-18T00:00:00Z",
            ticker_count=1,
            status="queued",
        )
        await repo.transition_batch_run_status(batch_id="batch-1", new_status="running")

        version = await repo.create_next_valuation_version(
            ticker="NVDA",
            assumptions_hash="hash-1",
            base_fair_value=120.0,
        )
        version_id = str(version["valuation_version_id"])
        await repo.transition_valuation_version_status(
            valuation_version_id=version_id,
            new_status="validated",
        )
        await repo.transition_valuation_version_status(
            valuation_version_id=version_id,
            new_status="computed",
        )

        for scenario_name, value in {
            "bull": 140.0,
            "base": 120.0,
            "bear": 95.0,
        }.items():
            await repo.upsert_valuation_scenario(
                valuation_version_id=version_id,
                scenario_type=scenario_name,
                npv_per_share=value,
                assumptions_payload={"discount_rate_pct": 10.0},
            )
        await repo.upsert_valuation_scenario(
            valuation_version_id=version_id,
            scenario_type="comparable",
            npv_per_share=110.0,
            assumptions_payload=None,
            multiples_source_state="fresh",
            unavailable_reason=None,
        )

        await repo.upsert_target_price_record(
            ticker="NVDA",
            valuation_version_id=version_id,
            composite_risk_score=50.0,
            model_margin_safety_pct=27.5,
            manual_margin_adjustment_pct=0.0,
            final_margin_safety_pct=27.5,
            margin_policy_snapshot={"min_pct": 15.0, "max_pct": 40.0},
            target_price=target_price,
            computed_in_batch_id="batch-1",
            status="computed",
        )
        await repo.replace_ranking_entries(
            batch_id="batch-1",
            entries=[
                {
                    "ticker": "NVDA",
                    "weighted_composite_score": 50.0,
                    "target_price": target_price,
                    "model_rank": 1,
                    "manual_override_rank": None,
                    "effective_rank": 1,
                    "status": "ranked",
                }
            ],
        )
        await repo.create_curation_action(
            action_id="action-1",
            ticker="NVDA",
            action_type="push",
            payload_snapshot={"batch_id": "batch-1", "source": "ranking_suggestion"},
            status="requested",
        )

        await repo.transition_valuation_version_status(
            valuation_version_id=version_id,
            new_status="persisted",
        )
        await repo.transition_valuation_version_status(
            valuation_version_id=version_id,
            new_status="exported",
        )
        await repo.transition_batch_run_status(
            batch_id="batch-1",
            new_status="succeeded",
            error_count=0,
        )


async def test_shadow_diff_report_equal_for_matching_snapshots(tmp_path: Path) -> None:
    """Test the expected behavior."""
    module = _load_module()
    legacy_db = tmp_path / "legacy.db"
    package_db = tmp_path / "package.db"

    await _seed_snapshot(legacy_db, target_price=87.0)
    await _seed_snapshot(package_db, target_price=87.0)

    report = module.build_shadow_diff_report(
        legacy_db=legacy_db,
        package_db=package_db,
    )

    assert report["equal"] is True
    assert report["batch_summary_equal"] is True
    assert report["sections"]["targets"]["changed"] == []


async def test_shadow_diff_report_flags_changed_values(tmp_path: Path) -> None:
    """Test the expected behavior."""
    module = _load_module()
    legacy_db = tmp_path / "legacy.db"
    package_db = tmp_path / "package.db"

    await _seed_snapshot(legacy_db, target_price=87.0)
    await _seed_snapshot(package_db, target_price=91.5)

    report = module.build_shadow_diff_report(
        legacy_db=legacy_db,
        package_db=package_db,
    )

    assert report["equal"] is False
    assert report["sections"]["targets"]["changed"] != []
    changed = report["sections"]["targets"]["changed"][0]
    assert changed["key"] == "NVDA"
    assert changed["legacy"]["target_price"] == 87.0
    assert changed["package"]["target_price"] == 91.5
