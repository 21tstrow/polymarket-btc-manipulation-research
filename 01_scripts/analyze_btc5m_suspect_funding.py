#!/usr/bin/env python3
"""On-chain funding graph for the push-concentrated suspect wallets (TODO #2).

The suspects are Polymarket proxy wallets on Polygon. Wallet rotation cannot
launder the money trail: if the same operator runs several of them, they tend
to share a funding source, a withdrawal destination, or transfer to each other
directly. This script pulls each suspect's USDC.e / USDC transfer history from
the Etherscan multichain API (chainid=137) and looks for:

  1. direct suspect-to-suspect transfers (strongest link);
  2. shared non-infrastructure counterparties (same address funds or receives
     from >= 2 suspects);
  3. shared first funder, one hop up: who funded the funders.

The symmetric market-maker control wallet is included to calibrate what shared
"infrastructure" looks like: any counterparty it also touches (exchange
contracts, relayers, CEX hot wallets) is weak evidence of common control.
Bridge deposits mint from the zero address and hide the source; CEX hot
wallets are shared across unrelated customers - both are annotated, not
treated as operator links.

Suspect list defaults to `02_exports/btc5m_suspect_ordering/`: wallets whose
markets carry outsized pushes (push_perm_p <= 0.01) plus the control.

Requires ETHERSCAN_API_KEY in the repo-root `.env` (free tier is enough).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ORDERING_CSV = ROOT / "02_exports/btc5m_suspect_ordering/suspect_ordering_summary.csv"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache/polygon_funding_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_suspect_funding"

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 137
TOKENS = {
    "USDC.e": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
    "USDC": "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
}
PAGE_SIZE = 1000
ASC_PAGES = 10   # earliest history (funding)
DESC_PAGES = 2   # most recent history (withdrawals) for hyperactive wallets

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
KNOWN_INFRA = {
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e": "polymarket_ctf_exchange",
    "0xc5d563a36ae78145c45a50134d48a1215220f80a": "polymarket_negrisk_exchange",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296": "polymarket_negrisk_adapter",
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045": "polymarket_conditional_tokens",
    "0xf70da97812cb96acdf810712aa562db8dfa3dbef": "polymarket_relayer",
    ZERO_ADDRESS: "bridge_mint_burn",
    # identified on-chain 2026-06-11 (eth_getCode / getsourcecode probes)
    "0xe3f18acc55091e2c48d883fc8c8413319d4ab7b0": "polymarket_fee_module",
    "0xb768891e3130f6df18214ac804d4db76c2c37730": "polymarket_negrisk_fee_module",
    "0x3a3bd7bb9528e159577f7c2e685cc81a765002e2": "polymarket_wrapped_collateral",
    "0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb": "polymarket_collateral_token",
    "0x3a9418b2651c8164db5ebc56f12008137865e0f7": "polymarket_rewards_distributor",
    "0xd36ec33c8bed5a9f7b6630855f1533455b98a418": "uniswap_v3_usdc_pool",
}
# explained but worth keeping visible: these group wallets by shared *tooling*
# or *venue*, which is weaker than shared control
KNOWN_ANNOTATED = {
    "0xe09b3943b5a2fd4b2d58d5a185111531e2c62679": "other_polymarket_user_proxy_trade_fills",
    "0x60c93de9da6cf3626d2c8bc2cdb42f5f86c64f24": "bot_service_fee_collector_~200_clients",
    "0xc417fd8e9661c0d2120b64a04bb3278c17e99db1": "high_volume_eoa_likely_cex_hot_wallet",
}


def load_env(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE parser for the repo-root .env (comments/blank lines ok)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def transfer_key(t: dict) -> tuple:
    return (t.get("hash"), t.get("from"), t.get("to"), t.get("value"),
            t.get("contractAddress"))


def dedupe_transfers(transfers: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for t in transfers:
        key = transfer_key(t)
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def first_incoming(transfers: list[dict], wallet: str) -> dict | None:
    """Earliest incoming transfer (mint-from-zero counts: it is a bridge deposit)."""
    incoming = [t for t in transfers if str(t.get("to", "")).lower() == wallet]
    if not incoming:
        return None
    return min(incoming, key=lambda t: (int(t.get("timeStamp") or 0), t.get("hash") or ""))


def counterparty_stats(transfers: list[dict], wallet: str) -> dict[tuple[str, str], dict]:
    """(counterparty, direction) -> {n, total_usdc}. Direction is in/out of wallet."""
    stats: dict[tuple[str, str], dict] = defaultdict(lambda: {"n": 0, "total_usdc": 0.0})
    for t in transfers:
        frm = str(t.get("from", "")).lower()
        to = str(t.get("to", "")).lower()
        try:
            amount = int(t.get("value") or 0) / 10 ** int(t.get("tokenDecimal") or 6)
        except (TypeError, ValueError):
            amount = 0.0
        if to == wallet and frm != wallet:
            cell = stats[(frm, "in")]
        elif frm == wallet and to != wallet:
            cell = stats[(to, "out")]
        else:
            continue
        cell["n"] += 1
        cell["total_usdc"] += amount
    return stats


def classify_counterparty(address: str, wallets_touching: set, control_wallet: str,
                          n_tracked: int) -> str:
    if address in KNOWN_INFRA:
        return KNOWN_INFRA[address]
    if address in KNOWN_ANNOTATED:
        return KNOWN_ANNOTATED[address]
    if control_wallet in wallets_touching:
        return "shared_with_control_likely_infra_or_cex"
    if len(wallets_touching) >= max(2, n_tracked - 2):
        return "high_degree_likely_infra_or_cex"
    return "candidate_operator_link"


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value, digits=2):
    if value is None or value == "":
        return "-"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)


class EtherscanClient:
    def __init__(self, api_key: str, cache_dir: Path, sleep_seconds: float):
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.sleep_seconds = sleep_seconds

    def _request(self, params: dict, cache_name: str, raw: bool = False):
        """Account-module call (status-checked) by default. With raw=True, return
        the JSON-RPC `result` as-is - needed for proxy-module calls like
        eth_getTransactionByHash, which have no status/message envelope."""
        cache_path = self.cache_dir / f"{cache_name}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        query = dict(params, chainid=CHAIN_ID, apikey=self.api_key)
        url = f"{API_URL}?{urlencode(query)}"
        request = Request(url, headers={"User-Agent": "btc5m-suspect-funding/0.1"})
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    body = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, json.JSONDecodeError):
                time.sleep(2.0 * (attempt + 1))
                continue
            time.sleep(self.sleep_seconds)
            message = str(body.get("message") or "")
            result = body.get("result")
            if raw:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(result), encoding="utf-8")
                return result
            if body.get("status") == "1" or message == "No transactions found":
                payload = result if isinstance(result, list) else []
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
                return payload
            if "rate limit" in str(result).lower() or "rate limit" in message.lower():
                time.sleep(2.0 * (attempt + 1))
                continue
            # hard API error (bad key, unsupported params): fail loudly
            raise RuntimeError(f"etherscan error: {message} / {result}")
        raise RuntimeError(f"etherscan request kept failing: {cache_name}")

    def token_transfers(self, wallet: str, token_label: str, token_address: str) -> tuple[list[dict], bool]:
        """All cached/fetched transfers for wallet+token. Returns (transfers, truncated)."""
        transfers: list[dict] = []
        truncated = False
        for sort_order, max_pages in (("asc", ASC_PAGES), ("desc", DESC_PAGES)):
            for page in range(1, max_pages + 1):
                params = {"module": "account", "action": "tokentx",
                          "contractaddress": token_address, "address": wallet,
                          "page": page, "offset": PAGE_SIZE, "sort": sort_order}
                name = f"{wallet}_{token_label}_{sort_order}_p{page}"
                rows = self._request(params, name)
                transfers.extend(rows)
                if len(rows) < PAGE_SIZE:
                    break
            else:
                if sort_order == "asc":
                    truncated = True
        return dedupe_transfers(transfers), truncated


def load_tracked_wallets(ordering_csv: Path, max_perm_p: float,
                         extra_wallets: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if ordering_csv.exists():
        for r in csv.DictReader(open(ordering_csv, newline="")):
            wallet = str(r.get("wallet") or "").lower()
            label = r.get("label") or ""
            if not wallet:
                continue
            if label == "market_maker_control":
                out[wallet] = label
                continue
            try:
                perm_p = float(r.get("push_perm_p") or "nan")
            except ValueError:
                continue
            if perm_p <= max_perm_p:
                out[wallet] = label
    # named wallets traced regardless of the ordering screen (e.g. the
    # corrected durable core, which the pre-correction suspect list never
    # covered): comma-separated, each as addr or addr:label
    for item in (extra_wallets or "").split(","):
        item = item.strip()
        if not item:
            continue
        addr, _, label = item.partition(":")
        out.setdefault(addr.lower(), label or "named_core")
    return out


def run(args: argparse.Namespace) -> int:
    env = load_env(ROOT / ".env")
    api_key = env.get("ETHERSCAN_API_KEY") or ""
    if not api_key:
        print("ETHERSCAN_API_KEY missing from .env", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    tracked = load_tracked_wallets(Path(args.ordering_csv), args.max_perm_p,
                                   getattr(args, "extra_wallets", ""))
    control = next((w for w, l in tracked.items() if l == "market_maker_control"), "")
    print(f"tracked wallets: {len(tracked)} ({sum(1 for l in tracked.values() if l != 'market_maker_control')} suspects + control)")
    client = EtherscanClient(api_key, Path(args.cache_dir), args.sleep_seconds)

    transfers_by_wallet: dict[str, list[dict]] = {}
    summary_rows: list[dict] = []
    counterparty_rows: list[dict] = []
    touch_map: dict[str, set] = defaultdict(set)  # counterparty -> tracked wallets touching it

    for wallet, label in tracked.items():
        all_transfers: list[dict] = []
        truncated_any = False
        for token_label, token_address in TOKENS.items():
            transfers, truncated = client.token_transfers(wallet, token_label, token_address)
            all_transfers.extend(transfers)
            truncated_any = truncated_any or truncated
        all_transfers = dedupe_transfers(all_transfers)
        transfers_by_wallet[wallet] = all_transfers
        first = first_incoming(all_transfers, wallet)
        stats = counterparty_stats(all_transfers, wallet)
        for (counterparty, direction), cell in stats.items():
            touch_map[counterparty].add(wallet)
            counterparty_rows.append({
                "wallet": wallet, "label": label, "counterparty": counterparty,
                "direction": direction, "n_transfers": cell["n"],
                "total_usdc": round(cell["total_usdc"], 2),
            })
        first_ts = int(first.get("timeStamp") or 0) if first else None
        summary_rows.append({
            "wallet": wallet, "label": label,
            "n_transfers_seen": len(all_transfers),
            "history_truncated": int(truncated_any),
            "first_funder": str(first.get("from", "")).lower() if first else None,
            "first_funder_tag": KNOWN_INFRA.get(str(first.get("from", "")).lower(), "") if first else None,
            "first_funding_usdc": (int(first.get("value") or 0) / 10 ** int(first.get("tokenDecimal") or 6)) if first else None,
            "first_funding_utc": datetime.fromtimestamp(first_ts, tz=timezone.utc).isoformat() if first_ts else None,
        })
        print(f"{wallet[:10]}… ({label}): {len(all_transfers)} transfers"
              f"{' [truncated]' if truncated_any else ''}", flush=True)

    # direct suspect-to-suspect transfers
    direct_rows: list[dict] = []
    tracked_set = set(tracked)
    for wallet, transfers in transfers_by_wallet.items():
        for t in transfers:
            frm = str(t.get("from", "")).lower()
            to = str(t.get("to", "")).lower()
            if frm in tracked_set and to in tracked_set and frm != to and wallet == frm:
                ts = int(t.get("timeStamp") or 0)
                direct_rows.append({
                    "from_wallet": frm, "from_label": tracked[frm],
                    "to_wallet": to, "to_label": tracked[to],
                    "usdc": int(t.get("value") or 0) / 10 ** int(t.get("tokenDecimal") or 6),
                    "utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                    "tx_hash": t.get("hash"),
                })

    # shared counterparties across tracked wallets
    shared_rows: list[dict] = []
    for counterparty, wallets in sorted(touch_map.items(), key=lambda kv: -len(kv[1])):
        if len(wallets) < 2 or counterparty in tracked_set:
            continue
        suspects_touching = sorted(w for w in wallets if tracked[w] != "market_maker_control")
        if not suspects_touching:
            continue
        shared_rows.append({
            "counterparty": counterparty,
            "n_tracked_wallets": len(wallets),
            "n_suspects": len(suspects_touching),
            "touches_control": int(control in wallets),
            "classification": classify_counterparty(counterparty, wallets, control, len(tracked)),
            "suspect_wallets": ";".join(suspects_touching),
        })

    # one hop up: who funded the first funders (skip infra/bridge)
    hop_rows: list[dict] = []
    funders = {r["first_funder"] for r in summary_rows
               if r["first_funder"] and r["first_funder"] not in KNOWN_INFRA}
    for funder in sorted(funders):
        transfers, _ = client.token_transfers(funder, "USDC.e", TOKENS["USDC.e"])
        first = first_incoming(transfers, funder)
        funded = sorted(r["wallet"] for r in summary_rows if r["first_funder"] == funder)
        hop_rows.append({
            "funder": funder,
            "funds_tracked_wallets": ";".join(funded),
            "funder_first_funder": str(first.get("from", "")).lower() if first else None,
            "funder_first_funder_tag": KNOWN_INFRA.get(str(first.get("from", "")).lower(), "") if first else None,
            "funder_n_transfers_seen": len(transfers),
        })

    write_csv(out_dir / "wallet_funding_summary.csv", summary_rows)
    write_csv(out_dir / "counterparties.csv", counterparty_rows)
    write_csv(out_dir / "shared_counterparties.csv", shared_rows)
    write_csv(out_dir / "suspect_to_suspect_transfers.csv", direct_rows)
    write_csv(out_dir / "funder_second_hop.csv", hop_rows)

    candidate_links = [r for r in shared_rows if r["classification"] == "candidate_operator_link"]
    lines = [
        "# Suspect wallet funding graph (Polygon USDC)",
        "",
        f"Generated {utc_now()}. {len(tracked) - 1} push-concentrated suspects + the",
        "market-maker control. Links shared with the control or with near-everyone",
        "are infrastructure/CEX, not operator evidence; bridge deposits (mint from",
        "0x0) hide their source. Polymarket fills settle USDC directly between user",
        "proxies, so proxy-contract counterparties are trade fills, not funding.",
        "For wallets marked history_truncated only the earliest ~10k and latest ~2k",
        "transfers are visible, so 'does not touch the control' is not airtight for",
        "high-volume counterparties.",
        "",
        f"- Direct suspect-to-suspect transfers: **{len(direct_rows)}**",
        f"- Shared counterparties (>=2 suspects): {len(shared_rows)}, of which",
        f"  **{len(candidate_links)}** classify as candidate operator links",
        "",
        "## First funding",
        "",
        "| wallet | label | first funder | tag | amount | when |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for r in summary_rows:
        lines.append(
            f"| `{r['wallet'][:10]}…` | {r['label']} | `{(r['first_funder'] or '-')[:14]}…` | "
            f"{r['first_funder_tag'] or '-'} | {fmt(r['first_funding_usdc'])} | {r['first_funding_utc'] or '-'} |")
    if candidate_links:
        lines += ["", "## Candidate operator links", "",
                  "| counterparty | suspects | touches control |", "| --- | --- | --- |"]
        for r in candidate_links:
            lines.append(f"| `{r['counterparty']}` | {r['suspect_wallets']} | {r['touches_control']} |")
    if direct_rows:
        lines += ["", "## Direct transfers between tracked wallets", "",
                  "| from | to | USDC | when |", "| --- | --- | ---: | --- |"]
        for r in direct_rows:
            lines.append(f"| `{r['from_wallet'][:10]}…` | `{r['to_wallet'][:10]}…` | "
                         f"{fmt(r['usdc'])} | {r['utc']} |")
    (out_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readme = [
        "# BTC 5m suspect funding graph",
        "",
        f"Generated {utc_now()} by `01_scripts/analyze_btc5m_suspect_funding.py`.",
        "Etherscan multichain API (Polygon, chainid=137); raw pages cached in",
        "`03_data_cache/polygon_funding_cache/`. API keys live in the repo-root `.env`.",
        "",
        "- `wallet_funding_summary.csv` - per tracked wallet: first funder, transfer counts.",
        "- `counterparties.csv` - per (wallet, counterparty, direction) USDC totals.",
        "- `shared_counterparties.csv` - addresses touching >=2 suspects, classified.",
        "- `suspect_to_suspect_transfers.csv` - direct transfers between tracked wallets.",
        "- `funder_second_hop.csv` - who funded the first funders.",
        "- `analysis_report.md` - summary with interpretation caveats.",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote {len(summary_rows)} wallets, {len(shared_rows)} shared counterparties, "
          f"{len(direct_rows)} direct transfers -> {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ordering-csv", default=str(DEFAULT_ORDERING_CSV))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-perm-p", type=float, default=0.01)
    parser.add_argument("--extra-wallets", default="",
                        help="comma-separated addr[:label] traced regardless of the "
                             "ordering screen (e.g. the corrected durable core)")
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
