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

Fills at/after end_epoch trade the close->oracle-resolution gap (outcome fixed
but not yet public), not the pre-close market. They get their own timing
buckets here, and crop_edge_by_period.csv carries a pre/post-close split
(edge, shares, and profit-if-held on each side of the close) so the pre-close
prediction claim is never silently contaminated by resolution-gap fills.
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
# crops come from the corrected runs: pre-close fills only, on-chain winner
# labels (the original all-fills/fallback-label crops were contaminated)
crops = {
 'jan-feb': crop('02_exports/btc5m_wallet_edge_jan1_feb28_preclose/top_edge_wallets.csv'),
 'mar-apr': crop('02_exports/btc5m_wallet_edge_mar1_apr30_preclose/top_edge_wallets.csv'),
 'may-jun': crop('02_exports/btc5m_wallet_edge_preclose/top_edge_wallets.csv'),
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
# on-chain ConditionResolution payouts override the Gamma-derived labels: the
# universe's exchange-price fallback mislabels a slice of micro-margin markets
OVERRIDES = ROOT / '02_exports/btc5m_resolution_times_contested_all/resolution_times.csv'
n_flipped = 0
if OVERRIDES.exists():
    for r in csv.DictReader(open(OVERRIDES)):
        cid = r.get('condition_id')
        if r.get('resolved')=='1' and cid in contested and r.get('onchain_winner') in ('Up','Down'):
            w,end,m = contested[cid]
            if w != r['onchain_winner']: n_flipped += 1
            contested[cid] = (r['onchain_winner'], end, m)
print(f'contested: {len(contested)} markets; winner labels corrected on-chain: {n_flipped}')

def period_of(end):
    if end < 1772323200: return 'jan-feb'   # < 2026-03-01
    if end < 1777593600: return 'mar-apr'   # < 2026-05-01
    return 'may-jun'

# per (wallet, market): aggregate buys by outcome, split at the close
# (w,cid)->outcome->[pre_shares,pre_cost,post_shares,post_cost]
wm = defaultdict(lambda: defaultdict(lambda: [0.0,0.0,0.0,0.0]))
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
        cell=wm[(w,cid)][o]
        if ts<end: cell[0]+=sz; cell[1]+=sz*pr
        else: cell[2]+=sz; cell[3]+=sz*pr
        wm_off[(w,cid)][o].append((ts-end, sz*pr))
    if i%5000==0: print(f'scan {i}/{len(files)}',flush=True)

# per period: edge by entry-timing bucket (dominant-side bets), pooled over crop
buckets = [(-300,-120),(-120,-60),(-60,-30),(-30,-10),(-10,0),(0,5),(5,15),(15,30),(30,10**9)]
def blab(o):
    for a,b in buckets:
        if a<=o<b: return f'{a}..{b}' if b<10**9 else f'{a}+'
    return 'other'
def tot(cell):  # all-fills shares/cost for dominant-side pick
    return cell[0]+cell[2], cell[1]+cell[3]
agg = defaultdict(lambda: [0,0,0.0])  # (period,bucket)->[n, wins, entryprice_sum]
# (w,period)->[pre_sh,pre_cost,pre_winsh, post_sh,post_cost,post_winsh, pnl_pre, pnl_post]
edge_by_wallet_period = defaultdict(lambda: [0.0]*8)
for (w,cid),byout in wm.items():
    winner,end,margin = contested[cid]
    per = period_of(end)
    # dominant bought side (all fills)
    dom = max(byout, key=lambda o: tot(byout[o])[0])
    sh,cost = tot(byout[dom])
    if sh<=0: continue
    offs = wm_off[(w,cid)][dom]
    woff = sum(o*n for o,n in offs)/sum(n for _,n in offs)
    won = dom==winner
    agg[(per,blab(woff))][0]+=1
    agg[(per,blab(woff))][1]+= 1 if won else 0
    agg[(per,blab(woff))][2]+= cost/sh
    e = edge_by_wallet_period[(w,per)]
    e[0]+=byout[dom][0]; e[1]+=byout[dom][1]
    e[3]+=byout[dom][2]; e[4]+=byout[dom][3]
    if winner in byout:
        e[2]+=byout[winner][0]; e[5]+=byout[winner][2]
    for o,cell in byout.items():  # profit-if-held across ALL bought sides
        e[6]+= (cell[0]-cell[1]) if o==winner else -cell[1]
        e[7]+= (cell[2]-cell[3]) if o==winner else -cell[3]

labels=[blab((a+min(b,a+1))/2) for a,b in buckets]
print("\n=== WIN RATE BY ENTRY-TIMING BUCKET (crop dominant-side bets, contested mkts) ===")
print("(buckets at/after 0 are post-close: the close->oracle-resolution gap)")
print(f"{'period':8} {'bucket(s to close)':>18} {'bets':>6} {'winrate':>8} {'avg entry':>10} {'edge':>7}")
for per in ('jan-feb','mar-apr','may-jun'):
    for lab in labels:
        n,wn,ep=agg[(per,lab)]
        if n==0: continue
        wr=wn/n; aep=ep/n
        print(f"{per:8} {lab:>14}".ljust(27)+f"{n:>6} {wr:>7.0%} {aep:>10.3f} {wr-aep:>+7.3f}")

# edge persistence: each crop wallet's contested edge in each period it traded
out = Path('02_exports/btc5m_crop_persistence'); out.mkdir(parents=True, exist_ok=True)
with open(out/'win_rate_by_entry_timing.csv','w',newline='') as f:
    wr=csv.writer(f); wr.writerow(['period','bucket_s_to_close','bets','win_rate','avg_entry_price','edge'])
    for per in ('jan-feb','mar-apr','may-jun'):
        for lab in labels:
            n,wn,ep=agg[(per,lab)]
            if n: wr.writerow([per,lab,n,round(wn/n,4),round(ep/n,4),round(wn/n-ep/n,4)])

print("\n=== CROP WALLET CONTESTED EDGE BY PERIOD (pre-close fills only; which periods hold edge?) ===")
rows=[]
edge_rows=[]
def edge_of(sh,cost,winsh):
    return winsh/sh - cost/sh
for w in sorted(crop_all):
    line=[]
    rec={'wallet':w,'crops':';'.join(p for p in crops if w in crops[p])}
    for per,tag in (('jan-feb','jf'),('mar-apr','ma'),('may-jun','mj')):
        e = edge_by_wallet_period[(w,per)]
        sh_all,cost_all,winsh_all = e[0]+e[3], e[1]+e[4], e[2]+e[5]
        if sh_all<20:
            line.append('   .   ')
            for suf in ('_edge','_pre_edge','_post_edge'): rec[tag+suf]=''
            for suf in ('_shares','_pre_shares','_post_shares'): rec[tag+suf]=0
            rec[tag+'_pnl_pre']=''; rec[tag+'_pnl_post']=''
            continue
        rec[tag+'_edge']=round(edge_of(sh_all,cost_all,winsh_all),4); rec[tag+'_shares']=int(sh_all)
        rec[tag+'_pre_edge']=round(edge_of(e[0],e[1],e[2]),4) if e[0]>=20 else ''
        rec[tag+'_pre_shares']=int(e[0])
        rec[tag+'_post_edge']=round(edge_of(e[3],e[4],e[5]),4) if e[3]>=20 else ''
        rec[tag+'_post_shares']=int(e[3])
        rec[tag+'_pnl_pre']=round(e[6],2); rec[tag+'_pnl_post']=round(e[7],2)
        pre = f'{edge_of(e[0],e[1],e[2]):+.2f}/{int(e[0]):>5}' if e[0]>=20 else '  none/pre '
        line.append(pre.rjust(11))
    incrops=[p for p in crops if w in crops[p]]
    rows.append((w,line,incrops)); edge_rows.append(rec)
with open(out/'crop_edge_by_period.csv','w',newline='') as f:
    wr=csv.DictWriter(f,fieldnames=list(edge_rows[0])); wr.writeheader(); wr.writerows(edge_rows)

print("\n=== PRE vs POST-CLOSE PROFIT-IF-HELD (crop wallets with >=$500 either side) ===")
tot_pre=tot_post=0.0
split_rows=[]
for w in sorted(crop_all):
    pnl_pre = sum(edge_by_wallet_period[(w,per)][6] for per in ('jan-feb','mar-apr','may-jun'))
    pnl_post = sum(edge_by_wallet_period[(w,per)][7] for per in ('jan-feb','mar-apr','may-jun'))
    tot_pre+=pnl_pre; tot_post+=pnl_post
    split_rows.append({'wallet':w,'pnl_if_held_pre_close':round(pnl_pre,2),
                       'pnl_if_held_post_close':round(pnl_post,2)})
    if abs(pnl_pre)>=500 or abs(pnl_post)>=500:
        print(f"  {w[:10]} pre ${pnl_pre:>10,.0f} | post ${pnl_post:>10,.0f}")
print(f"  {'CROP TOTAL':10} pre ${tot_pre:>10,.0f} | post ${tot_post:>10,.0f}")
with open(out/'crop_preclose_split.csv','w',newline='') as f:
    wr=csv.DictWriter(f,fieldnames=['wallet','pnl_if_held_pre_close','pnl_if_held_post_close'])
    wr.writeheader(); wr.writerows(split_rows)
held = defaultdict(int)
for w,line,incrops in rows:
    nz = sum(1 for c in line if c.strip()!='.')
    held[nz]+=1
print(f"crop wallets trading >=20 contested shares in N periods: {dict(held)}")
print("wallets with positive PRE-CLOSE contested edge (>=20 pre-close shares) in >=2 periods:")
for w,line,incrops in rows:
    pos = sum(1 for c in line if c.strip()!='.' and c.strip().startswith('+'))
    if pos>=2:
        print(f"  {w[:10]} | jf {line[0]} | ma {line[1]} | mj {line[2]} | crop:{incrops}")
print(f"\nwrote tables -> {out}")
