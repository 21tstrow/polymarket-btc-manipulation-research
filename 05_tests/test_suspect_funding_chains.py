from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "01_scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCRIPT_PATH = ROOT / "01_scripts" / "trace_btc5m_suspect_funding_chains.py"
SPEC = importlib.util.spec_from_file_location("trace_btc5m_suspect_funding_chains", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
tc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tc)


W = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def xfer(frm, to, value, ts, hash_="0x1"):
    return {"from": frm, "to": to, "value": str(value), "timeStamp": str(ts),
            "hash": hash_, "tokenDecimal": "6"}


def test_earliest_inbound_source_picks_first_funder_not_largest() -> None:
    transfers = [
        xfer("0xbig", W, 9_000_000, 100, "0xh1"),    # larger but later
        xfer("0xbig", W, 1_000_000, 200, "0xh2"),
        xfer("0xfirst", W, 2_000_000, 50, "0xh3"),   # earliest inbound = funding
        xfer(W, "0xout", 500_000, 60, "0xh4"),       # outgoing ignored
    ]
    src = tc.earliest_inbound_source(transfers, W)
    assert src["address"] == "0xfirst"
    assert src["usdc"] == 2.0
    assert src["first_ts"] == 50
    assert src["first_hash"] == "0xh3"


def test_earliest_inbound_source_none_when_no_inbound() -> None:
    assert tc.earliest_inbound_source([xfer(W, "0xout", 1, 1)], W) is None


def test_fanout_counts_distinct_recipients() -> None:
    transfers = [
        xfer(W, "0xa", 1, 1), xfer(W, "0xa", 1, 2), xfer(W, "0xb", 1, 3),
        xfer("0xc", W, 1, 4),  # inbound not counted
    ]
    assert tc.fanout(transfers, W) == 2


class FakeClient:
    """Stand-in for EtherscanClient: serves canned transfers and signers."""

    def __init__(self, transfers_by_wallet, signers=None):
        self._t = transfers_by_wallet
        self._signers = signers or {}

    def token_transfers(self, wallet, label, token):
        # only return rows on the first (USDC.e) token to avoid double counting
        if label == "USDC.e":
            return list(self._t.get(wallet, [])), False
        return [], False

    def _request(self, params, cache_name, raw=False):
        return {"from": self._signers.get(params["txhash"])}


def test_classify_mixer_bridge_and_fanout() -> None:
    tracer = tc.Tracer(FakeClient({}))
    mixer = next(iter(tc.POLYGON_MIXERS))
    assert tracer.classify(mixer)[0] == "mixer"
    assert tracer.classify(tc.funding.ZERO_ADDRESS)[0] == "bridge_mint"
    relayer = "0xf70da97812cb96acdf810712aa562db8dfa3dbef"
    assert tracer.classify(relayer)[0] == "infra"


def test_classify_cex_vs_operator_by_fanout() -> None:
    hub = "0xhub"
    quiet = "0xquiet"
    transfers = {
        hub: [xfer(hub, f"0x{i:040x}", 1, i) for i in range(tc.CEX_FANOUT_THRESHOLD + 5)],
        quiet: [xfer(quiet, "0xz", 1, 1)],
    }
    tracer = tc.Tracer(FakeClient(transfers))
    assert tracer.classify(hub)[0] == "cex_or_service"
    assert tracer.classify(quiet)[0] == "operator_eoa" or tracer.classify(quiet)[0] == "continue"


def test_trace_resolves_relayer_signer_and_stops_at_cex() -> None:
    relayer = "0xf70da97812cb96acdf810712aa562db8dfa3dbef"
    signer = "0xdeadbeef00000000000000000000000000000001"
    cex = "0xcex"
    suspect = W
    transfers = {
        # suspect funded by relayer, deposit tx signed by `signer`
        suspect: [xfer(relayer, suspect, 1_000_000, 100, "0xdep")],
        # signer funded by a high-fanout CEX
        signer: [xfer(cex, signer, 5_000_000, 50, "0xc1")],
        cex: [xfer(cex, f"0x{i:040x}", 1, i) for i in range(tc.CEX_FANOUT_THRESHOLD + 1)],
    }
    tracer = tc.Tracer(FakeClient(transfers, signers={"0xdep": signer}))
    path = tracer.trace(suspect, max_hops=5)
    # hop 1 resolves relayer -> signer; hop 2 reaches the CEX terminal
    assert path[0]["funder"] == relayer
    assert path[0]["resolved"] == signer
    assert path[-1]["terminal"] == "cex_or_service"
