#!/usr/bin/env python3
"""Multi-hop funding-chain trace for the push-concentrated suspect wallets.

The one-hop funding check (analyze_btc5m_suspect_funding.py) cannot answer the
operator question, for two reasons it now fixes:

  1. Depth. It stopped at the first funder. A shared operator can sit several
     hops upstream of CEX-fresh proxies. This walks back up to --max-hops,
     following the earliest (funding) inbound USDC source at each node.

  2. The relayer mask. Five wallets show the Polymarket relayer as first
     funder, which only means "deposited through Polymarket". The address that
     actually signed (and paid gas for) that deposit transaction is the real
     lead - and a gas wallet that signs deposits for two different suspects is
     an operator link that no CEX hop can launder. For relayer / proxy-deposit
     funding we resolve the tx signer via eth_getTransactionByHash.

At each node we classify the terminal:
  - mixer            : known Polygon Tornado Cash pool (laundering signature);
  - bridge_mint      : minted from 0x0 (cross-chain deposit, source off-Polygon);
  - cex_or_service   : high fan-out hot wallet (many distinct recipients) - an
                       exchange or custodial service; the chain dead-ends here
                       because the real owner is inside that custodian;
  - operator_eoa     : a low-fan-out EOA that is NOT shared infra - the only
                       terminal that, if shared across suspects, implies one
                       operator.

Cross-suspect: report any node (funder, tx-signer, or terminal) reached by >=2
suspects. That, not "same CEX", is what would make the shared-operator call.
A shared CEX deadend is the opposite of a kill: Binance serves millions, so it
neither confirms nor refutes common control.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "01_scripts"))
import analyze_btc5m_suspect_funding as funding  # noqa: E402

DEFAULT_ORDERING_CSV = ROOT / "02_exports/btc5m_suspect_ordering/suspect_ordering_summary.csv"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache/polygon_funding_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_suspect_funding"

USDC_E = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
USDC = "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"

# Known Tornado Cash pools on Polygon (MATIC denominations). Laundering signal.
POLYGON_MIXERS = {
    "0x1e34a77868e19a6647b1f2f47b51ed72dede95dd": "tornado_100_matic",
    "0xdf231d99ff8b6c6cbf4e9b9a945cbacef9339178": "tornado_1000_matic",
    "0xaf4c0b70b2ea9fb7487c7cbb37ada259579fe040": "tornado_10000_matic",
    "0xa5c2254e4253490c54cef0a4347fddb8f75a4998": "tornado_100000_matic",
    "0x8589427373d6d84e98730d7795d8f6f8731fda16": "tornado_router",
}

# fan-out at/above this many distinct recipients => custodial/exchange/service
CEX_FANOUT_THRESHOLD = 200

# terminals identified by hand 2026-06-11 (polygonscan name-tag + upstream-funder
# pattern). All are many-user on-ramps/bridges/CEX, so two suspects sharing one
# is expected base-rate noise, not an operator link.
TERMINAL_LABELS = {
    "0x1231deb6f5749ef6ce6943a275a1d3e7486f4eae": "lifi_bridge_aggregator",
    "0x18dd3c14e34c1bc379f7538068c59160d9f68e25": "relay_onramp_solver",
    "0xca7ded7e4f4ba8ab3b10009236ae6d1b95094589": "relay_onramp_solver",
    "0xe7804c37c13166ff0b37f5ae0bb07a3aebb6e245": "high_fanout_onramp_or_cex",
    "0xa5a5491bca93dd4c076e4906e79e7673f4a5a142": "high_fanout_onramp_or_cex",
    "0xc417fd8e9661c0d2120b64a04bb3278c17e99db1": "cex_hot_wallet_also_funds_control",
}


def addr(value) -> str:
    return str(value or "").lower()


def earliest_inbound_source(transfers: list[dict], wallet: str) -> dict | None:
    """The wallet's FIRST incoming USDC transfer = its funding event.

    Funding origin must be traced by the earliest inflow, not the largest: the
    largest inflow is dominated by Polymarket trade-settlement payouts from the
    exchange contracts (winnings), which point back into trading infra, not to
    whoever capitalized the wallet.
    """
    incoming = [t for t in transfers
                if addr(t.get("to")) == wallet and addr(t.get("from")) != wallet]
    if not incoming:
        return None
    first = min(incoming, key=lambda t: (int(t.get("timeStamp") or 0), t.get("hash") or ""))
    try:
        usdc = int(first.get("value") or 0) / 10 ** int(first.get("tokenDecimal") or 6)
    except (TypeError, ValueError):
        usdc = 0.0
    return {"address": addr(first.get("from")), "usdc": usdc,
            "first_ts": int(first.get("timeStamp") or 0), "first_hash": first.get("hash")}


def fanout(transfers: list[dict], wallet: str) -> int:
    """Distinct recipients this wallet has sent USDC to (custodial fingerprint)."""
    return len({addr(t.get("to")) for t in transfers if addr(t.get("from")) == wallet})


class Tracer:
    def __init__(self, client: funding.EtherscanClient):
        self.client = client
        self._transfers: dict[str, list[dict]] = {}
        self._fanout: dict[str, int] = {}

    def transfers(self, wallet: str) -> list[dict]:
        if wallet not in self._transfers:
            rows: list[dict] = []
            for label, token in (("USDC.e", USDC_E), ("USDC", USDC)):
                got, _ = self.client.token_transfers(wallet, label, token)
                rows.extend(got)
            self._transfers[wallet] = funding.dedupe_transfers(rows)
        return self._transfers[wallet]

    def fanout(self, wallet: str) -> int:
        if wallet not in self._fanout:
            self._fanout[wallet] = fanout(self.transfers(wallet), wallet)
        return self._fanout[wallet]

    def tx_signer(self, tx_hash: str) -> str | None:
        """EOA that signed/paid for a tx. The proxy endpoint returns the result
        object directly (no status field), so request it in raw mode."""
        params = {"module": "proxy", "action": "eth_getTransactionByHash", "txhash": tx_hash}
        result = self.client._request(params, f"tx_{tx_hash}", raw=True)
        if isinstance(result, dict):
            return addr(result.get("from"))
        return None

    def classify(self, address: str) -> tuple[str, str]:
        """Return (terminal_kind, detail). terminal_kind in
        {mixer, bridge_mint, infra, cex_or_service, operator_eoa, continue}."""
        if address in POLYGON_MIXERS:
            return "mixer", POLYGON_MIXERS[address]
        if address == funding.ZERO_ADDRESS:
            return "bridge_mint", "mint_from_zero"
        if address in funding.KNOWN_INFRA:
            return "infra", funding.KNOWN_INFRA[address]
        if address in funding.KNOWN_ANNOTATED:
            return "infra", funding.KNOWN_ANNOTATED[address]
        if self.fanout(address) >= CEX_FANOUT_THRESHOLD:
            label = TERMINAL_LABELS.get(address, "unidentified")
            return "cex_or_service", f"{label} fanout={self.fanout(address)}"
        return "continue", f"fanout={self.fanout(address)}"

    def trace(self, suspect: str, max_hops: int) -> list[dict]:
        """Walk back from a suspect; one path, following the main funder each hop."""
        path: list[dict] = []
        node = suspect
        seen = {suspect}
        for hop in range(1, max_hops + 1):
            src = earliest_inbound_source(self.transfers(node), node)
            if src is None:
                path.append({"hop": hop, "from_node": node, "funder": None,
                             "terminal": "no_inbound", "detail": ""})
                break
            funder = src["address"]
            signer = None
            # if funded by the relayer or another infra forwarder, the deposit
            # signer is the real upstream party - resolve it
            resolved = funder
            if (funder in funding.KNOWN_INFRA or funder in funding.KNOWN_ANNOTATED) and src["first_hash"]:
                signer = self.tx_signer(src["first_hash"])
                if signer and signer not in (funder, node):
                    resolved = signer
            kind, detail = self.classify(resolved)
            path.append({
                "hop": hop, "from_node": node, "funder": funder,
                "tx_signer": signer, "resolved": resolved,
                "usdc": round(src["usdc"], 2),
                "first_funding_utc": datetime.fromtimestamp(src["first_ts"], tz=timezone.utc).isoformat()
                if src["first_ts"] else None,
                "terminal": kind, "detail": detail,
            })
            if kind != "continue" or resolved in seen:
                break
            seen.add(resolved)
            node = resolved
        return path


def run(args: argparse.Namespace) -> int:
    env = funding.load_env(ROOT / ".env")
    api_key = env.get("ETHERSCAN_API_KEY") or ""
    if not api_key:
        print("ETHERSCAN_API_KEY missing from .env", file=sys.stderr)
        return 2
    tracked = funding.load_tracked_wallets(Path(args.ordering_csv), args.max_perm_p)
    suspects = {w: l for w, l in tracked.items() if l != "market_maker_control"}
    print(f"tracing {len(suspects)} suspects, up to {args.max_hops} hops")
    client = funding.EtherscanClient(api_key, Path(args.cache_dir), args.sleep_seconds)
    tracer = Tracer(client)

    all_rows: list[dict] = []
    terminals: list[dict] = []
    node_reach: dict[str, set] = defaultdict(set)  # any traversed node -> suspects reaching it
    for suspect, label in suspects.items():
        path = tracer.trace(suspect, args.max_hops)
        for step in path:
            all_rows.append({"suspect": suspect, "label": label, **step})
            for key in ("funder", "tx_signer", "resolved"):
                v = step.get(key)
                if v and v not in (funding.ZERO_ADDRESS,) and v not in funding.KNOWN_INFRA:
                    node_reach[v].add(suspect)
        last = path[-1] if path else {}
        terminals.append({
            "suspect": suspect, "label": label,
            "hops_traced": len(path),
            "terminal_kind": last.get("terminal"),
            "terminal_address": last.get("resolved") or last.get("funder"),
            "terminal_detail": last.get("detail"),
        })
        end = last.get("resolved") or last.get("funder") or "-"
        print(f"{suspect[:10]}… ({label}): {len(path)} hops -> {last.get('terminal')} {str(end)[:12]}", flush=True)

    shared = [{"node": n, "n_suspects": len(s), "suspects": ";".join(sorted(s))}
              for n, s in node_reach.items() if len(s) >= 2]
    shared.sort(key=lambda r: -r["n_suspects"])

    out_dir = Path(args.out_dir)
    funding.write_csv(out_dir / "funding_chain_steps.csv", all_rows)
    funding.write_csv(out_dir / "funding_chain_terminals.csv", terminals)
    funding.write_csv(out_dir / "funding_chain_shared_nodes.csv", shared)

    mixers = [t for t in terminals if t["terminal_kind"] == "mixer"]
    kinds: dict[str, int] = defaultdict(int)
    for t in terminals:
        kinds[t["terminal_kind"]] += 1
    lines = [
        "# Suspect funding chains (multi-hop)",
        "",
        f"Generated {funding.utc_now()}. {len(suspects)} suspects, up to {args.max_hops} hops,",
        "following the earliest (funding) USDC inflow each hop and resolving the tx signer",
        "behind relayer/infra deposits.",
        "",
        f"- Mixer terminals (Tornado Cash Polygon): **{len(mixers)}**",
        f"- Terminal kinds: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())),
        f"- Nodes reached by >=2 suspects (incl. tx signers): **{len(shared)}**",
        "",
        "A shared CEX/service terminal is NOT evidence of one operator (shared",
        "custodians serve everyone). A shared low-fan-out tx signer or operator",
        "EOA WOULD be. Mixer use would explain why a chain dead-ends opaquely.",
        "",
        "## Terminals",
        "",
        "| suspect | label | hops | terminal | address | detail |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for t in terminals:
        lines.append(f"| `{t['suspect'][:10]}…` | {t['label']} | {t['hops_traced']} | "
                     f"{t['terminal_kind']} | `{str(t['terminal_address'])[:12]}…` | {t['terminal_detail']} |")
    if shared:
        lines += ["", "## Nodes reached by >= 2 suspects", "",
                  "| node | n suspects | suspects |", "| --- | ---: | --- |"]
        for r in shared:
            lines.append(f"| `{r['node']}` | {r['n_suspects']} | {r['suspects']} |")
    else:
        lines += ["", "No node (funder, tx signer, or terminal) was reached by two or more",
                  "suspects across the traced hops."]
    (out_dir / "funding_chain_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {len(all_rows)} steps, {len(terminals)} terminals, {len(shared)} shared nodes -> {out_dir}")
    print("mixer terminals:", len(mixers), "| shared nodes:", len(shared))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ordering-csv", default=str(DEFAULT_ORDERING_CSV))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-perm-p", type=float, default=0.01)
    parser.add_argument("--max-hops", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
