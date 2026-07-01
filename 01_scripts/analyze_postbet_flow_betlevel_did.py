#!/usr/bin/env python3
"""Bet-level, dollar-weighted post-bet directional-flow DiD.

Unlike analyze_postbet_flow_did.py, this runner does not collapse a
wallet-market to one first-entry side. Every target-wallet pre-close BUY fill is
one treated observation, signed to that fill's own outcome and weighted by its
realized P&L magnitude if held to resolution.

Primary weight:
  winning BUY: size * (1 - price)
  losing BUY : size * price

Controls are wallet-absent markets at the same anchor offset and side
perspective. Cluster diagnostics then ask whether a few markets or wallets carry
the weighted result.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import random
import statistics as st
import subprocess
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def safe_float(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def load_universe(path: Path, flat_bps: float) -> dict:
    out = {}
    with open(path, newline="") as handle:
        for r in csv.DictReader(handle):
            cid = r.get("condition_id")
            winner = r.get("winner")
            margin = safe_float(r.get("official_margin_bps_abs") or r.get("margin_bps_abs"))
            end = safe_float(r.get("end_epoch"))
            if cid and winner in ("Up", "Down") and margin is not None and end is not None and margin <= flat_bps:
                out[cid] = {"winner": winner, "end": int(end), "margin": margin}
    return out


def opposite(outcome: str) -> str:
    return "Down" if outcome == "Up" else "Up"


def side_sign(outcome: str) -> int:
    return 1 if outcome == "Up" else -1


def buy_observation(t: dict, wallet: str, cid: str, market: dict, ts: int, *, include_sell: bool = False) -> dict | None:
    outcome = str(t.get("outcome") or "")
    side = str(t.get("side") or "").upper()
    size = safe_float(t.get("size")) or 0.0
    price = safe_float(t.get("price"))
    if outcome not in ("Up", "Down") or side not in ("BUY", "SELL") or size <= 0 or price is None:
        return None
    if not 0 <= price <= 1:
        return None
    if side == "SELL" and not include_sell:
        return None
    if side == "BUY":
        exposure_outcome = outcome
        won = exposure_outcome == market["winner"]
        cost_usd = size * price
        pnl_usd = size * (1.0 - price) if won else -cost_usd
        stake_usd = cost_usd
    else:
        exposure_outcome = opposite(outcome)
        won = exposure_outcome == market["winner"]
        cost_usd = size * price
        pnl_usd = cost_usd if won else -size * (1.0 - price)
        stake_usd = size * (1.0 - price)
    return {
        "wallet": wallet,
        "condition_id": cid,
        "timestamp": ts,
        "side": side,
        "outcome": outcome,
        "exposure_outcome": exposure_outcome,
        "sign": side_sign(exposure_outcome),
        "won": bool(won),
        "size": size,
        "price": price,
        "cost_usd": cost_usd,
        "stake_usd": stake_usd,
        "pnl_usd": pnl_usd,
        "weight_usd": abs(pnl_usd),
    }


def scan_bet_observations(trades_glob: str, targets: set[str], universe: dict, *, include_sell: bool = False) -> tuple[list[dict], dict]:
    observations = []
    preclose_by_wallet: dict[str, set] = {w: set() for w in targets}
    for path in sorted(glob.glob(trades_glob)):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, list):
            continue
        for t in data:
            wallet = str(t.get("proxyWallet") or "").lower()
            if wallet not in targets:
                continue
            cid = t.get("conditionId")
            market = universe.get(cid)
            if market is None:
                continue
            ts = int(safe_float(t.get("timestamp")) or 0)
            if ts <= 0 or ts >= market["end"]:
                continue
            preclose_by_wallet[wallet].add(cid)
            obs = buy_observation(t, wallet, cid, market, ts, include_sell=include_sell)
            if obs is not None:
                obs["winner"] = market["winner"]
                obs["end_epoch"] = market["end"]
                obs["margin_bps_abs"] = market["margin"]
                obs["anchor_offset_s"] = ts - market["end"]
                observations.append(obs)
    return observations, preclose_by_wallet


def load_window(exchange_cache_dir: Path, end: int, pre: int, post: int, cache: dict):
    lo, hi = end - pre, end + post
    out = []
    for start in range(math.floor(lo / 300) * 300, math.floor(hi / 300) * 300 + 300, 300):
        if start not in cache:
            path = exchange_cache_dir / "kraken_trades" / f"XBTUSD_{start}_{start + 300}.json"
            rows = []
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for t in data:
                            ts = safe_float(t.get("timestamp"))
                            price = safe_float(t.get("price"))
                            size = safe_float(t.get("size"))
                            if ts is not None and price and size:
                                rows.append((ts, price, str(t.get("side") or ""), size))
                except Exception:  # noqa: BLE001
                    pass
            cache[start] = rows
        for row in cache[start]:
            if lo <= row[0] <= hi:
                out.append(row)
    return out


def window_flow(trades, end: int, start_offset: int, end_offset: int, sign: int) -> tuple[float, float]:
    total = aligned = 0.0
    for ts, price, side, size in trades:
        offset = ts - end
        if start_offset < offset <= end_offset:
            notional = price * size
            total += notional
            aligned += sign * (1.0 if side == "buy" else -1.0) * notional
    return total, aligned


def market_features(trades, end: int, anchor: int, sign: int) -> dict | None:
    length = -anchor
    total_pre = aligned_pre = total_post = aligned_post = 0.0
    pre_start = anchor - length
    for ts, price, side, size in trades:
        offset = ts - end
        notional = price * size
        signed = sign * (1.0 if side == "buy" else -1.0) * notional
        if pre_start < offset <= anchor:
            total_pre += notional
            aligned_pre += signed
        elif anchor < offset <= 0:
            total_post += notional
            aligned_post += signed
    if total_pre <= 0 or total_post <= 0:
        return None
    dshare_pre = aligned_pre / total_pre
    dshare_post = aligned_post / total_post
    return {
        "total_pre": total_pre,
        "total_post": total_post,
        "aligned_post": aligned_post,
        "dshare_pre": dshare_pre,
        "dshare_post": dshare_post,
        "did": dshare_post - dshare_pre,
        "log_total_pre": math.log(max(total_pre, 1.0)),
    }


def market_flow_series(exchange_cache_dir: Path, end: int, pre: int, post: int, spot_cache: dict) -> tuple[list[float], list[float], list[float]]:
    trades = load_window(exchange_cache_dir, end, pre, post, spot_cache)
    trades.sort(key=lambda row: row[0])
    offsets = []
    total_prefix = [0.0]
    directional_prefix = [0.0]
    total = directional = 0.0
    for ts, price, side, size in trades:
        notional = price * size
        total += notional
        directional += (1.0 if side == "buy" else -1.0) * notional
        offsets.append(ts - end)
        total_prefix.append(total)
        directional_prefix.append(directional)
    return offsets, total_prefix, directional_prefix


def _prefix_sum(offsets: list[float], prefix: list[float], start_offset: int, end_offset: int) -> float:
    lo = bisect_right(offsets, start_offset)
    hi = bisect_right(offsets, end_offset)
    return prefix[hi] - prefix[lo]


def market_features_from_series(series: tuple[list[float], list[float], list[float]], anchor: int, sign: int) -> dict | None:
    offsets, total_prefix, directional_prefix = series
    length = -anchor
    pre_start = anchor - length
    total_pre = _prefix_sum(offsets, total_prefix, pre_start, anchor)
    base_pre = _prefix_sum(offsets, directional_prefix, pre_start, anchor)
    total_post = _prefix_sum(offsets, total_prefix, anchor, 0)
    base_post = _prefix_sum(offsets, directional_prefix, anchor, 0)
    if total_pre <= 0 or total_post <= 0:
        return None
    aligned_pre = sign * base_pre
    aligned_post = sign * base_post
    dshare_pre = aligned_pre / total_pre
    dshare_post = aligned_post / total_post
    return {
        "total_pre": total_pre,
        "total_post": total_post,
        "aligned_post": aligned_post,
        "dshare_pre": dshare_pre,
        "dshare_post": dshare_post,
        "did": dshare_post - dshare_pre,
        "log_total_pre": math.log(max(total_pre, 1.0)),
    }


def _decile_thresholds(values: list[float]) -> list[float]:
    if not values:
        return []
    vals = sorted(values)
    return [vals[int(q * (len(vals) - 1))] for q in (.1, .2, .3, .4, .5, .6, .7, .8, .9)]


def _decile(value: float, thresholds: list[float]) -> int:
    return sum(1 for t in thresholds if value > t)


def match_one(treated: dict, controls: list[dict], cov: list[str], cell_keys: list[str], k: int, caliper: float) -> tuple[list[dict], int]:
    if not controls:
        return [], 1
    prepared = prepare_matcher(controls, cov, cell_keys)
    return match_one_prepared(treated, prepared, cov, cell_keys, k, caliper)


def prepare_matcher(controls: list[dict], cov: list[str], cell_keys: list[str]) -> dict:
    means = {key: st.mean(c[key] for c in controls) for key in cov}
    sds = {key: st.pstdev([c[key] for c in controls]) or 1.0 for key in cov}
    pools = defaultdict(list)
    for c in controls:
        pools[tuple(c[key] for key in cell_keys)].append(c)
    return {"means": means, "sds": sds, "pools": pools}


def match_one_prepared(
    treated: dict,
    prepared: dict,
    cov: list[str],
    cell_keys: list[str],
    k: int,
    caliper: float,
) -> tuple[list[dict], int]:
    def z(row, key):
        return (row[key] - prepared["means"][key]) / prepared["sds"][key]

    target_cell = tuple(treated[key] for key in cell_keys)
    pool = prepared["pools"].get(target_cell, [])
    if not pool:
        return [], 1
    scored = sorted(
        ((sum((z(treated, key) - z(c, key)) ** 2 for key in cov) ** 0.5, c) for c in pool),
        key=lambda x: x[0],
    )
    chosen = [c for dist, c in scored[:k] if dist <= caliper * len(cov) ** 0.5]
    return chosen, 0 if chosen else 1


def weighted_att(rows: list[dict], ykey: str) -> dict:
    vals = [(float(r["weight_usd"]), float(r[f"{ykey}_diff"])) for r in rows
            if r.get("status") == "matched" and r.get(f"{ykey}_diff") not in ("", None) and float(r.get("weight_usd") or 0) > 0]
    total_weight = sum(w for w, _ in vals)
    if not vals or total_weight <= 0:
        return {"att": None, "n": 0, "total_weight_usd": 0.0}
    att = sum(w * d for w, d in vals) / total_weight
    return {"att": round(att, 6), "n": len(vals), "total_weight_usd": round(total_weight, 2)}


def _weighted_att_raw(rows: list[dict], ykey: str, weight_scale_by_id: dict | None = None, id_key: str | None = None) -> float | None:
    num = den = 0.0
    for r in rows:
        if r.get("status") != "matched" or r.get(f"{ykey}_diff") in ("", None):
            continue
        weight = float(r.get("weight_usd") or 0.0)
        if weight <= 0:
            continue
        if weight_scale_by_id is not None and id_key is not None:
            weight *= weight_scale_by_id.get(r[id_key], 1.0)
        num += weight * float(r[f"{ykey}_diff"])
        den += weight
    return num / den if den > 0 else None


def bootstrap_ci(rows: list[dict], ykey: str, rng: random.Random, nboot: int, cluster_key: str | None = None) -> dict:
    matched = [r for r in rows if r.get("status") == "matched" and r.get(f"{ykey}_diff") not in ("", None)]
    point = _weighted_att_raw(matched, ykey)
    if point is None:
        return {"att": None, "ci": [None, None], "n": 0}
    boots = []
    if cluster_key is None:
        n = len(matched)
        for _ in range(nboot):
            sample = [matched[rng.randrange(n)] for _ in range(n)]
            b = _weighted_att_raw(sample, ykey)
            if b is not None:
                boots.append(b)
    else:
        clusters = sorted({r[cluster_key] for r in matched})
        if len(clusters) < 2:
            return {"att": round(point, 6), "ci": [None, None], "n": len(matched), "n_clusters": len(clusters)}
        by_cluster = defaultdict(list)
        for r in matched:
            by_cluster[r[cluster_key]].append(r)
        for _ in range(nboot):
            sample = []
            for _ in clusters:
                sample.extend(by_cluster[clusters[rng.randrange(len(clusters))]])
            b = _weighted_att_raw(sample, ykey)
            if b is not None:
                boots.append(b)
    if len(boots) < 20:
        return {"att": round(point, 6), "ci": [None, None], "n": len(matched)}
    boots.sort()
    lo = boots[int(.025 * len(boots))]
    hi = boots[int(.975 * len(boots))]
    out = {"att": round(point, 6), "ci": [round(lo, 6), round(hi, 6)], "n": len(matched)}
    if cluster_key is not None:
        out["n_clusters"] = len({r[cluster_key] for r in matched})
    return out


def cluster_diagnostics(rows: list[dict], ykey: str, cluster_key: str, cap_share: float = 0.05) -> dict:
    matched = [r for r in rows if r.get("status") == "matched" and r.get(f"{ykey}_diff") not in ("", None)]
    point = _weighted_att_raw(matched, ykey)
    if point is None:
        return {"n_clusters": 0}
    by_cluster = defaultdict(list)
    total_weight = sum(float(r["weight_usd"]) for r in matched)
    total_abs_contrib = sum(abs(float(r["weight_usd"]) * float(r[f"{ykey}_diff"])) for r in matched)
    for r in matched:
        by_cluster[r[cluster_key]].append(r)
    contrib_rows = []
    for cluster, rs in by_cluster.items():
        weight = sum(float(r["weight_usd"]) for r in rs)
        abs_contrib = sum(abs(float(r["weight_usd"]) * float(r[f"{ykey}_diff"])) for r in rs)
        contrib_rows.append((cluster, weight, abs_contrib))
    contrib_rows.sort(key=lambda x: x[2], reverse=True)
    shares = [(c / total_abs_contrib) for _, _, c in contrib_rows] if total_abs_contrib > 0 else []
    leave_one = []
    for cluster in by_cluster:
        rest = [r for r in matched if r[cluster_key] != cluster]
        att = _weighted_att_raw(rest, ykey)
        if att is not None:
            leave_one.append(att)
    cluster_weights = {cluster: sum(float(r["weight_usd"]) for r in rs) for cluster, rs in by_cluster.items()}
    scales = {}
    for cluster, weight in cluster_weights.items():
        max_weight = cap_share * total_weight
        scales[cluster] = min(1.0, max_weight / weight) if weight > 0 and total_weight > 0 else 1.0
    capped = _weighted_att_raw(matched, ykey, scales, cluster_key)
    return {
        "n_clusters": len(by_cluster),
        "top_cluster": contrib_rows[0][0] if contrib_rows else None,
        "top_weight_share": round((max((w for _, w, _ in contrib_rows), default=0.0) / total_weight), 6) if total_weight else None,
        "top_abs_contribution_share": round(shares[0], 6) if shares else None,
        "top5_abs_contribution_share": round(sum(shares[:5]), 6) if shares else None,
        "abs_contribution_hhi": round(sum(s * s for s in shares), 6) if shares else None,
        "leave_one_out_att_min": round(min(leave_one), 6) if leave_one else None,
        "leave_one_out_att_max": round(max(leave_one), 6) if leave_one else None,
        "leave_one_out_max_abs_delta": round(max(abs(x - point) for x in leave_one), 6) if leave_one else None,
        "capped_5pct_weight_att": round(capped, 6) if capped is not None else None,
    }


def score_observations(observations: list[dict], preclose_by_wallet: dict, universe: dict, exchange_cache_dir: Path, args) -> list[dict]:
    spot_cache = {}
    series_cache = {}
    cov = ["log_total_pre", "dshare_pre"]
    cell_keys = ["vol_decile", "margin_bin"]

    def feature_for(cid: str, anchor: int, sign: int, feature_cache: dict) -> dict | None:
        if cid not in feature_cache:
            market = universe[cid]
            if cid not in series_cache:
                series_cache[cid] = market_flow_series(exchange_cache_dir, market["end"], args.preload, 40, spot_cache)
            fx = market_features_from_series(series_cache[cid], anchor, sign)
            if fx:
                fx["condition_id"] = cid
                fx["margin_bin"] = min(int(market["margin"] // 5), 4)
            feature_cache[cid] = fx
        return feature_cache[cid]

    rows: list[dict | None] = [None] * len(observations)
    groups = defaultdict(list)
    for idx, obs in enumerate(observations):
        row = dict(obs)
        anchor = int(obs["anchor_offset_s"])
        row["status"] = "scanned"
        if obs["weight_usd"] < args.min_weight_usd:
            row["status"] = "below_min_weight"
            rows[idx] = row
            continue
        if not (-args.preload + 60 < anchor < -args.min_offset):
            row["status"] = "offset_out_of_range"
            rows[idx] = row
            continue
        groups[(obs["wallet"], anchor, obs["sign"])].append((idx, row))

    total_groups = len(groups)
    for group_idx, ((wallet, anchor, sign), group_rows) in enumerate(groups.items(), start=1):
        if group_idx == 1 or group_idx % 100 == 0 or group_idx == total_groups:
            print(f"scoring group {group_idx}/{total_groups}: rows={len(group_rows)} wallet={wallet[:10]} anchor={anchor}s sign={sign}", flush=True)
        feature_cache = {}
        excluded = preclose_by_wallet.get(wallet, set())
        controls = []
        for cid in universe:
            if cid in excluded:
                continue
            fx = feature_for(cid, anchor, sign, feature_cache)
            if fx:
                controls.append({**fx})
        if not controls:
            for idx, row in group_rows:
                row["status"] = "no_controls"
                rows[idx] = row
            continue
        thresholds = _decile_thresholds([c["log_total_pre"] for c in controls])
        for c in controls:
            c["vol_decile"] = _decile(c["log_total_pre"], thresholds)
        matcher = prepare_matcher(controls, cov, cell_keys)
        for idx, row in group_rows:
            treated = feature_for(row["condition_id"], anchor, sign, feature_cache)
            if treated is None:
                row["status"] = "no_treated_features"
                rows[idx] = row
                continue
            treated = {**treated, "vol_decile": _decile(treated["log_total_pre"], thresholds)}
            chosen, off_support = match_one_prepared(treated, matcher, cov, cell_keys, args.k, args.caliper)
            if off_support or not chosen:
                row["status"] = "off_support"
                rows[idx] = row
                continue
            row["status"] = "matched"
            row["n_controls"] = len(chosen)
            for key in ("did", "dshare_post", "aligned_post", "total_pre"):
                control_mean = st.mean(c[key] for c in chosen)
                row[f"{key}_treated"] = treated[key]
                row[f"{key}_control_mean"] = control_mean
                row[f"{key}_diff"] = treated[key] - control_mean
                row[f"{key}_weighted_contribution"] = row["weight_usd"] * (treated[key] - control_mean)
            rows[idx] = row

    return [r for r in rows if r is not None]


def estimate_table(rows: list[dict], rng: random.Random, nboot: int) -> dict:
    out = {}
    splits = {
        "all": lambda r: True,
        "won": lambda r: bool(r.get("won")),
        "lost": lambda r: not bool(r.get("won")),
    }
    for split, pred in splits.items():
        rs = [r for r in rows if pred(r)]
        out[split] = {
            "did": bootstrap_ci(rs, "did", rng, nboot),
            "dshare_post": bootstrap_ci(rs, "dshare_post", rng, nboot),
            "aligned_post": bootstrap_ci(rs, "aligned_post", rng, nboot),
            "PLACEBO_total_pre": bootstrap_ci(rs, "total_pre", rng, nboot),
        }
    return out


def per_wallet_table(rows: list[dict]) -> list[dict]:
    out = []
    for wallet in sorted({r["wallet"] for r in rows}):
        rs = [r for r in rows if r["wallet"] == wallet and r.get("status") == "matched"]
        est = weighted_att(rs, "did")
        out.append({
            "wallet": wallet,
            "n_matched_bets": est["n"],
            "total_weight_usd": est["total_weight_usd"],
            "won_weight_usd": round(sum(float(r["weight_usd"]) for r in rs if r.get("won")), 2),
            "lost_weight_usd": round(sum(float(r["weight_usd"]) for r in rs if not r.get("won")), 2),
            "weighted_did_att": est["att"],
        })
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_meta() -> dict:
    def run_git(cmd: list[str]) -> str | None:
        try:
            return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:  # noqa: BLE001
            return None

    status = run_git(["git", "status", "--short"])
    return {
        "commit": run_git(["git", "rev-parse", "HEAD"]),
        "dirty": bool(status),
        "status_short": status,
    }


def run(args) -> int:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    universe = load_universe(Path(args.universe_csv), args.flat_bps)
    targets = {w.strip().lower() for w in args.wallets.split(",") if w.strip()}
    rng = random.Random(args.seed)
    observations, preclose_by_wallet = scan_bet_observations(args.trades_glob, targets, universe, include_sell=False)
    rows = score_observations(observations, preclose_by_wallet, universe, Path(args.exchange_cache_dir), args)
    matched = [r for r in rows if r.get("status") == "matched"]
    estimates = estimate_table(rows, rng, args.bootstrap)
    summary = {
        "product": args.product,
        "primary": "bet-level weighted DiD, BUY fills only, realized-P&L weights",
        "n_scanned_bets": len(rows),
        "n_matched_bets": len(matched),
        "weight_basis": args.weight_basis,
        "trade_scope": "BUY",
        "estimates": estimates,
        "cluster_validation": {
            "market": {
                "did_cluster_ci": bootstrap_ci(rows, "did", rng, args.bootstrap, cluster_key="condition_id"),
                "diagnostics": cluster_diagnostics(rows, "did", "condition_id"),
            },
            "wallet": {
                "did_cluster_ci": bootstrap_ci(rows, "did", rng, args.bootstrap, cluster_key="wallet"),
                "diagnostics": cluster_diagnostics(rows, "did", "wallet"),
            },
        },
    }
    if args.sell_sensitivity:
        sell_obs, sell_preclose = scan_bet_observations(args.trades_glob, targets, universe, include_sell=True)
        sell_rows = score_observations(sell_obs, sell_preclose, universe, Path(args.exchange_cache_dir), args)
        summary["sell_sensitivity"] = {
            "trade_scope": "BUY plus SELL-as-opposite-exposure",
            "n_scanned_bets": len(sell_rows),
            "n_matched_bets": len([r for r in sell_rows if r.get("status") == "matched"]),
            "estimates": estimate_table(sell_rows, rng, args.bootstrap),
            "market_diagnostics": cluster_diagnostics(sell_rows, "did", "condition_id"),
        }
        write_csv(out_dir / "betlevel_observations_buy_plus_sell_sensitivity.csv", sell_rows)

    write_csv(out_dir / "betlevel_observations.csv", rows)
    write_csv(out_dir / "betlevel_per_wallet.csv", per_wallet_table(rows))
    (out_dir / "betlevel_did_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    manifest = {
        "generated_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "script": "01_scripts/analyze_postbet_flow_betlevel_did.py",
        "argv": sys.argv,
        "args": vars(args),
        "git": git_meta(),
        "inputs": {
            "universe_csv": str(args.universe_csv),
            "universe_csv_sha256": sha256_file(args.universe_csv),
            "trades_glob": args.trades_glob,
            "exchange_cache_dir": str(args.exchange_cache_dir),
        },
        "design": {
            "primary_observation": "one target-wallet pre-close BUY fill",
            "weight_basis": "realized P&L magnitude if held to resolution",
            "winner_buy_weight": "size * (1 - price)",
            "loser_buy_weight": "size * price",
            "sell_sensitivity": bool(args.sell_sensitivity),
            "controls": "wallet-absent markets at same anchor offset and side perspective",
            "cluster_validation": "market and wallet cluster bootstrap plus contribution diagnostics",
        },
    }
    (out_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"product={args.product} scanned={len(rows)} matched={len(matched)}")
    print(f"weighted DiD={summary['estimates']['all']['did']}")
    print(f"wrote {out_dir}")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--product", required=True)
    parser.add_argument("--universe-csv", required=True)
    parser.add_argument("--trades-glob", required=True)
    parser.add_argument("--wallets", required=True)
    parser.add_argument("--exchange-cache-dir", default=str(ROOT / "03_data_cache/btc5m_underlying_volume_cache"))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--trade-scope", choices=["buy"], default="buy",
                        help="primary estimand uses BUY fills only; SELLs appear only in the optional sensitivity")
    parser.add_argument("--weight-basis", choices=["realized-pnl"], default="realized-pnl")
    parser.add_argument("--min-weight-usd", type=float, default=0.0)
    parser.add_argument("--flat-bps", type=float, default=20.0)
    parser.add_argument("--preload", type=int, default=1600)
    parser.add_argument("--min-offset", type=int, default=10)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--caliper", type=float, default=0.5)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260623)
    parser.set_defaults(sell_sensitivity=True)
    parser.add_argument("--no-sell-sensitivity", dest="sell_sensitivity", action="store_false")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
