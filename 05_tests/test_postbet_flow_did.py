from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_postbet_flow_did.py"
SPEC = importlib.util.spec_from_file_location("analyze_postbet_flow_did", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
did = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(did)


def test_scan_wallets_first_buy_side_does_not_flip_to_later_winner(tmp_path) -> None:
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

    bets = did.scan_wallets(str(tmp_path / "*.json"), {wallet}, universe)

    first = bets[wallet]["0xc1"]
    assert first["first_ts"] == 900
    assert first["side"] == "Down"
    assert first["won"] is False
    assert first["buy_sides"] == {"Down", "Up"}

    sell_only = bets[wallet]["0xc2"]
    assert sell_only["first_ts"] is None
    assert sell_only["side"] is None
    assert sell_only["won"] is None
    assert sell_only["preclose_trade_count"] == 1


def test_parse_args_defaults_to_outcome_unconditioned_all(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "argv", [
        "analyze_postbet_flow_did.py",
        "--product", "test",
        "--universe-csv", str(tmp_path / "universe.csv"),
        "--trades-glob", str(tmp_path / "*.json"),
        "--wallets", "0xwallet",
        "--out-dir", str(tmp_path / "out"),
    ])

    args = did.parse_args()

    assert args.treatment == "all"
