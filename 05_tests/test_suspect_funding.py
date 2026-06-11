from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "analyze_btc5m_suspect_funding.py"
SPEC = importlib.util.spec_from_file_location("analyze_btc5m_suspect_funding", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
sf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sf)


W = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def transfer(frm, to, value, ts, hash_="0x1", decimals="6"):
    return {"from": frm, "to": to, "value": str(value), "timeStamp": str(ts),
            "hash": hash_, "tokenDecimal": decimals,
            "contractAddress": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"}


def test_load_env_parses_and_skips_comments(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\n\nETHERSCAN_API_KEY= abc123 \nBAD LINE\n", encoding="utf-8")
    assert sf.load_env(env) == {"ETHERSCAN_API_KEY": "abc123"}
    assert sf.load_env(tmp_path / "missing.env") == {}


def test_dedupe_transfers_by_identity() -> None:
    a = transfer("0xb", W, 100, 1, "0xh1")
    b = transfer("0xb", W, 100, 1, "0xh1")
    c = transfer("0xb", W, 200, 2, "0xh2")
    assert sf.dedupe_transfers([a, b, c]) == [a, c]


def test_first_incoming_earliest_by_timestamp() -> None:
    early = transfer("0xfunder", W, 5_000_000, 100, "0xh1")
    late = transfer("0xother", W, 9_000_000, 200, "0xh2")
    outgoing = transfer(W, "0xdest", 1_000_000, 50, "0xh3")
    assert sf.first_incoming([late, outgoing, early], W) == early
    assert sf.first_incoming([outgoing], W) is None


def test_counterparty_stats_direction_and_totals() -> None:
    transfers = [
        transfer("0xb", W, 5_000_000, 1, "0xh1"),   # in: 5 USDC
        transfer("0xb", W, 3_000_000, 2, "0xh2"),   # in: 3 USDC
        transfer(W, "0xc", 2_000_000, 3, "0xh3"),   # out: 2 USDC
    ]
    stats = sf.counterparty_stats(transfers, W)
    assert stats[("0xb", "in")] == {"n": 2, "total_usdc": 8.0}
    assert stats[("0xc", "out")] == {"n": 1, "total_usdc": 2.0}


def test_classify_counterparty_rules() -> None:
    control = "0xcontrol"
    # known infra wins regardless
    relayer = "0xf70da97812cb96acdf810712aa562db8dfa3dbef"
    assert sf.classify_counterparty(relayer, {W}, control, 9) == "polymarket_relayer"
    # touching the control = infra-like
    assert sf.classify_counterparty("0xhot", {W, control}, control, 9) \
        == "shared_with_control_likely_infra_or_cex"
    # touching nearly all tracked wallets = infra-like even without the control
    many = {f"0x{i}" for i in range(7)}
    assert sf.classify_counterparty("0xhub", many, control, 9) \
        == "high_degree_likely_infra_or_cex"
    # a quiet address linking two suspects is the interesting case
    assert sf.classify_counterparty("0xop", {W, "0xother"}, control, 9) \
        == "candidate_operator_link"


def test_transfer_key_distinguishes_value_and_hash() -> None:
    a = sf.transfer_key(transfer("0xb", W, 100, 1, "0xh1"))
    b = sf.transfer_key(transfer("0xb", W, 101, 1, "0xh1"))
    assert a != b
