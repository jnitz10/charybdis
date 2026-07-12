"""Forced-flow passive-harvester backtest on SKHX/SMSN tick trades.

Conservative trades-only fill model: a resting bid at P counts as filled only
when a print occurs strictly below P (the level was consumed); symmetric for
asks. Quotes re-peg each minute to the trailing 5-minute median trade price;
no quoting after 30 trade-silent minutes. One fill per side per 60-minute
cooldown. Markouts at +5m/+30m/+4h vs the median trade price of the first
traded minute at/after the offset (NA beyond +30m tolerance).
"""

from __future__ import annotations

import gzip
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl

from charybdis.loaders import parse_flat_file_key

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
OUT = ROOT / "data/reports/ff_harvest_fills_all.parquet"
MARKETS = None  # all markets found
DELTAS = [0.0025, 0.005, 0.01, 0.02]
COOLDOWN_MIN = 60
HORIZONS = {"m5": 5, "m30": 30, "h4": 240}
TOL_MIN = 30

files = []
for path in ROOT.glob("data/T-TRADES/D-*/E-HYPERLIQUID*/**/*.csv.gz"):
    key = parse_flat_file_key(path)
    market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
    files.append((market, key.partition, path))
files.sort(key=lambda x: (x[0], x[1]))
MARKETS = sorted({m for m, _, _ in files})
print(f"{len(files)} trade files, {len(MARKETS)} markets", flush=True)
from collections import defaultdict as _dd
files_by_market = _dd(list)
for market, partition, path in files:
    files_by_market[market].append((market, partition, path))

# per-market per-minute aggregation: minute -> [min_px, max_px, median approximated by mid of sorted sample, n]
minutes = {m: {} for m in MARKETS}
corrupt = 0
seen_partitions: dict[str, set] = defaultdict(set)
_flat = [t for m in MARKETS for t in files_by_market[m]]
for fi, (market, partition, path) in enumerate(_flat):
    if fi % 1000 == 0:
        print(f"  parse {fi}/{len(_flat)} ({market})", flush=True)
    if partition in seen_partitions[market]:
        continue  # duplicate hour across eras (HYPERLIQUID vs HYPERLIQUIDL4): first wins
    try:
        df = pl.read_csv(path, separator=";", columns=["time_exchange", "price"],
                         schema_overrides={"time_exchange": pl.String, "price": pl.Float64})
    except Exception:
        corrupt += 1
        continue
    seen_partitions[market].add(partition)
    if df.height == 0:
        continue
    df = df.with_columns(
        pl.col("time_exchange").str.slice(0, 16).str.to_datetime("%Y-%m-%dT%H:%M").alias("minute"))
    agg = df.group_by("minute").agg(
        pl.col("price").min().alias("lo"), pl.col("price").max().alias("hi"),
        pl.col("price").median().alias("med"), pl.len().alias("n"))
    sink = minutes[market]
    for mnt, lo, hi, med, n in agg.iter_rows():
        row = sink.get(mnt)
        if row is None:
            sink[mnt] = [lo, hi, med, n]
        else:
            row[0] = min(row[0], lo); row[1] = max(row[1], hi)
            row[2] = (row[2] * row[3] + med * n) / (row[3] + n); row[3] += n

print(f"minute bars: " + ", ".join(f"{m}:{len(v)}" for m, v in minutes.items()) + f" corrupt={corrupt}", flush=True)

fee_table = pl.read_parquet(ROOT / "data/reports/study3_fee_table.parquet")
fee_by_dex = dict(fee_table.select("dex", "effective_maker_bps").iter_rows())
print(f"maker fees by dex: {fee_by_dex}", flush=True)

records = []
for market, sink in minutes.items():
    times = sorted(sink)
    med_list = [sink[t][2] for t in times]
    # simulate per delta per side
    for delta in DELTAS:
        for side in ("bid", "ask"):
            cooldown_until = None
            for i, t in enumerate(times):
                if i < 5:
                    continue
                if cooldown_until is not None and t < cooldown_until:
                    continue
                # ref: median of previous 5 traded minutes; require recency
                prev_t = times[i - 1]
                if (t - prev_t).total_seconds() > 1800:
                    continue
                window = sorted(med_list[i - 5:i])
                ref = window[2]
                lo, hi, med, n = sink[t]
                if side == "bid":
                    px = ref * (1 - delta)
                    filled = lo < px
                else:
                    px = ref * (1 + delta)
                    filled = hi > px
                if not filled:
                    continue
                # markouts
                mk = {}
                for hname, off in HORIZONS.items():
                    target = None
                    for j in range(i + 1, len(times)):
                        dt_min = (times[j] - t).total_seconds() / 60
                        if dt_min >= off:
                            if dt_min <= off + TOL_MIN:
                                target = sink[times[j]][2]
                            break
                    if target is None:
                        mk[hname] = None
                    else:
                        raw = (target - px) / px if side == "bid" else (px - target) / px
                        mk[hname] = raw * 1e4  # bps
                records.append({
                    "market": market, "side": side, "delta_bps": delta * 1e4,
                    "fill_time": t, "fill_px": px, "ref": ref,
                    "markout_m5_bps": mk["m5"], "markout_m30_bps": mk["m30"], "markout_h4_bps": mk["h4"],
                })
                from datetime import timedelta as _td
                cooldown_until = t + _td(minutes=COOLDOWN_MIN)

fills = pl.DataFrame(records)
fills.write_parquet(OUT)
print(f"{fills.height} fills -> {OUT.name}", flush=True)

import math
def stats(v):
    v = [x for x in v if x is not None]
    n = len(v)
    if n < 2: return float("nan"), float("nan"), n
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, (m / sd * math.sqrt(n) if sd > 0 else float("nan")), n

span_days = max((max(s) - min(s)).days for s in (sorted(minutes[m]) for m in MARKETS) if s)
print(f"\nspan ~{span_days} days per market")
print(f"{'mkt':10s} {'side':4s} {'δbp':>4s} {'fills':>6s} {'/day':>5s} | {'m5':>7s} {'t':>5s} | {'m30':>7s} {'t':>5s} | {'h4':>7s} {'t':>5s} | {'m30 p5':>7s} {'net30':>6s}")
for (mkt, side, db), g in fills.partition_by(["market", "side", "delta_bps"], as_dict=True).items():
    # day-clustered: mean per day then t over days
    daily = g.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(
        pl.col("markout_m5_bps").mean(), pl.col("markout_m30_bps").mean(), pl.col("markout_h4_bps").mean())
    m5, t5, _ = stats(daily["markout_m5_bps"].to_list())
    m30, t30, nd = stats(daily["markout_m30_bps"].to_list())
    h4, t4, _ = stats(daily["markout_h4_bps"].to_list())
    p5 = g["markout_m30_bps"].drop_nulls().quantile(0.05) if g["markout_m30_bps"].drop_nulls().len() else None
    net30 = (m30 - fee_by_dex.get(mkt.split(":")[0], 1.5)) if m30 == m30 else float("nan")
    print(f"{mkt:10s} {side:4s} {db:4.0f} {g.height:>6d} {g.height/max(span_days,1):>5.1f} | "
          f"{m5:>7.1f} {t5:>5.1f} | {m30:>7.1f} {t30:>5.1f} | {h4:>7.1f} {t4:>5.1f} | "
          f"{p5 if p5 is None else round(p5,1):>7} {net30:>6.1f}")
EOF_MARKER_NOT_USED = None
