"""Passive-exit simulation for bid-side wide harvester fills.

Policy A: rest sell at ref (full reversion). Policy B: rest at ref*(1-delta/2).
Exit fill rule mirrors entry conservatism: a resting sell at P fills only when
a trade prints strictly ABOVE P within the 60-minute window. Unfilled -> cross
the bid at t+60 from L4 quotes (taker fee), quote within 5min else fill NA.
Fees: 1.5bp maker entry; exit 1.5bp if passive, 4.5bp if crossed.
"""

from __future__ import annotations

import gzip
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from charybdis.loaders import parse_flat_file_key

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
MIN_BARS = ROOT / "data/reports/ff_minute_bars.parquet"

fills = pl.read_parquet(ROOT / "data/reports/ff_harvest_fills_all.parquet").filter(
    (pl.col("delta_bps") >= 100) & (pl.col("side") == "bid"))
MARKETS = set(fills["market"].unique().to_list())
print(f"{fills.height} bid fills across {len(MARKETS)} markets", flush=True)

BAR_DIR = ROOT / "data/reports/ff_bars"
BAR_DIR.mkdir(exist_ok=True)
if MIN_BARS.exists():
    bars = pl.read_parquet(MIN_BARS)
    print(f"loaded saved minute bars: {bars.height}", flush=True)
    all_files = {}
else:
    all_files = defaultdict(list)
    for path in ROOT.glob("data/T-TRADES/D-*/E-HYPERLIQUID*/**/*.csv.gz"):
        key = parse_flat_file_key(path)
        market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
        if market in MARKETS:
            all_files[market].append((market, key.partition, path))
frames = []
for mkt in sorted(all_files) if all_files else []:
    shard = BAR_DIR / (mkt.replace(":", "_") + ".parquet")
    if shard.exists():
        frames.append(pl.read_parquet(shard))
        continue
    minutes = defaultdict(dict)
    seen = defaultdict(set)
    files = sorted(all_files[mkt])
    print(f"parsing {mkt}: {len(files)} files", flush=True)
    for i, (market, partition, path) in enumerate(files):
        if partition in seen[market]:
            continue
        try:
            df = pl.read_csv(path, separator=";", columns=["time_exchange", "price"],
                             schema_overrides={"time_exchange": pl.String, "price": pl.Float64})
        except Exception:
            continue
        seen[market].add(partition)
        if df.height == 0:
            continue
        df = df.with_columns(pl.col("time_exchange").str.slice(0, 16).str.to_datetime("%Y-%m-%dT%H:%M").alias("minute"))
        for mnt, lo, hi, med, n in df.group_by("minute").agg(
                pl.col("price").min().alias("lo"), pl.col("price").max().alias("hi"),
                pl.col("price").median().alias("med"), pl.len().alias("n")).iter_rows():
            row = minutes[market].get(mnt)
            if row is None:
                minutes[market][mnt] = [lo, hi, med, n]
            else:
                row[0] = min(row[0], lo); row[1] = max(row[1], hi)
                row[2] = (row[2] * row[3] + med * n) / (row[3] + n); row[3] += n
        if (i + 1) % 2000 == 0:
            print(f"  {i+1}/{len(files)}", flush=True)
    shard_df = pl.DataFrame([
        {"market": m, "minute": mnt, "lo": v[0], "hi": v[1], "med": v[2], "n": v[3]}
        for m, sink in minutes.items() for mnt, v in sink.items()])
    shard_df.write_parquet(shard)
    frames.append(shard_df)
    print(f"  saved {shard.name}: {shard_df.height} bars", flush=True)
if frames:
    bars = pl.concat(frames)
    bars.write_parquet(MIN_BARS)
print(f"minute bars: {bars.height}", flush=True)

hi_map = {}
for (m,), g in bars.partition_by("market", as_dict=True).items():
    g = g.sort("minute")
    hi_map[m] = (g["minute"].to_list(), g["hi"].to_list())

# quote index for fallback exits
qindex = {}
for path in ROOT.glob("data/T-QUOTES/D-*/E-HYPERLIQUIDL4/*.csv.gz"):
    key = parse_flat_file_key(path)
    market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
    qindex[(market, key.partition)] = path

qcache = {}
def bid_at(market, target):
    part = target.strftime("%Y%m%d%H")
    keyt = (market, part)
    if keyt not in qcache:
        path = qindex.get(keyt)
        if path is None:
            qcache[keyt] = None
        else:
            try:
                q = pl.read_csv(path, separator=";", columns=["time_exchange", "bid_px", "ask_px"],
                                schema_overrides={"time_exchange": pl.String, "bid_px": pl.Float64, "ask_px": pl.Float64})
                q = q.with_columns(pl.col("time_exchange").str.slice(0, 26)
                                   .str.to_datetime("%Y-%m-%dT%H:%M:%S%.f", strict=False).alias("ts")).drop_nulls("ts").sort("ts")
                qcache[keyt] = (q["ts"].to_list(), q["bid_px"].to_list(), q["ask_px"].to_list())
            except Exception:
                qcache[keyt] = None
    entry = qcache[keyt]
    if entry is None:
        return None
    ts, bids, asks = entry
    lo, hi = 0, len(ts)
    while lo < hi:
        mid = (lo + hi) // 2
        if ts[mid] <= target: lo = mid + 1
        else: hi = mid
    if lo == 0 or (target - ts[lo - 1]).total_seconds() > 300:
        return None
    b, a = bids[lo - 1], asks[lo - 1]
    if b is None or a is None or b <= 0 or a <= b or (a - b) / ((a + b) / 2) * 1e4 > 200:
        return None
    return b

records = []
for r in fills.iter_rows(named=True):
    m = r["market"]; t0 = r["fill_time"]; fp = r["fill_px"]; ref = r["ref"]
    times, his = hi_map[m]
    lo_i, hi_i = 0, len(times)
    while lo_i < hi_i:
        mid = (lo_i + hi_i) // 2
        if times[mid] <= t0: lo_i = mid + 1
        else: hi_i = mid
    for policy, target_px in (("full", ref), ("half", ref * (1 - r["delta_bps"] / 2e4))):
        filled_at = None
        j = lo_i
        while j < len(times) and (times[j] - t0).total_seconds() <= 3600:
            if his[j] > target_px:
                filled_at = times[j]
                break
            j += 1
        if filled_at is not None:
            net = (target_px - fp) / fp * 1e4 - 1.5 - 1.5
            mode = "passive"
        else:
            b = bid_at(m, t0 + timedelta(minutes=60))
            if b is None:
                records.append({"market": m, "fill_time": t0, "policy": policy, "mode": "na", "net_bps": None})
                continue
            net = (b - fp) / fp * 1e4 - 1.5 - 4.5
            mode = "crossed"
        records.append({"market": m, "fill_time": t0, "policy": policy, "mode": mode, "net_bps": net})

out = pl.DataFrame(records)
out.write_parquet(ROOT / "data/reports/ff_passive_exit.parquet")

def dstat(f):
    daily = f.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(pl.col("net_bps").mean())
    v = [x for x in daily["net_bps"].to_list() if x is not None]
    n = len(v); m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, m / sd * math.sqrt(n), n

for policy in ("full", "half"):
    g = out.filter((pl.col("policy") == policy) & (pl.col("mode") != "na")).drop_nulls("net_bps")
    total = out.filter(pl.col("policy") == policy).height
    pr = g.filter(pl.col("mode") == "passive").height / g.height * 100
    m, t, nd = dstat(g)
    p5 = g["net_bps"].quantile(0.05)
    print(f"policy={policy:4s} usable {g.height}/{total}  passive-fill {pr:.0f}%  net {m:+7.1f}bp (t={t:+.2f}, days={nd})  p5 {p5:+.1f}")
    for mode in ("passive", "crossed"):
        sub = g.filter(pl.col("mode") == mode)
        if sub.height:
            print(f"    {mode:8s} {sub.height:>5} fills  mean {sub['net_bps'].mean():+7.1f}bp")
