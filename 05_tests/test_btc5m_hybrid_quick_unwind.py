from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "01_scripts" / "backfill_btc5m_hybrid_quick_unwind.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backfill_btc5m_hybrid_quick_unwind", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def synthetic_market(module, start_epoch: int) -> dict:
    end_epoch = start_epoch + module.MARKET_DURATION_SECONDS
    return {
        **module.product_fields(),
        "slug": module.slug_for_start(start_epoch),
        "condition_id": "synthetic-condition",
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "start_utc": module.utc(start_epoch),
        "end_utc": module.utc(end_epoch),
        "winner": "Up",
        "price_to_beat": 100.0,
        "settlement_final_price": 100.05,
        "official_margin_bps_abs": 5.0,
    }


def test_missing_final_endpoint_does_not_pass_match_filter():
    module = load_module()
    start_epoch = 1_780_000_000
    end_epoch = start_epoch + module.MARKET_DURATION_SECONDS
    trades = []
    trade_id = 1
    for timestamp in range(start_epoch - 30, end_epoch, 5):
        if timestamp == end_epoch:
            continue
        trades.append(
            {
                "timestamp": timestamp,
                "price": 100.0,
                "size": 0.01,
                "side": "buy",
                "trade_id": trade_id,
                "source": "synthetic",
            }
        )
        trade_id += 1
    trades.append(
        {
            "timestamp": end_epoch - 4,
            "price": 100.02,
            "size": 2.0,
            "side": "buy",
            "trade_id": trade_id,
            "source": "synthetic",
        }
    )

    row = module.build_exchange_metrics_for_market(
        synthetic_market(module, start_epoch),
        trades,
        provider="kraken",
        symbol="XBTUSD",
        flat_margin_bps=10.0,
        exchange_window_cache_complete=False,
        exchange_cache_missing_chunks=[Path("missing-tail.json")],
        max_prior_momentum_bps=module.DEFAULT_MAX_PRIOR_MOMENTUM_BPS,
        prior_momentum_lookback_seconds=module.DEFAULT_PRIOR_MOMENTUM_LOOKBACK_SECONDS,
        max_price_lag_seconds=2,
    )

    assert row["exchange_final_endpoint_observed"] == 0
    assert row["exchange_window_cache_complete"] == 0
    assert row["exchange_cache_missing_chunk_count"] == 1
    assert row["final_passes_match_filter"] == 0
    assert row["positive_winner_aligned_price_impact"] == ""


def test_synthetic_primary_thin_quick_unwind_path_is_estimable():
    module = load_module()

    def row(slug: str, flow: int, impact: int, final_move: float, reversion: float) -> dict:
        return {
            "slug": slug,
            "underlying_source": "kraken",
            "underlying_symbol": "XBTUSD",
            "window_seconds": module.WINDOW_SECONDS,
            "flat_margin_bps_lte": 10.0,
            "match_filter": module.MATCH_FILTER,
            "control_method": module.CONTROL_METHOD,
            "volume_regime": "thin",
            "final_passes_match_filter": 1,
            "official_close_enough": 1,
            "exchange_final_endpoint_observed": 1,
            "exchange_window_cache_complete": 1,
            "flow_spike": flow,
            "flow_plus_impact": impact,
            "already_winner_assist": impact,
            "crossing_assist": 0,
            "final_volume_multiple_control_mean": 5.0 if flow else 1.0,
            "final_aligned_multiple_control_mean": 4.0 if flow else 0.5,
            "final_volume_midrank_pct": 0.98 if flow else 0.5,
            "final_aligned_midrank_pct": 0.97 if flow else 0.5,
            "exchange_aligned_final_move_bps": final_move,
            "post_close_reversion_5s_bps": reversion,
            "post_close_reversion_15s_bps": reversion,
            "post_close_reversion_30s_bps": reversion,
        }

    summary = module.summarize_all(
        [
            row("case-flow", 1, 1, 2.0, 1.0),
            row("case-control-a", 0, 0, 0.1, -0.2),
            row("case-control-b", 0, 0, -0.1, -0.1),
        ],
        permutations=50,
    )
    primary = next(item for item in summary if item["design_label"] == "primary_thin")

    assert primary["eligible_markets"] == 3
    assert primary["endpoint_observed_markets"] == 3
    assert primary["exchange_window_cache_complete_markets"] == 3
    assert primary["flow_spike_markets"] == 1
    assert primary["flow_plus_impact_markets"] == 1
    assert primary["flow_plus_impact_reverted_5s_markets"] == 1
    assert primary["flow_plus_impact_gt_nonimpact_reversion_5s_p"] != ""
    assert primary["flow_plus_impact_gt_nonimpact_reversion_5s_p_bh"] != ""
    assert primary["p_value_family"] == "primary_confirmatory_within_design"
    assert primary["bh_scope"] == "within_design_only_not_pooled_across_overlapping_cohorts"


def test_fallback_winner_label_comes_from_outcome_prices():
    """When Gamma finalPrice is missing, the exchange tape supplies the margin
    DIAGNOSTIC only; the winner LABEL must come from Gamma outcomePrices when
    the book resolved (the tape mislabels ~13% of micro-margin fallback rows
    — the 2026-06-12 label-integrity correction's root cause)."""
    module = load_module()
    market = {
        "slug": "btc-updown-5m-1000",
        "start_epoch": 1000,
        "end_epoch": 1300,
        "price_to_beat": 100.0,
        "settlement_final_price": "",
        "final_price_source": "pending_exchange_final_fallback",
        "winner": "",
        # resolved book says Down won...
        "winner_outcome_prices": "Down",
    }
    # ...but the last tape print sits just ABOVE the strike (kraken-implied Up)
    trades = [{"timestamp": 1299.5, "price": 100.01, "side": "buy", "size": 1.0}]
    ok, status = module.fill_exchange_final_price_fallback(
        market, provider="kraken", symbol="XBTUSD", trades=trades,
        max_price_lag_seconds=120)
    assert ok
    assert market["winner"] == "Down"
    assert status["winner_label_source"] == "outcome_prices"
    assert status["kraken_implied_winner"] == "Up"
    assert "outcome_prices_winner" in market["final_price_source"]
    # margin diagnostic still from the tape
    assert abs(float(market["official_margin_bps_abs"]) - 1.0) < 0.2


def test_fallback_without_outcome_prices_keeps_exchange_label():
    """No resolved outcomePrices -> the exchange label survives but is marked
    as exchange_fallback so downstream override/provenance tooling can see it."""
    module = load_module()
    market = {
        "slug": "btc-updown-5m-1000",
        "start_epoch": 1000,
        "end_epoch": 1300,
        "price_to_beat": 100.0,
        "settlement_final_price": "",
        "final_price_source": "pending_exchange_final_fallback",
        "winner": "",
        "winner_outcome_prices": "",
    }
    trades = [{"timestamp": 1299.5, "price": 100.01, "side": "buy", "size": 1.0}]
    ok, status = module.fill_exchange_final_price_fallback(
        market, provider="kraken", symbol="XBTUSD", trades=trades,
        max_price_lag_seconds=120)
    assert ok
    assert market["winner"] == "Up"
    assert status["winner_label_source"] == "exchange_fallback"
