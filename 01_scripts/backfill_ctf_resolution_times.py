#!/usr/bin/env python3
"""Backfill on-chain resolution timestamps for Polymarket conditions.

For each condition_id, fetches the ConditionalTokens `ConditionResolution`
event from Polygon via the Etherscan v2 API and records WHEN the outcome
became official on-chain plus the reported payout vector. This timestamps the
close -> resolution gap that post-close fills trade inside, and independently
verifies the Gamma-derived winner label.

Event (Gnosis CTF, 0x4D97...6045):
    ConditionResolution(bytes32 indexed conditionId, address indexed oracle,
                        bytes32 indexed questionId, uint outcomeSlotCount,
                        uint[] payoutNumerators)
Both ConditionPreparation and ConditionResolution index conditionId as
topic1; they are told apart by data length (preparation carries one word).
Outcome slot order is the Gamma `outcomes` order — ["Up", "Down"] for every
BTC up/down market — so payouts [1,0] -> Up, [0,1] -> Down.

Resumable: one cached logs JSON per condition under
03_data_cache/ctf_resolution_cache/.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

API_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 137
CTF_ADDRESS = "0x4d97dcd97ec945f40cf65f87097ace5ea0476045"
DEFAULT_CACHE_DIR = ROOT / "03_data_cache/ctf_resolution_cache"
DEFAULT_CIDS_FILE = DEFAULT_CACHE_DIR / "needed_cids.txt"
DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_resolution_times"
DEFAULT_UNIVERSE_CSVS = [
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_jan1_feb28/hybrid_market_universe.csv",
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_mar1_apr30/hybrid_market_universe.csv",
    ROOT / "02_exports/btc5m_hybrid_quick_unwind_may1_present/hybrid_market_universe.csv",
]


def load_env(path: Path) -> dict[str, str]:
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


def fetch_logs(cid: str, api_key: str, cache_dir: Path, sleep_seconds: float) -> list[dict]:
    cache_path = cache_dir / f"logs_{cid}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    params = {"module": "logs", "action": "getLogs", "address": CTF_ADDRESS,
              "fromBlock": 0, "toBlock": "latest", "topic1": cid,
              "chainid": CHAIN_ID, "apikey": api_key}
    request = Request(f"{API_URL}?{urlencode(params)}",
                      headers={"User-Agent": "btc5m-resolution-times/0.1"})
    for attempt in range(6):
        try:
            with urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, json.JSONDecodeError):
            time.sleep(2.0 * (attempt + 1))
            continue
        time.sleep(sleep_seconds)
        message = str(body.get("message") or "")
        result = body.get("result")
        if body.get("status") == "1" or "No records found" in message:
            payload = result if isinstance(result, list) else []
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        # rate limits and transient server errors are both retryable; only a
        # persistent failure (bad key, unsupported params) falls through
        time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"etherscan request kept failing: {cid}")


def hexint(value) -> int | None:
    try:
        s = str(value)
        return int(s, 16) if s.startswith("0x") else int(s)
    except (TypeError, ValueError):
        return None


def decode_resolution(logs: list[dict]) -> dict | None:
    """Pick the ConditionResolution log (data >= 4 words) and decode it."""
    for log in logs:
        data = str(log.get("data") or "")
        if not data.startswith("0x"):
            continue
        words = [data[2 + i * 64:2 + (i + 1) * 64] for i in range((len(data) - 2) // 64)]
        if len(words) < 4:
            continue  # ConditionPreparation
        slot_count = int(words[0], 16)
        array_len = int(words[2], 16)
        payouts = [int(w, 16) for w in words[3:3 + array_len]]
        return {"resolved_ts": hexint(log.get("timeStamp")),
                "block_number": hexint(log.get("blockNumber")),
                "tx_hash": log.get("transactionHash"),
                "outcome_slot_count": slot_count,
                "payout_numerators": payouts}
    return None


def onchain_winner(payouts: list[int]) -> str:
    """Outcome slot order for BTC up/down markets is ["Up", "Down"]."""
    if payouts == [1, 0]:
        return "Up"
    if payouts == [0, 1]:
        return "Down"
    return f"other:{payouts}"


def run(args: argparse.Namespace) -> int:
    env = load_env(ROOT / ".env")
    api_key = env.get("ETHERSCAN_API_KEY", "")
    if not api_key:
        raise SystemExit("ETHERSCAN_API_KEY missing from .env")

    cids = [line.strip() for line in Path(args.cids_file).read_text().splitlines() if line.strip()]
    universe: dict[str, dict] = {}
    for path in args.universe_csv:
        for r in csv.DictReader(open(path, newline="")):
            cid = r.get("condition_id")
            if not cid:
                continue
            try:
                universe[cid] = {"end_epoch": int(float(r["end_epoch"])),
                                 "winner": r.get("winner"),
                                 "margin_bps_abs": r.get("official_margin_bps_abs") or r.get("margin_bps_abs"),
                                 "slug": r.get("slug")}
            except (KeyError, TypeError, ValueError):
                continue

    cache_dir = Path(args.cache_dir)
    rows = []
    n_missing = n_disagree = 0
    for i, cid in enumerate(cids, start=1):
        logs = fetch_logs(cid, api_key, cache_dir, args.sleep_seconds)
        res = decode_resolution(logs)
        meta = universe.get(cid, {})
        if res is None:
            n_missing += 1
            rows.append({"condition_id": cid, "slug": meta.get("slug"), "resolved": 0})
            continue
        end_epoch = meta.get("end_epoch")
        winner = onchain_winner(res["payout_numerators"])
        agree = (winner == meta.get("winner")) if meta.get("winner") in ("Up", "Down") else None
        if agree is False:
            n_disagree += 1
        rows.append({
            "condition_id": cid, "slug": meta.get("slug"), "resolved": 1,
            "end_epoch": end_epoch, "resolved_ts": res["resolved_ts"],
            "resolution_lag_s": (res["resolved_ts"] - end_epoch) if end_epoch else None,
            "onchain_winner": winner, "gamma_winner": meta.get("winner"),
            "winner_agree": agree, "margin_bps_abs": meta.get("margin_bps_abs"),
            "block_number": res["block_number"], "tx_hash": res["tx_hash"],
        })
        if i % 50 == 0 or i == len(cids):
            print(f"fetched {i}/{len(cids)} (missing {n_missing}, disagreements {n_disagree})", flush=True)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(out_dir / "resolution_times.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    lags = sorted(r["resolution_lag_s"] for r in rows
                  if r.get("resolution_lag_s") is not None and r["resolution_lag_s"] >= 0)
    manifest = {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "01_scripts/backfill_ctf_resolution_times.py",
        "n_conditions": len(cids), "n_resolved": len(lags),
        "n_missing_resolution": n_missing, "n_winner_disagreements": n_disagree,
        "resolution_lag_s": {
            "p10": lags[int(len(lags) * 0.10)] if lags else None,
            "median": lags[len(lags) // 2] if lags else None,
            "p90": lags[int(len(lags) * 0.90)] if lags else None,
            "max": lags[-1] if lags else None,
        },
    }
    (out_dir / "backfill_manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=1))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cids-file", default=str(DEFAULT_CIDS_FILE))
    parser.add_argument("--universe-csv", action="append", default=None,
                        help="repeatable; defaults to the three 5m hybrid universes")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    args = parser.parse_args()
    if not args.universe_csv:
        args.universe_csv = [str(p) for p in DEFAULT_UNIVERSE_CSVS]
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
