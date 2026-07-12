"""Real-spread costing for the exhaustion-reversal events.

For each long event on a market with raw L4 trade coverage, estimate the
effective spread in the entry hour and the exit hour from the gap between
mean taker-BUY and mean taker-SELL prices within a minute (both sides
present). A marketable order pays ~half the effective spread per side, so:

    round_trip_spread_bp = (entry_spread_bp + exit_spread_bp) / 2
    total_cost_bp        = 9 (fees) + round_trip_spread_bp

The report assumed 20bp total (9 fees + 11 spread/slippage). Output:
data/reports/disc_check_spreads.parquet
"""
import glob
import gzip
import io
from datetime import timedelta

import polars as pl

COVERED = {f"xyz:{s}" for s in
           "AMD ARM BE COIN CRCL HIMS HOOD INTC MRVL MSTR MU NBIS NVDA PLTR RIVN RKLB TSLA".split()}
COVERED |= {"xyz:SKHX", "xyz:SMSN", "xyz:EWY", "xyz:KR200", "xyz:SMH", "xyz:SP500",
            "xyz:XYZ100", "km:US500", "km:USTECH", "km:SMALL2000", "cash:USA500",
            "flx:USA500", "flx:USA100"}


def sym_pattern(market: str) -> str:
    dex, name = market.split(":")
    return f"{dex.upper()}_{name}"


def hour_spread_bp(market: str, ts) -> tuple[float | None, int]:
    """Median per-minute buy-sell gap in bp for the hour containing ts."""
    for probe in (ts, ts + timedelta(hours=1)):
        d = probe.strftime("%Y%m%d%H")
        hits = glob.glob(f"data/T-TRADES/D-{d}/E-HYPERLIQUIDL4/*DPERP_{sym_pattern(market)}_USDC*.csv.gz")
        if not hits:
            continue
        with gzip.open(hits[0], "rt") as f:
            df = pl.read_csv(io.StringIO(f.read()), separator=";",
                             columns=["time_exchange", "price", "taker_side"])
        if df.height == 0:
            continue
        df = df.with_columns(
            pl.col("time_exchange").str.slice(0, 16).alias("minute"))
        g = (df.group_by("minute", "taker_side").agg(pl.col("price").mean())
               .pivot(values="price", index="minute", on="taker_side"))
        if "BUY" not in g.columns or "SELL" not in g.columns:
            continue
        g = g.drop_nulls().with_columns(
            ((pl.col("BUY") - pl.col("SELL"))
             / ((pl.col("BUY") + pl.col("SELL")) / 2) * 1e4).alias("gap_bp"))
        g = g.filter(pl.col("gap_bp") > -50)  # discard pathological inversions
        if g.height < 2:
            continue
        return float(g["gap_bp"].median()), g.height
    return None, 0


ev = pl.read_parquet("data/reports/disc_check_events.parquet").filter(pl.col("side") == 1)
ev = ev.filter(pl.col("market").is_in(COVERED))
# trade coverage windows: index markets from 2026-03-11, single names from 2026-06-01
ev = ev.filter(
    pl.when(pl.col("market").is_in(["xyz:SKHX", "xyz:SMSN", "xyz:EWY", "xyz:KR200",
                                    "xyz:SMH", "xyz:SP500", "xyz:XYZ100", "km:US500",
                                    "km:USTECH", "km:SMALL2000", "cash:USA500",
                                    "flx:USA500", "flx:USA100"]))
    .then(pl.col("date") >= pl.date(2026, 3, 12))
    .otherwise(pl.col("date") >= pl.date(2026, 6, 2)))

rows = []
for r in ev.iter_rows(named=True):
    es, en = hour_spread_bp(r["market"], r["entry_ts"])
    xs, xn = hour_spread_bp(r["market"], r["exit_ts"])
    rows.append({**{k: r[k] for k in ("market", "date", "net_bp", "ret3", "liq7")},
                 "entry_spread_bp": es, "exit_spread_bp": xs,
                 "entry_minutes": en, "exit_minutes": xn})
    print(f"{r['date']} {r['market']:14s} entry={es if es is None else round(es,1)} "
          f"exit={xs if xs is None else round(xs,1)}", flush=True)

out = pl.DataFrame(rows)
out.write_parquet("data/reports/disc_check_spreads.parquet")

ok = out.drop_nulls(["entry_spread_bp", "exit_spread_bp"]).with_columns(
    ((pl.col("entry_spread_bp") + pl.col("exit_spread_bp")) / 2).alias("rt_spread_bp"))
ok = ok.with_columns((9 + pl.col("rt_spread_bp")).alias("total_cost_bp"),
                     (pl.col("net_bp") + 20 - 9 - pl.col("rt_spread_bp")).alias("net_realcost_bp"))
print(f"\ncovered events with both spreads: {ok.height} / {ev.height} candidates / 214 all longs")
for c in ("entry_spread_bp", "exit_spread_bp", "rt_spread_bp", "total_cost_bp"):
    s = ok[c]
    print(f"{c:18s} mean={s.mean():6.1f} med={s.median():6.1f} p25={s.quantile(.25):6.1f} p75={s.quantile(.75):6.1f} p95={s.quantile(.95):7.1f}")
print(f"\nnet with 20bp assumption : {ok['net_bp'].mean():+.1f}bp")
print(f"net with measured costs  : {ok['net_realcost_bp'].mean():+.1f}bp")
days = ok.group_by("date").agg(pl.col("net_realcost_bp").mean())
m, s, n = days["net_realcost_bp"].mean(), days["net_realcost_bp"].std(), days.height
print(f"day-clustered: n={n} mean={m:+.1f} t={m/s*n**0.5:.2f}")
print("\nby market:")
print(ok.group_by("market").agg(pl.len(), pl.col("rt_spread_bp").median().round(1),
                                pl.col("net_realcost_bp").mean().round(1)).sort("rt_spread_bp", descending=True))
