from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_perwallet_flow_footprint.py"
SPEC = importlib.util.spec_from_file_location("analyze_perwallet_flow_footprint", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
fp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fp)


def test_scan_wallets_first_buy_won_semantics_and_sell_only_presence(tmp_path) -> None:
    wallet = "0xwallet"
    universe = {
        "0xc1": {"winner": "Up", "end": 1000, "margin": 5.0},
        "0xc2": {"winner": "Down", "end": 1000, "margin": 5.0},
    }
    shard = tmp_path / "trades.json"
    shard.write_text(json.dumps([
        {"proxyWallet": wallet, "conditionId": "0xc1", "outcome": "Down",
         "side": "BUY", "timestamp": 900},
        {"proxyWallet": wallet, "conditionId": "0xc1", "outcome": "Up",
         "side": "BUY", "timestamp": 950},
        {"proxyWallet": wallet, "conditionId": "0xc2", "outcome": "Down",
         "side": "SELL", "timestamp": 940},
    ]))

    bets = fp.scan_wallets(str(tmp_path / "*.json"), {wallet}, universe)

    first = bets[wallet]["0xc1"]
    assert first["first_ts"] == 900
    assert first["side"] == "Down"
    assert first["won"] is False
    assert first["buy_sides"] == {"Down", "Up"}

    sell_only = bets[wallet]["0xc2"]
    assert sell_only["first_ts"] is None
    assert sell_only["preclose_trade_count"] == 1


def test_select_guarded_won_treated_excludes_close30_overlap() -> None:
    universe = {
        "early": {"end": 1000},
        "boundary": {"end": 1000},
        "late": {"end": 1000},
        "lost": {"end": 1000},
    }
    feat = {cid: {"cid": cid} for cid in universe}
    wb = {
        "early": {"won": True, "first_ts": 960},
        "boundary": {"won": True, "first_ts": 970},
        "late": {"won": True, "first_ts": 971},
        "lost": {"won": False, "first_ts": 940},
    }

    treated, candidates, guard_excluded = fp.select_guarded_won_treated(wb, feat, universe, 30)

    assert [r["cid"] for r in treated] == ["early", "boundary"]
    assert candidates == 3
    assert guard_excluded == 1
