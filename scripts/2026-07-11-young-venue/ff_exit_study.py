"""Exit-cost study: executable exits for wide harvester fills via L4 quotes.

For each δ>=100bp fill, find the touch 30 minutes after fill and compute the
executable round trip: enter passive at fill_px (maker 1.5bp), exit by
crossing the touch at t+30 (taker 4.5bp). Longs exit at bid, shorts at ask.
Quote must be within 5 minutes of target else the fill is excluded (counted).
Also records touch dollar depth at exit.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from charybdis.loaders import parse_flat_file_key

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
OUT = ROOT / "data/reports/ff_exit_study.parquet"

fills = pl.read_parquet(ROOT / "data/reports/ff_harvest_fills_all.parquet").filter(
    pl.col("delta_bps") >= 100)
print(f"{fills.height} wide fills", flush=True)

# index quote files by (market, hour-string)
qindex: dict[tuple[str, str], Path] = {}
for path in ROOT.glob("data/T-QUOTES/D-*/E-HYPERLIQUIDL4/*.csv.gz"):
    key = parse_flat_file_key(path)
    market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
    qindex[(market, key.partition)] = path
print(f"{len(qindex)} quote files indexed", flush=True)

# group fill exit-targets by quote file
targets = defaultdict(list)  # (market, partition) -> [(row_idx, target_dt)]
rows = fills.with_row_index("idx").iter_rows(named=True)
for r in rows:
    target = r["fill_time"] + timedelta(minutes=30)
    part = target.strftime("%Y%m%d%H")
    targets[(r["market"], part)].append((r["idx"], target, r["side"], r["fill_px"]))

results = {}
missing_file = stale = 0
done = 0
for (market, part), items in targets.items():
    path = qindex.get((market, part))
    if path is None:
        missing_file += len(items)
        continue
    try:
        q = pl.read_csv(path, separator=";",
                        columns=["time_exchange", "ask_px", "ask_sx", "bid_px", "bid_sx"],
                        schema_overrides={"time_exchange": pl.String, "ask_px": pl.Float64,
                                          "ask_sx": pl.Float64, "bid_px": pl.Float64,
                                          "bid_sx": pl.Float64})
    except Exception:
        missing_file += len(items)
        continue
    q = q.with_columns(
        pl.col("time_exchange").str.slice(0, 26).str.to_datetime("%Y-%m-%dT%H:%M:%S%.f", strict=False).alias("ts")
    ).drop_nulls("ts").sort("ts")
    ts = q["ts"].to_list()
    for idx, target, side, fill_px in items:
        # last quote at/before target
        lo, hi = 0, len(ts)
        while lo < hi:
            mid = (lo + hi) // 2
            if ts[mid] <= target:
                lo = mid + 1
            else:
                hi = mid
        if lo == 0:
            stale += 1
            continue
        row = q.row(lo - 1, named=True)
        if (target - row["ts"]).total_seconds() > 300:
            stale += 1
            continue
        bid, ask = row["bid_px"], row["ask_px"]
        if bid is None or ask is None or bid <= 0 or ask <= bid:
            stale += 1
            continue
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 1e4
        if side == "bid":
            exit_px = bid; depth = bid * (row["bid_sx"] or 0)
            mark = (exit_px - fill_px) / fill_px * 1e4
        else:
            exit_px = ask; depth = ask * (row["ask_sx"] or 0)
            mark = (fill_px - exit_px) / fill_px * 1e4
        results[idx] = (mark, depth, spread_bps)
    done += len(items)
    if done % 500 < len(items):
        print(f"  matched {len(results)} / processed {done}", flush=True)

print(f"matched {len(results)}, missing_file {missing_file}, stale {stale}", flush=True)

out = fills.with_row_index("idx").with_columns(
    pl.col("idx").map_elements(lambda i: results.get(i, (None, None, None))[0], return_dtype=pl.Float64).alias("exec_markout_bps"),
    pl.col("idx").map_elements(lambda i: results.get(i, (None, None, None))[1], return_dtype=pl.Float64).alias("exit_touch_depth_usd"),
    pl.col("idx").map_elements(lambda i: results.get(i, (None, None, None))[2], return_dtype=pl.Float64).alias("exit_spread_bps"),
)
out.write_parquet(OUT)

FEES_RT = 1.5 + 4.5  # maker entry + taker exit
have = out.drop_nulls("exec_markout_bps").filter(
    (pl.col("exit_spread_bps") < 200) & (pl.col("exit_touch_depth_usd") > 50))
print(f"sane-quote fills: {have.height} (spread<200bp, depth>$50)")
def dstat(f, expr):
    daily = f.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(expr.mean().alias("v"))
    v = [x for x in daily["v"].to_list() if x is not None]
    n = len(v); m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, m / sd * math.sqrt(n), n

exec_net = pl.col("exec_markout_bps") - FEES_RT
mark_net = pl.col("markout_m30_bps") - 1.5
for label, f in [("ALL wide", have),
                 ("bids", have.filter(pl.col("side") == "bid")),
                 ("asks", have.filter(pl.col("side") == "ask")),
                 ("ex-SKHX", have.filter(pl.col("market") != "xyz:SKHX"))]:
    me, te, nd = dstat(f, exec_net)
    mm, tm, _ = dstat(f, mark_net)
    print(f"{label:10s} exec net {me:+7.1f}bp (t={te:+.2f}, days={nd}) | mark net same fills {mm:+7.1f}bp (t={tm:+.2f}) | haircut {me-mm:+.1f}bp | fills {f.height}")
med_depth = have["exit_touch_depth_usd"].median()
p25 = have["exit_touch_depth_usd"].quantile(0.25)
print(f"exit touch depth: median ${med_depth:,.0f}, p25 ${p25:,.0f}")
c = (have["exec_markout_bps"] - FEES_RT)
print(f"exec net p5 {c.quantile(0.05):+.1f}bp | hit {(c>0).sum()/c.len()*100:.0f}%")
print("\nper-market exec net:")
for r in have.group_by("market").agg((pl.col("exec_markout_bps") - FEES_RT).mean().alias("x"), pl.len()).sort("x", descending=True).iter_rows(named=True):
    print(f"  {r['market']:14s} {r['x']:+7.1f}bp  ({r['len']})")
