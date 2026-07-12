"""Generalized perp−oracle basis event study — any-day entries, 30 markets.

Basis = ln(traded_median_minute / oracle_px) in bps. Event = basis crossing
beyond ±T (fresh: |basis| < T on previous traded minute), 60m cooldown per
market+threshold+side-of-gap. Forward measurement at +30m/+2h/+8h (nearest
traded minute within 30m tolerance): convergence PnL in bps = signed perp
return that closes the gap (buy discount / short premium).

Conditioning: oracle move over prior 30m toward the gap direction, classed
flat vs confirming (≥0.25·|basis at event|), as in ff_oracle_condition_full.
Scale guard drops markets whose trade px is >30% from the bare-symbol oracle
series (multi-dex scale wart), counted per market.

Also reported: events and per-event returns by weekday (does gap size subsume
the Monday effect?), and the 3-weekend Monday-reversion cross-section.
"""

from __future__ import annotations

import bisect
import math
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
THRESHOLDS = [50.0, 100.0, 200.0]
HORIZONS = {"m30": 30, "h2": 120, "h8": 480}
TOL_MIN = 30
COOLDOWN_MIN = 60
CONFIRM_FRAC = 0.25
ORACLE_START = datetime(2026, 6, 17)

# trade minute bars: 13 mkts + 17 singles
bars13 = pl.read_parquet(ROOT / "data/reports/ff_minute_bars.parquet")
frames = [bars13]
for shard in (ROOT / "data/reports/ff_bars_sn").glob("*.parquet"):
    frames.append(pl.read_parquet(shard).with_columns(pl.lit(f"xyz:{shard.stem}").alias("market")))
trades = pl.concat([f.select("market", "minute", "lo", "hi", "med", "n") for f in frames]).filter(
    pl.col("minute") >= ORACLE_START)

oracle = {}
for shard in (ROOT / "data/reports/oracle_bars").glob("*.parquet"):
    df = pl.read_parquet(shard)
    oracle[shard.stem] = (df["minute"].to_list(), df["oracle_px"].to_list())


def oracle_at(sym, t):
    times, px = oracle[sym]
    i = bisect.bisect_right(times, t) - 1
    if i < 0 or (t - times[i]) > timedelta(minutes=10):
        return None
    return px[i]


events = []
scale_dropped = {}
for market, g in trades.partition_by("market", as_dict=True).items():
    market = market[0] if isinstance(market, tuple) else market
    sym = market.split(":", 1)[1]
    if sym not in oracle:
        continue
    g = g.sort("minute")
    times = g["minute"].to_list()
    med = g["med"].to_list()
    # basis series on traded minutes
    basis = []
    drops = 0
    for t, p in zip(times, med):
        o = oracle_at(sym, t)
        if o is None:
            basis.append(None)
            continue
        if abs(p / o - 1) > 0.30:
            basis.append(None)
            drops += 1
            continue
        basis.append(math.log(p / o) * 1e4)
    if drops:
        scale_dropped[market] = drops
    for T in THRESHOLDS:
        cooldown = {1: None, -1: None}
        for i in range(1, len(times)):
            b, bp = basis[i], basis[i - 1]
            if b is None or bp is None:
                continue
            if abs(b) < T or abs(bp) >= T:
                continue
            sign = 1 if b > 0 else -1  # premium / discount
            cu = cooldown[sign]
            if cu is not None and times[i] < cu:
                continue
            cooldown[sign] = times[i] + timedelta(minutes=COOLDOWN_MIN)
            # oracle conditioning over prior 30m
            o_now = oracle_at(sym, times[i])
            o_pre = oracle_at(sym, times[i] - timedelta(minutes=30))
            if o_now is None or o_pre is None:
                continue
            omove = (o_now - o_pre) / o_pre * 1e4
            toward = omove * (-1 if sign < 0 else 1)  # oracle moving in gap direction
            cls = "confirmed" if toward >= CONFIRM_FRAC * abs(b) else (
                "opposed" if toward <= -CONFIRM_FRAC * abs(b) else "flat")
            row = {"market": market, "cohort": "singles" if market.startswith("xyz:") and sym in
                   {"INTC","HIMS","MSTR","CRCL","HOOD","COIN","MU","MRVL","TSLA","NVDA","PLTR",
                    "RKLB","NBIS","AMD","ARM","BE","RIVN"} else "mkts13",
                   "T": T, "gap_sign": sign, "basis_bps": b, "time": times[i], "cls": cls}
            for hname, off in HORIZONS.items():
                pnl = None
                for j in range(i + 1, len(times)):
                    dt_min = (times[j] - times[i]).total_seconds() / 60
                    if dt_min >= off:
                        if dt_min <= off + TOL_MIN and med[j] is not None:
                            # convergence pnl: long discount (+ret) / short premium (−ret)
                            ret = math.log(med[j] / med[i]) * 1e4
                            pnl = -sign * ret
                        break
                row[f"pnl_{hname}"] = pnl
            events.append(row)

ev = pl.DataFrame(events)
ev.write_parquet(ROOT / "data/reports/ff_basis_events.parquet")
print(f"{ev.height} events; scale-dropped minutes: {scale_dropped}", flush=True)


def stats(v):
    v = [x for x in v if x is not None]
    n = len(v)
    if n < 2:
        return float("nan"), float("nan"), n
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, (m / sd * math.sqrt(n) if sd > 0 else float("nan")), n


def cell(g, col="pnl_m30"):
    daily = g.with_columns(pl.col("time").dt.date().alias("d")).group_by("d").agg(pl.col(col).mean())
    return stats(daily[col].to_list()) + (g.height,)


print("\n=== convergence PnL by threshold x class (all mkts, both gap signs) ===")
print(f"{'T':>4} {'cls':10s} {'n':>5} {'days':>4} | {'m30':>7} {'t':>5} | {'h2':>7} {'t':>5} | {'h8':>7} {'t':>5}")
for T in THRESHOLDS:
    for cls in ("flat", "confirmed", "opposed"):
        g = ev.filter((pl.col("T") == T) & (pl.col("cls") == cls))
        if g.height < 5:
            continue
        m30, t30, nd, n = cell(g, "pnl_m30")
        h2, t2, _, _ = cell(g, "pnl_h2")
        h8, t8, _, _ = cell(g, "pnl_h8")
        print(f"{T:4.0f} {cls:10s} {n:5d} {nd:4d} | {m30:+7.1f} {t30:+5.2f} | {h2:+7.1f} {t2:+5.2f} | {h8:+7.1f} {t8:+5.2f}")

print("\n=== discount-only (gap_sign=-1 → long perp), by cohort, T=100 ===")
for cohort in ("mkts13", "singles"):
    for cls in ("flat", "confirmed", "opposed"):
        g = ev.filter((pl.col("T") == 100.0) & (pl.col("gap_sign") == -1) &
                      (pl.col("cohort") == cohort) & (pl.col("cls") == cls))
        if g.height < 5:
            continue
        m30, t30, nd, n = cell(g)
        h2, t2, _, _ = cell(g, "pnl_h2")
        print(f"  {cohort} {cls:10s} {n:5d}/{nd:3d}d  m30 {m30:+7.1f} t={t30:+5.2f}  h2 {h2:+7.1f} t={t2:+5.2f}")

print("\n=== events by weekday (T=100, flat cls): does gap subsume Monday? ===")
g = ev.filter((pl.col("T") == 100.0) & (pl.col("cls") == "flat")).with_columns(
    pl.col("time").dt.weekday().alias("wd"))
for wd in range(1, 8):
    gg = g.filter(pl.col("wd") == wd)
    if gg.height < 3:
        print(f"  wd{wd}: {gg.height} events")
        continue
    m30, t30, nd, n = cell(gg)
    h2, t2, _, _ = cell(gg, "pnl_h2")
    print(f"  wd{wd}: {n:4d} events/{nd:3d}d  m30 {m30:+7.1f} t={t30:+5.2f}  h2 {h2:+7.1f} t={t2:+5.2f}")
