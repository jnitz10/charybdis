"""Replicate the funding-impulse size-conditioning split on HL main-dex perps.

Universe: top-100 main-dex coins by current dayNtlVlm (non-delisted) — a
present-day filter, noted as a caveat. Window matches the HIP-3 study
(2026-01-01 .. 2026-07-10). Spec is byte-identical to the HIP-3 run:
impulse_z = (24h mean funding - prior-6d mean) / prior-6d std, bands
(-inf,-2,-0.5,0.5,2,inf), forward 24h close-to-close return strictly after
rebalance, net = price - funding paid over the hold. Daily 00:00 rebalances.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import math
from pathlib import Path

import polars as pl

from charybdis import hl_rest
from charybdis.run_study3_carry import _schedule, _price_known_at
from charybdis.study3_carry import strictly_after_candle_return, funding_window

SCRATCH = Path(__file__).parent
START = datetime(2026, 1, 1)
STOP = datetime(2026, 7, 10)
START_MS = int(START.timestamp() * 1000) + 0  # naive-UTC datetimes; HL client validates
STOP_MS = int(STOP.timestamp() * 1000)
TOP_N = 100

meta, ctxs = hl_rest.meta_and_asset_ctxs()
coins = []
for a, c in zip(meta["universe"], ctxs):
    if a.get("isDelisted"):
        continue
    coins.append((a["name"], float(c.get("dayNtlVlm") or 0)))
coins.sort(key=lambda x: -x[1])
universe = [c for c, _ in coins[:TOP_N]]
print(f"universe: {len(universe)} coins, volume floor ${coins[:TOP_N][-1][1]:,.0f}/day", flush=True)

funding_frames, candle_frames_raw = [], []
for i, coin in enumerate(universe):
    try:
        f = hl_rest.funding_history(coin, START_MS, end_ms=STOP_MS)
        c = hl_rest.candle_snapshot(coin, "1h", START_MS, STOP_MS)
        funding_frames.append(f)
        candle_frames_raw.append(c)
    except Exception as e:
        print(f"  {coin}: SKIP ({e})", flush=True)
    if (i + 1) % 20 == 0:
        print(f"  pulled {i+1}/{len(universe)}", flush=True)

funding = pl.concat(funding_frames)
candles = pl.concat(candle_frames_raw).with_columns(
    pl.from_epoch("close_time_ms", time_unit="ms").alias("time_close")
)
funding.write_parquet(SCRATCH / "maindex_funding.parquet")
candles.write_parquet(SCRATCH / "maindex_candles_1h.parquet")
print(f"funding rows {funding.height}, candle rows {candles.height}", flush=True)

funding_map = {
    m: sorted(zip(g["time_exchange"].to_list(), g["funding_rate"].to_list()))
    for (m,), g in funding.partition_by("market", as_dict=True).items()
}
candle_map = {
    m: sorted(zip(g["time_open"].to_list(), g["time_close"].to_list(), g["close"].to_list()))
    for (m,), g in candles.partition_by("market", as_dict=True).items()
}
candle_pl = {m: pl.DataFrame({
    "time_open": [r[0] for r in rows], "time_close": [r[1] for r in rows], "close": [r[2] for r in rows]})
    for m, rows in candle_map.items()}

start = START + timedelta(days=7)
daily = [t for t, _ in _schedule(start, STOP, 24)]

def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i]); r = [0.0] * len(xs); i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]: j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1): r[order[k]] = avg
        i = j + 1
    return r

def pearson(a, b):
    n = len(a); ma = sum(a) / n; mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((x - mb) ** 2 for x in b)
    if va == 0 or vb == 0: return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)

def spear(a, b):
    return pearson(rank(a), rank(b))

BANDS = [("z<-2", -1e9, -2), ("-2..-0.5", -2, -0.5), ("-0.5..0.5", -0.5, 0.5), ("0.5..2", 0.5, 2), ("z>2", 2, 1e9)]
band_price = {b[0]: [] for b in BANDS}; band_net = {b[0]: [] for b in BANDS}; band_n = {b[0]: [] for b in BANDS}
ic_impulse, ic_level = [], []

for t in daily:
    end = t + timedelta(hours=24)
    if end > STOP: continue
    rows = []
    for m in candle_map:
        if not _price_known_at(candle_map[m], t): continue
        recent = funding_window(funding_map.get(m, []), t - timedelta(hours=24), t)
        base = funding_window(funding_map.get(m, []), t - timedelta(days=7), t - timedelta(hours=24))
        if len(recent) < 20 or len(base) < 120: continue
        mb = sum(base) / len(base)
        sd = math.sqrt(sum((x - mb) ** 2 for x in base) / (len(base) - 1))
        if sd <= 0: continue
        z = (sum(recent) / len(recent) - mb) / sd
        fwd = strictly_after_candle_return(candle_pl[m], t, end)
        if fwd is None: continue
        paid = sum(funding_window(funding_map.get(m, []), t, end))
        level = sum(base) / len(base)
        rows.append((z, fwd, fwd - paid, level, sum(recent) / len(recent) - mb))
    if len(rows) < 20: continue
    for label, lo, hi in BANDS:
        sel = [r for r in rows if lo <= r[0] < hi]
        if sel:
            band_price[label].append(sum(r[1] for r in sel) / len(sel))
            band_net[label].append(sum(r[2] for r in sel) / len(sel))
            band_n[label].append(len(sel))
    ici = spear([r[4] for r in rows], [r[1] for r in rows])
    icl = spear([r[3] for r in rows], [r[1] for r in rows])
    if ici is not None: ic_impulse.append(ici)
    if icl is not None: ic_level.append(icl)

def stats(v):
    n = len(v); m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1)) if n > 1 else float("nan")
    return m, m / sd * math.sqrt(n) if sd > 0 else float("nan"), n

out = {"bands": {}, "ic": {}}
print(f"\n{'z band':10s} {'avg n/day':>9s} {'fwd 24h price':>14s} {'t':>6s} {'fwd 24h net':>12s} {'t':>6s} {'days':>5s}")
for label, _, _ in BANDS:
    if not band_price[label]: continue
    mp, tp, n = stats(band_price[label]); mn, tn, _ = stats(band_net[label])
    avg_n = sum(band_n[label]) / len(band_n[label])
    out["bands"][label] = {"n_per_day": avg_n, "price": mp, "price_t": tp, "net": mn, "net_t": tn, "days": n}
    print(f"{label:10s} {avg_n:>9.1f} {100*mp:>+13.3f}% {tp:>+6.2f} {100*mn:>+11.3f}% {tn:>+6.2f} {n:>5d}")
m, t, n = stats(ic_impulse); out["ic"]["impulse_24h"] = {"mean": m, "t": t, "n": n}
print(f"\nimpulse IC 24h: {m:+.4f}  t={t:+.2f}  n={n}")
m, t, n = stats(ic_level); out["ic"]["level_24h"] = {"mean": m, "t": t, "n": n}
print(f"level IC 24h:   {m:+.4f}  t={t:+.2f}  n={n}")
(SCRATCH / "maindex_replication.json").write_text(json.dumps(out, indent=1))
print("\ndone", flush=True)
