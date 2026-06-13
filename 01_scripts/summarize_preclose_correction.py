#!/usr/bin/env python3
"""Summarize what the pre-close filter + on-chain label correction does to the
edge-class claim: crop size, membership, and profit-if-held per cell, plus the
named durable-core wallets' corrected trajectories. Reads the original
(all-fills) and corrected (pre-close) top_edge_wallets.csv pairs.

NOTE per cell what the 'before' column actually contains: the three 5m cells
and 15m apr-jun ran on Gamma/fallback labels, so their delta = pre-close
filter + label correction combined; the 15m jan-mar 'before' cell already
carried on-chain winners (enriched universe), so its delta is the pre-close
filter ALONE."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# (label, before_dir, after_dir, what the before cell's labels were)
PAIRS = [
    ("5m jan-feb", "btc5m_wallet_edge_jan1_feb28", "btc5m_wallet_edge_jan1_feb28_preclose", "fallback labels"),
    ("5m mar-apr", "btc5m_wallet_edge_mar1_apr30", "btc5m_wallet_edge_mar1_apr30_preclose", "fallback labels"),
    ("5m may-jun", "btc5m_wallet_edge", "btc5m_wallet_edge_preclose", "fallback labels"),
    ("15m apr-jun", "btc15m_wallet_edge_apr1_jun9", "btc15m_wallet_edge_apr1_jun9_preclose", "fallback labels"),
    ("15m jan-mar", "btc15m_wallet_edge_jan1_mar31", "btc15m_wallet_edge_jan1_mar31_preclose",
     "on-chain labels already (delta = pre-close filter only)"),
]
CORE = ["0xed86741e", "0x08ea825d", "0x537494c5", "0xa3d043b2", "0xfcefc196", "0x45ca1731"]


def crop_z(r: dict) -> float:
    # market_bet_z (one bet per market) where the CSV provides it;
    # trade_edge_z only as a legacy fallback for pre-correction CSVs
    z = r.get("market_bet_z")
    return float(z) if z not in (None, "") else float(r.get("trade_edge_z") or 0)


def is_crop_member(r: dict) -> bool:
    # prefer the wallet-edge BH crop_member flag; fall back to z>=5 for old CSVs
    if int(r["n_markets"]) < 10 or float(r["edge_contested"] or 0) <= 0:
        return False
    if r.get("crop_member") not in (None, ""):
        return str(r["crop_member"]) == "1"
    return crop_z(r) >= 5


def crop(path: Path) -> dict:
    return {r["wallet"]: r for r in csv.DictReader(open(path)) if is_crop_member(r)}


def rows(path: Path) -> dict:
    return {r["wallet"]: r for r in csv.DictReader(open(path))}


print("=== EDGE CLASS: original (all fills) vs corrected (pre-close, on-chain labels) ===")
for label, before, after, before_labels in PAIRS:
    b = crop(ROOT / "02_exports" / before / "top_edge_wallets.csv")
    a = crop(ROOT / "02_exports" / after / "top_edge_wallets.csv")
    pb = sum(float(r["profit_if_held_usd"] or 0) for r in b.values())
    pa = sum(float(r["profit_if_held_usd"] or 0) for r in a.values())
    print(f"{label:12} crop {len(b):3d} -> {len(a):3d} (kept {len(set(b) & set(a))})   "
          f"profit-if-held ${pb:>10,.0f} -> ${pa:>10,.0f}   [before: {before_labels}]")

print("\n=== NAMED CORE WALLETS, corrected pre-close stats per cell ===")
print(f"{'wallet':12} {'cell':12} {'mkts':>5} {'win':>7} {'entry':>7} {'edge/sh':>8} {'z':>7} {'pnl$':>10}")
for short in CORE:
    for label, _, after, _ in PAIRS:
        table = rows(ROOT / "02_exports" / after / "top_edge_wallets.csv")
        match = [r for w, r in table.items() if w.startswith(short)]
        for r in match:
            print(f"{short:12} {label:12} {r['n_markets']:>5} {float(r['win_rate']):>6.1%} "
                  f"{float(r['avg_entry_price']):>7.3f} {float(r['edge_per_share']):>+8.3f} "
                  f"{crop_z(r):>7.1f} {float(r['profit_if_held_usd'] or 0):>10,.0f}")
