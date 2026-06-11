#!/usr/bin/env python3
"""Multi-hop funding chains for the push-concentrated suspect wallets.

Extends the one-hop funding graph (`analyze_btc5m_suspect_funding.py`) with the
three checks a one-hop scan cannot make:

  1. Recursive backward trace - follow each suspect's early USDC inflows
     funder-by-funder until a deadend: bridge mint, CEX-like high-volume
     wallet, Polymarket infra, an unverified service contract, or the depth
     cap. Then compare: do different suspects' chains converge on a shared
     address before the deadend, and do they deadend at the same venue?
  2. Relayer bypass - five wallets were first funded by the Polymarket
     relayer, which sweeps user deposits and so masks the true source. For
     each relayer-funded deposit, scan the relayer's own transfers in the
     surrounding blocks for the matching-amount inbound transfer; its sender
     is the true depositor.
  3. Initiator extraction - for every funding transaction, pull the EOA that
     *initiated* the tx (`tx.from`). Contract-mediated deposits (swaps,
     bridge claims, forwarders) are initiated by the user's own gas wallet.
     Two suspects sharing an initiator is operator-level evidence that
     survives any number of USDC hops.

Mixer screen: every traced address is checked for mixer-style naming
(Tornado/Privacy/Mixer in the verified contract name) and flagged. Note the
honest limit: an unverified custom mixer would only show up as an unverified
contract node in the chain, not as a positive mixer ID.

Reads ETHERSCAN_API_KEY from the repo-root `.env`; raw responses cached in
`03_data_cache/polygon_funding_cache/`.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "analyze_btc5m_suspect_funding", ROOT / "01_scripts/analyze_btc5m_suspect_funding.py")
assert _SPEC is not None and _SPEC.loader is not None
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

DEFAULT_OUT_DIR = ROOT / "02_exports/btc5m_suspect_funding_chains"
RELAYER = "0xf70da97812cb96acdf810712aa562db8dfa3dbef"
USDCE = base.TOKENS["USDC.e"]

# volume above which an EOA is treated as a venue (CEX/processor), not a person
CEX_LIKE_TRANSFER_THRESHOLD = 3000
MIXER_NAME_HINTS = ("tornado", "mixer", "privacy", "cyclone")


def early_funders(transfers: list[dict], wallet: str, *, max_funders: int,
                  min_usdc: float, exclude: set) -> list[dict]:
    """Top inbound senders by USDC within the wallet's earliest history."""
    totals: dict[str, dict] = defaultdict(lambda: {"usdc": 0.0, "first_ts": None,
                                                   "first_hash": None, "first_block": None})
    for t in sorted(transfers, key=lambda t: int(t.get("timeStamp") or 0)):
        frm = str(t.get("from", "")).lower()
        if str(t.get("to", "")).lower() != wallet or frm == wallet or frm in exclude:
            continue
        try:
            amount = int(t.get("value") or 0) / 10 ** int(t.get("tokenDecimal") or 6)
        except (TypeError, ValueError):
            continue
        cell = totals[frm]
        cell["usdc"] += amount
        if cell["first_ts"] is None:
            cell["first_ts"] = int(t.get("timeStamp") or 0)
            cell["first_hash"] = t.get("hash")
            cell["first_block"] = int(t.get("blockNumber") or 0)
    ranked = [{"funder": f, **cell} for f, cell in totals.items() if cell["usdc"] >= min_usdc]
    ranked.sort(key=lambda r: -r["usdc"])
    return ranked[:max_funders]


def looks_like_mixer(contract_name: str | None) -> bool:
    if not contract_name:
        return False
    lowered = contract_name.lower()
    return any(hint in lowered for hint in MIXER_NAME_HINTS)


def match_relayer_inbound(relayer_transfers: list[dict], value_raw: int,
                          block: int, *, block_tolerance: int = 5,
                          value_tolerance: float = 0.01) -> dict | None:
    """Inbound transfer to the relayer near `block` whose amount matches the sweep."""
    best = None
    for t in relayer_transfers:
        if str(t.get("to", "")).lower() != RELAYER:
            continue
        t_block = int(t.get("blockNumber") or 0)
        if abs