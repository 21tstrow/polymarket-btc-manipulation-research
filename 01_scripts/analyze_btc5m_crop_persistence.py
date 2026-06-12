#!/usr/bin/env python3
"""Crop persistence + entry-timing analysis (5m).

Answers two questions the top-edge files cannot:

1. Do the per-period edge crops MAINTAIN edge, or is each period's crop a
   fresh set of one-window wallets? For every crop wallet, recomputes its
   realized contested edge (win rate - avg entry price) directly from the
   tape in each period it traded, regardless of whether it made that
   period's top-100. -> crop_edge_by_period.csv

2. WHEN in the 5-minute window do they place the bet that wins? Edge bucketed
   by the dominant bet's notional-weighted entry offset vs close. Late-window
   (T-5s) wins are reaction-consistent; mid-window (T-60..-10s) wins are
   commitments made before settlement. -> win_rate_by_entry_timing.csv

Crop = z>=5, >=10 markets, positive contested edge in each period's
top_edge_wallets.csv. Trade cache covers the final ~300s only, so entries
before T-300 are invisible (truncates the earliest bucket).
"""
import json, csv
from pathlib import Path
from collections import defaultdict
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
SPANS = ROOT / "02_exports/btc5m_crop_persistence/crop_wallet_spans.csv"
data = {}
if SPANS.exists():
    for r in csv.DictReader(open(SPANS)):
        data[r['wallet']] = {'cells': r['crops'].split(';') if r['crops'] else [],
                             'first': int(r['first_ts']), 'last': int(r['last_ts']), 'n': int(r['n_trades'])}
def crop(path):
    return {r['wallet'] for r in csv.DictReader(open(path))
            if float(r['trade_edge_z'] or 0)>=5 and int(r['n_markets'])>=10 and float(r['edge_contested'] or 0)>0}
crops = {
 'jan-feb': crop('02_exports/btc5m_wallet_edge_jan1_feb28/top_edge_wallets.csv'),
 'mar-apr': crop('02_exports/btc5m_wallet_edge_mar1_apr30/top_edge_wallets.csv'),
 'may-jun': crop('02_exports/btc5m_wallet_edge/top_edge_wallets.csv'),
}
crop_all = set().union(*crops.values())

# merged contested map cid -> (winner, end_epoch, margin)
contested = {}
for u in ('jan1_feb28','mar1_apr30','may1_present'):
    for r in csv.DictReader(open(f'02_exports/btc5m_hybrid_quick_unwind_{u}/hybrid_market_universe.csv')):
        try:
            m=float(r['official_margin_bps_abs']); end=int(float(r['end_epoch']))
        except (ValueError,KeyError,TypeError): continue
        if r.get('winner') in ('Up','Down') and m<=10:
            contested[r['condition_id']]=(r['winner'],end,m)

def period_of(end):
    if end < 1772323200: return 'jan-feb'   # < 2026-03-01
    if end < 1777593600: return 'mar-apr'   # < 2026-05-01
    return 'may-jun'

# per (wallet, market): aggregate buys by outcome
wm = defaultdict(lambda: defaultdict(lambda: [0.0,0.0,0.0]))  # (w,cid)->outcome->[shares,cost,wnotional_offset]
wm_off = defaultdict(lambda: defaultdict(list))  # (w,cid)->outcome->[(offset,notional)]
files = sorted(Path('03_data_cache/polymarket_btc5m_close_contests_cache/trades').glob('*.json'))
for i,f in enumerate(files,1):
    try: d=json.loads(f.read_text())
    except Exception: continue
    if not isinstance(d,list): continue
    for t in d:
        w=t.get('proxyWallet')
        if w not in crop_all: continue
        cid=t.get('conditionId')
        if cid not in contested or str(t.get('side') or '').upper()!='BUY': continue
        o=t.get('outcome')
        if o not in ('Up','Down'): continue
        sz=float(t.get('size') or 0); pr=float(t.get('price') or 0); ts=int(t.get('timestamp') or 0)
        if sz<=0 or ts<=0: continue
        end=contested[cid][1]
        wm[(w,cid)][o][0]+=sz; wm[(w,cid)][o][1]+=sz*pr
        wm_off[(w,cid)][o].append((ts-end, sz*pr))
    if i%5000==0: print(f'scan {i}/{len(files)}',flush=True)

# per period: edge by entry-timing bucket (dominant-side bets), pooled over crop
buckets = [(-300,-120),(-120,-60),(-60,-30),(-30,-10),(-10,0)]
def blab(o):
    for a,b in buckets:
        if a<=o<b: return f'{a}..{b}'
    return 'other'
agg = defaultdict(lambda: [0,0,0.0])  # (period,bucket)->[n, wins, entryprice_sum]
edge_by_wallet_period = defaultdict(lambda: [0.0,0.0,0.0])  # (w,period)->[shares,cost,winshares]
for (w,cid),byout in wm.items():
    winner,end,margin = contested[cid]
    per = period_of(end)
    # dominant bought side
    dom = max(byout, key=lambda o: byout[o][0])
    sh,cost = byout[dom][0], byout[dom][1]
    if sh<=0: continue
    offs = wm_off[(w,cid)][dom]
    woff = sum(o*n for o,n in offs)/sum(n for _,n in offs)
    won = dom==winner
    agg[(per,blab(woff))][0]+=1
    agg[(per,blab(woff))][1]+= 1 if won else 0
    agg[(per,blab(woff))][2]+= cost/sh
    e = edge_by_wallet_period[(w,per)]
    e[0]+=sh; e[1]+=cost; e[2]+= byout[winner][0] if winner in byout else 0.0

print("\n=== WIN RATE BY ENTRY-TIMING BUCKET (crop dominant-side bets, contested mkts) ===")
print(f"{'period':8} {'bucket(s to close)':>18} {'bets':>6} {'winrate':>8} {'avg entry':>10} {'edge':>7}")
for per in ('jan-feb','mar-apr','may-jun'):
    for a,b in buckets:
        k=(per,f'{a}..{b}'); n,wn,ep=agg[k]
        if n==0: continue
        wr=wn/n; aep=ep/n
        print(f"{per:8} {a}..{b:>4}".ljust(27)+f"{n:>6} {wr:>7.0%} {aep:>10.3f} {wr-aep:>+7.3f}")

# edge persistence: each crop wallet's contested edge in each period it traded
out = Path('02_exports/btc5m_crop_persistence'); out.mkdir(parents=True, exist_ok=True)
with open(out/'win_rate_by_entry_timing.csv','w',newline='') as f:
    wr=csv.writer(f); wr.writerow(['period','bucket_s_to_close','bets','win_rate','avg_entry_price','edge'])
    for per in ('jan-feb','mar-apr','may-jun'):
        for a,b in buckets:
            n,wn,ep=agg[(per,f'{a}..{b}')]
            if n: wr.writerow([per,f'{a}..{b}',n,round(wn/n,4),round(ep/n,4),round(wn/n-ep/n,4)])

print("\n=== CROP WALLET CONTESTED EDGE BY PERIOD (which periods does each hold edge?) ===")
rows=[]
edge_rows=[]
for w in sorted(crop_all):
    line=[]
    rec={'wallet':w,'crops':';'.join(p for p in crops if w in crops[p])}
    for per,tag in (('jan-feb','jf'),('mar-apr','ma'),('may-jun','mj')):
        sh,cost,winsh = edge_by_wallet_period[(w,per)]
        if sh<20:
            line.append('   .   '); rec[tag+'_edge']=''; rec[tag+'_shares']=0
        else:
            e = winsh/sh - cost/sh
            line.append(f'{e:+.2f}/{int(sh):>5}'.rjust(11))
            rec[tag+'_edge']=round(e,4); rec[tag+'_shares']=int(sh)
    incrops=[p for p in crops if w in crops[p]]
    rows.append((w,line,incrops)); edge_rows.append(rec)
with open(out/'crop_edge_by_period.csv','w',newline='') as f:
    wr=csv.DictWriter(f,fieldnames=list(edge_rows[0])); wr.writeheader(); wr.writerows(edge_rows)
held = defaultdict(int)
for w,line,incrops in rows:
    nz = sum(1 for c in line if c.strip()!='.')
    held[nz]+=1
print(f"crop wallets trading >=20 contested shares in N periods: {dict(held)}")
print("wallets with positive contested edge (>=20 shares) in >=2 periods:")
for w,line,incrops in rows:
    pos = sum(1 for c in line if c.strip()!='.' and c.strip().startswith('+'))
    if pos>=2:
        print(f"  {w[:10]} | jf {line[0]} | ma {line[1]} | mj {line[2]} | crop:{incrops}")
print(f"\nwrote tables -> {out}")
