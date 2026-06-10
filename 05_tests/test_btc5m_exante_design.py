from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "01_scripts" / "analyze_btc5m_exante_design.py"


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_btc5m_exante_design", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def product_fields() -> dict:
    return {
        "market_timeframe": "5m",
        "market_duration_seconds": 300,
        "series_slug": "btc-up-or-down-5m",
        "slug_prefix": "btc-updown-5m",
    }


def market(start: int = 1000) -> dict:
    end = start + 300
    return {
        **product_fields(),
        "slug": f"btc-updown-5m-{start}",
        "condition_id": "0xtest",
        "start_epoch": start,
        "end_epoch": end,
        "start_utc": "2026-01-01T00:00:00Z",
        "end_utc": "2026-01-01T00:05:00Z",
        "price_to_beat": 100.0,
        "settlement_final_price": 150.0,
        "winner": "Down",
        "official_margin_bps_abs": 4000.0,
    }


def trade(timestamp: float, price: float = 100.0, size: float = 0.01, side: str = "buy", trade_id: int = 1) -> dict:
    return {
        "timestamp": timestamp,
        "price": price,
        "size": size,
        "side": side,
        "trade_id": trade_id,
        "source": "synthetic",
    }


def synthetic_trades(start: int = 1000) -> list[dict]:
    rows = []
    trade_id = 1
    for ts in range(start - 35, start + 331, 5):
        rows.append(trade(ts, size=0.01, side="buy", trade_id=trade_id))
        trade_id += 1
    # Large final-window buy flow. This should be treated as buy/up pressure even
    # though the synthetic official winner field says Down.
    rows.append(trade(start + 296, price=100.02, size=10.0, side="buy", trade_id=trade_id))
    return rows


def build_row(module, test_market: dict | None = None, trades: list[dict] | None = None) -> dict:
    test_market = test_market or market()
    return module.build_event_row(
        test_market,
        trades or synthetic_trades(int(test_market["start_epoch"])),
        provider="kraken",
        symbol="XBTUSD",
        event_epoch=int(test_market["end_epoch"]),
        event_label="actual",
        cache_status="complete_nonempty",
        missing_paths=[],
        segment="evaluation",
        close_bps=10.0,
        max_prior_momentum_bps=10.0,
        min_controls=20,
        rank_threshold=0.90,
        imbalance_share_threshold=0.60,
        max_price_lag_seconds=2,
    )


def test_exante_eligibility_does_not_require_official_close_or_winner() -> None:
    module = load_module()
    row = build_row(module)

    assert row["official_winner"] == "Down"
    assert float(row["official_margin_bps_abs"]) == 4000.0
    assert row["analysis_eligible"] == 1
    assert row["large_directional_flow"] == 1


def test_flow_sign_is_raw_buy_sell_not_winner_aligned() -> None:
    module = load_module()
    row = build_row(module)

    assert row["final_flow_sign"] == 1
    assert row["final_signed_taker_quote"] > 0


def test_final_interval_excludes_endpoint_trade() -> None:
    module = load_module()
    start = 1000
    rows = synthetic_trades(start)
    rows.append(trade(start + 300, price=100.0, size=99.0, side="sell", trade_id=999))

    stats = module.signed_interval_stats(rows, start + 295, start + 300)

    assert stats["sell_taker_quote"] == 0
    assert stats["flow_sign"] == 1


def test_thin_cutoff_uses_calibration_rows_only() -> None:
    module = load_module()
    rows = [
        {"segment": "calibration", "underlying_source": "kraken", "underlying_symbol": "XBTUSD", "pre_60s_quote_volume": "10", "cache_complete": 1},
        {"segment": "calibration", "underlying_source": "kraken", "underlying_symbol": "XBTUSD", "pre_60s_quote_volume": "20", "cache_complete": 1},
        {"segment": "evaluation", "underlying_source": "kraken", "underlying_symbol": "XBTUSD", "pre_60s_quote_volume": "100000", "cache_complete": 1},
    ]

    cutoff = module.thin_cutoff_from_calibration(
        [row for row in rows if row["segment"] == "calibration"],
        0.5,
    )

    assert cutoff == 15.0


def test_complete_empty_cache_is_not_missing(tmp_path: Path) -> None:
    module = load_module()
    cache_dir = tmp_path / "cache"
    target_dir = cache_dir / "kraken_trades"
    target_dir.mkdir(parents=True)
    path = target_dir / "XBTUSD_1000_1300.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    trades, missing, status = module.load_trade_window(
        "kraken",
        "XBTUSD",
        1000,
        1300,
        cache_dir,
        {},
    )

    assert trades == []
    assert missing == []
    assert status == "complete_empty"
