from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_wallet_attribution.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_wallet_attribution", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
wallet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wallet)


def trade(ts: int, w: str, outcome: str, side: str, size: float, price: float) -> dict:
    return {"timestamp": ts, "proxyWallet": w, "outcome": outcome, "side": side, "size": size, "price": price}


def test_slug_epochs_parses_start_and_end() -> None:
    start, end = wallet.slug_epochs("btc-updown-5m-1780606200")
    assert start == 1780606200
    assert end == 1780606200 + 300


def test_aggregate_counts_pro_and_anti_winner_flow() -> None:
    end = 1000
    trades = [
        trade(end - 10, "0xA", "Up", "BUY", 100.0, 0.9),   # pro-winner buy
        trade(end - 5, "0xB", "Down", "SELL", 50.0, 0.2),  # pro-winner (sell loser)
        trade(end - 5, "0xA", "Down", "BUY", 30.0, 0.1),   # anti-winner
        trade(end - 400, "0xA", "Up", "BUY", 999.0, 0.5),  # outside 60s window
    ]
    wallets = wallet.aggregate_wallet_flows(trades, winner="Up", end_epoch=end, window_seconds=60)
    assert wallets["0xA"]["pro_winner_notional"] == 90.0
    assert wallets["0xA"]["pro_winner_buy_profit"] == 100.0 * (1.0 - 0.9)
    assert wallets["0xA"]["anti_winner_notional"] == 3.0
    assert wallets["0xB"]["pro_winner_notional"] == 10.0


def test_concentration_metrics_shares_and_hhi() -> None:
    wallets = {
        "0xA": {"pro_winner_notional": 75.0},
        "0xB": {"pro_winner_notional": 25.0},
    }
    metrics = wallet.concentration_metrics(wallets)
    assert metrics["pro_winner_notional_total"] == 100.0
    assert metrics["pro_winner_wallets"] == 2
    assert abs(metrics["top1_share"] - 0.75) < 1e-9
    assert abs(metrics["hhi"] - (0.75 ** 2 + 0.25 ** 2)) < 1e-9


def test_concentration_metrics_handles_empty() -> None:
    metrics = wallet.concentration_metrics({})
    assert metrics["pro_winner_notional_total"] == 0.0
    assert metrics["top1_share"] is None


def test_cross_market_stats_counts_repeat_wallets() -> None:
    m1 = {"0xA": {"pro_winner_notional": 100.0, "pro_winner_buy_profit": 10.0}}
    m2 = {"0xA": {"pro_winner_notional": 50.0, "pro_winner_buy_profit": 5.0},
          "0xC": {"pro_winner_notional": 50.0, "pro_winner_buy_profit": 0.0}}
    stats = wallet.cross_market_stats([m1, m2])
    assert stats["max_wallet_market_count"] == 2  # 0xA appears in both
    assert stats["repeat_wallets_2plus"] == 1
    assert abs(stats["repeat_notional_share"] - 150.0 / 200.0) < 1e-9
    assert stats["total_pro_winner_buy_profit"] == 15.0


def test_permutation_test_returns_p_for_each_stat() -> None:
    observed = {
        "max_wallet_market_count": 2,
        "repeat_notional_share": 0.9,
        "top_wallet_notional_share": 0.9,
    }
    control = [
        {"0xX": {"pro_winner_notional": 100.0, "pro_winner_buy_profit": 0.0}},
        {"0xY": {"pro_winner_notional": 100.0, "pro_winner_buy_profit": 0.0}},
        {"0xZ": {"pro_winner_notional": 100.0, "pro_winner_buy_profit": 0.0}},
        {"0xW": {"pro_winner_notional": 100.0, "pro_winner_buy_profit": 0.0}},
    ]
    perm = wallet.permutation_test(observed, control, set_size=2, permutations=200, seed=1)
    # controls never repeat a wallet, so observed repeat concentration is extreme -> small p
    assert perm["max_wallet_market_count"]["p"] is not None
    assert perm["max_wallet_market_count"]["p"] < 0.5
