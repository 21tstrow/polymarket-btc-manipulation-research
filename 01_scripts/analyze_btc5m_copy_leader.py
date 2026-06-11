#!/usr/bin/env python3
"""Find the copy-trade LEADER behind the bot-service follower wallets.

The fee collector 0x60c93de9 takes a ~0.5%/trade rake in pUSD from hundreds of
client wallets running a commercial Polymarket copy/sniper bot. Copy bots
mirror a leader's fills on-chain within ~1-2 seconds, so the leader is visible
in the cached trade data by construction:

  follower event   = a follower wallet's BUY in (market, outcome) at second t;
  lead event for W = wallet W bought the same (market, outcome) in [t-3, t-1];
  lag event for W  = same but in [t+1, t+3].

A real leader (a) leads many *distinct* followers, (b) is strongly asymmetric
(leads >> lags - mirrors react to it, never the reverse), and (c) has a high
conversion rate (a large share of its own trades are mirrored within 3s).
A high-volume market maker fails (b): it sits on both sides of everyone's
timestamps symmetrically. Followers can also "lead" each other (fast vs slow
mirrors of the same signal), so candidates that are themselves followers are
tagged rather than dropped.

Followers = senders of fee payments into the collector (any token - fees were
USDC.e in 2025, pUSD in 2026), fetched via the Etherscan client and cached.
Trade data = the cached close-contests trade files (final ~300s per market).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (SRC, ROOT / "01_scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from polymarket_research.btc5m_config import product_fields  # noqa: E402

import analyze_btc5m_suspect_funding as funding  # noqa: E402

DEFAULT_TRADES_DIR = ROOT / "03_data_cache/polymarket_btc5m_close_contests_cache/trades"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache/polygon_funding_cache"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_copy_leader"

FEE_COLLECTOR = "0x60c93de9da6cf3626d2c8bc2cdb42f5f86c64f24"
WATCH_WALLETS = {
    "0xc5d521074e88279556836998fb2a5d2e2c1c6caa": "directional_suspect",
    "0x30be23d0622ae9ea3072a0091c214c78cdcbf4c1": "directional_suspect",
    "0x32ec633aa376cfe621e2a34e978244d61291645e": "directional_suspect",
    "0x6d9f6ea54a3aaac3ceee0a0a9579da944ccb5568": "directional_suspect",
    "0x97e1678857baa09aeeec1ac7c0a4e732ab836825": "window_dressing",
    "0xa6214292fba769fc1c0a11c3191cefe197bf6e29": "window_dressing",
    "0xbe9188e967077bbca786cbcf7f052e00ee27c74d": "window_dressing",
    "0x93173b86dbe2f2dd9922c751806d306b48cf5a5f": "window_dressing",
    "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30": "market_maker_control",
}


def fetch_followers(client: funding.EtherscanClient, collector: str,
                    max_pages: int = 10) -> set[str]:
    """Distinct senders of fee payments into the collector (any token)."""
    followers: set[str] = set()
    for sort_order in ("asc", "desc"):
        for page in range(1, max_pages + 1):
            params = {"module": "account", "action": "tokentx", "address": collector,
                      "page": page, "offset": 1000, "sort": sort_order}
            rows = client._request(params, f"{collector}_alltok_{sort_order}_p{page}")
            for t in rows:
                if str(t.get("to", "")).lower() == collector:
                    frm = str(t.get("from", "")).lower()
                    if frm and frm != collector:
                        followers.add(frm)
            if len(rows) < 1000:
                break
    return followers


def group_market_files(trades_dir: Path) -> dict[str, list[Path]]:
    """condition_id -> its cached page files (cid_offset.json)."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in trades_dir.glob("*.json"):
        cid = path.stem.rsplit("_", 1)[0]
        groups[cid].append(path)
    return groups


def load_market_buys(paths: list[Path]) -> list[tuple[int, str, str]]:
    """All BUY fills in a market as (timestamp, wallet, outcome), deduped."""
    out: set[tuple[int, str, str]] = set()
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - skip malformed cache files
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            if str(t.get("side") or "").upper() != "BUY":
                continue
            outcome = str(t.get("outcome") or "")
            if outcome not in ("Up", "Down"):
                continue
            wallet = str(t.get("proxyWallet") or "").lower()
            ts = int(t.get("timestamp") or 0)
            if wallet and ts:
                out.add((ts, wallet, outcome))
    return sorted(out)


def match_events(buys: list[tuple[int, str, str]], followers: set[str],
                 window: int = 3):
    """Per market: count lead/lag/same-second co-trades around follower events.

    Returns (pair_lead, pair_lag, pair_same, follower_events, wallet_trades)
      pair_*        : (candidate, follower) -> event count
      follower_events: follower -> event count
      wallet_trades : candidate wallet -> distinct (second, outcome) trade count
    """
    pair_lead: dict[tuple[str, str], int] = defaultdict(int)
    pair_lag: dict[tuple[str, str], int] = defaultdict(int)
    pair_same: dict[tuple[str, str], int] = defaultdict(int)
    follower_events: dict[str, int] = defaultdict(int)
    wallet_trades: dict[str, int] = defaultdict(int)

    by_outcome: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for ts, wallet, outcome in buys:
        by_outcome[outcome].append((ts, wallet))
        wallet_trades[wallet] += 1

    for outcome, rows in by_outcome.items():
        # follower events collapsed to one per (follower, second)
        f_events = sorted({(ts, w) for ts, w in rows if w in followers})
        if not f_events:
            continue
        for ts, follower in f_events:
            follower_events[follower] += 1
            lo, hi = ts - window, ts + window
            # rows are sorted by ts; market windows are ~300s so linear scan
            # bounded by bisect is unnecessary at this scale
            seen_lead: set[str] = set()
            seen_lag: set[str] = set()
            seen_same: set[str] = set()
            for ts2, w2 in rows:
                if ts2 < lo:
                    continue
                if ts2 > hi:
                    break
                if w2 == follower:
                    continue
                if ts2 < ts:
                    seen_lead.add(w2)
                elif ts2 > ts:
                    seen_lag.add(w2)
                else:
                    seen_same.add(w2)
            for w2 in seen_lead:
                pair_lead[(w2, follower)] += 1
            for w2 in seen_lag:
                pair_lag[(w2, follower)] += 1
            for w2 in seen_same:
                pair_same[(w2, follower)] += 1
    return pair_lead, pair_lag, pair_same, follower_events, wallet_trades


def run(args: argparse.Namespace) -> int:
    env = funding.load_env(ROOT / ".env")
    api_key = env.get("ETHERSCAN_API_KEY") or ""
    if not api_key:
        print("ETHERSCAN_API_KEY missing from .env", file=sys.stderr)
        return 2
    client = funding.EtherscanClient(api_key, Path(args.cache_dir), args.sleep_seconds)
    followers = fetch_followers(client, FEE_COLLECTOR.lower())
    print(f"followers (bot-fee payers): {len(followers)}")

    groups = group_market_files(Path(args.trades_dir))
    print(f"cached markets: {len(groups)}")

    lead: dict[tuple[str, str], int] = defaultdict(int)
    lag: dict[tuple[str, str], int] = defaultdict(int)
    same: dict[tuple[str, str], int] = defaultdict(int)
    fol_events: dict[str, int] = defaultdict(int)
    trades_total: dict[str, int] = defaultdict(int)
    markets_led: dict[str, set] = defaultdict(set)

    for i, (cid, paths) in enumerate(sorted(groups.items()), start=1):
        buys = load_market_buys(paths)
        if buys:
            p_lead, p_lag, p_same, f_ev, w_tr = match_events(buys, followers, args.window)
            for k, v in p_lead.items():
                lead[k] += v
                markets_led[k[0]].add(cid)
            for k, v in p_lag.items():
                lag[k] += v
            for k, v in p_same.items():
                same[k] += v
            for k, v in f_ev.items():
                fol_events[k] += v
            for k, v in w_tr.items():
                trades_total[k] += v
        if i % 1000 == 0 or i == len(groups):
            print(f"scanned {i}/{len(groups)} markets", flush=True)

    total_follower_events = sum(fol_events.values())
    print(f"follower BUY events in cache: {total_follower_events} "
          f"from {len(fol_events)} active followers")

    # aggregate per candidate
    cand_lead: dict[str, int] = defaultdict(int)
    cand_lag: dict[str, int] = defaultdict(int)
    cand_same: dict[str, int] = defaultdict(int)
    cand_followers: dict[str, set] = defaultdict(set)
    for (w, f), v in lead.items():
        cand_lead[w] += v
        cand_followers[w].add(f)
    for (w, f), v in lag.items():
        cand_lag[w] += v
    for (w, f), v in same.items():
        cand_same[w] += v

    rows = []
    for w, n_lead in cand_lead.items():
        n_lag = cand_lag.get(w, 0)
        decided = n_lead + n_lag
        if n_lead < args.min_lead_events:
            continue
        rows.append({
            **product_fields(),
            "wallet": w,
            "is_follower": int(w in followers),
            "watch_label": WATCH_WALLETS.get(w, ""),
            "n_lead_events": n_lead,
            "n_lag_events": n_lag,
            "n_same_second": cand_same.get(w, 0),
            "lead_ratio": n_lead / decided if decided else None,
            "n_distinct_followers_led": len(cand_followers[w]),
            "n_markets_led": len(markets_led[w]),
            "own_trades": trades_total.get(w, 0),
            "conversion_rate": n_lead / trades_total[w] if trades_total.get(w) else None,
            "share_of_all_follower_events": n_lead / total_follower_events
            if total_follower_events else None,
        })
    rows.sort(key=lambda r: (-r["n_distinct_followers_led"], -r["n_lead_events"]))

    out_dir = Path(args.out_dir)
    funding.write_csv(out_dir / "leader_candidates.csv", rows)

    top = [r for r in rows
           if r["n_distinct_followers_led"] >= args.min_followers
           and (r["lead_ratio"] or 0) >= args.min_lead_ratio]
    lines = [
        "# Copy-trade leader search",
        "",
        f"Generated {funding.utc_now()}. {len(followers)} bot-fee-paying follower",
        f"wallets; {total_follower_events} follower BUY events across",
        f"{len(groups)} cached markets (final ~300s windows, May-Jun + partial",
        "Jan-Apr). Candidate = wallet trading same market+direction 1-",
        f"{args.window}s before a follower event.",
        "",
        "Leader signature = high lead_ratio (asymmetry), many distinct followers,",
        "high conversion_rate (share of its own trades that get mirrored).",
        "Symmetric high-volume wallets are market makers, not leaders. Candidates",
        "that are themselves followers are fast mirrors of the true signal.",
        "",
        f"## Candidates with >= {args.min_followers} distinct followers and lead_ratio >= {args.min_lead_ratio}",
        "",
        "| wallet | follower? | watch | leads | lags | ratio | followers | markets | own trades | conversion |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in top[:25]:
        lines.append(
            f"| `{r['wallet'][:12]}…` | {r['is_follower']} | {r['watch_label'] or '-'} | "
            f"{r['n_lead_events']} | {r['n_lag_events']} | {r['lead_ratio']:.2f} | "
            f"{r['n_distinct_followers_led']} | {r['n_markets_led']} | {r['own_trades']} | "
            f"{(r['conversion_rate'] or 0):.2f} |")
    if not top:
        lines.append("(none cleared the bar)")
    (out_dir / "analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readme = [
        "# BTC 5m copy-trade leader search",
        "",
        f"Generated {funding.utc_now()} by `01_scripts/analyze_btc5m_copy_leader.py`.",
        "",
        "- `leader_candidates.csv` - per candidate wallet: lead/lag counts vs the",
        "  bot-service follower base, asymmetry, distinct followers, conversion.",
        "- `analysis_report.md` - top candidates with the leader signature.",
        "",
        "Followers = fee payers into the bot collector 0x60c93de9 (cached",
        "Etherscan pages). Trades = cached close-contests files (final ~300s).",
    ]
    (out_dir / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} candidates -> {out_dir}")
    for r in top[:8]:
        print(f"  LEADER? {r['wallet']} leads {r['n_distinct_followers_led']} followers, "
              f"{r['n_lead_events']} events, ratio {r['lead_ratio']:.2f}, "
              f"conversion {(r['conversion_rate'] or 0):.2f} {r['watch_label']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades-dir", default=str(DEFAULT_TRADES_DIR))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--min-lead-events", type=int, default=10)
    parser.add_argument("--min-followers", type=int, default=5)
    parser.add_argument("--min-lead-ratio", type=float, default=0.6)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    return parser.parse_args()


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
