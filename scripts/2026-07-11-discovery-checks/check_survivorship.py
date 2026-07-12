"""Survivorship check for the exhaustion-reversal candidate.

Questions:
1. Does the candle panel include markets that died mid-sample? (yes -> harvest
   is not current-universe-only; quantify)
2. Do qualifying long events occur on markets that die soon after? What did
   those events return before death?
3. How many signals fail to complete (no exit candle 24h later) because the
   market stopped printing -- the silent in-panel survivorship channel?
4. Birth/death time series: does market disappearance only happen near the
   harvest date (which would suggest earlier deaths are missing entirely)?
"""
import polars as pl
from datetime import timedelta

d = (
    pl.read_parquet("data/reports/study3_candles_1d.parquet")
    .filter(pl.col("dex") != "main")
    .with_columns(pl.from_epoch("open_time_ms", time_unit="ms").dt.date().alias("date"),
                  (pl.col("v") * pl.col("close")).alias("ntl"))
    .sort("market", "date")
)
span = d.group_by("market").agg(
    pl.col("date").min().alias("first"), pl.col("date").max().alias("last"),
    pl.len().alias("rows"), pl.col("ntl").median().alias("med_ntl"))

END = pl.date(2026, 7, 7)
dead = span.filter(pl.col("last") < END)
print(f"markets: {span.height}, dead before {END}: {dead.height}")
print("\ndeaths by month (last candle):")
print(dead.with_columns(pl.col("last").dt.strftime("%Y-%m").alias("mo"))
      .group_by("mo").len().sort("mo"))
print("\nbirths by month (first candle, ex left-censored 01-01):")
print(span.filter(pl.col("first") != pl.date(2026, 1, 1))
      .with_columns(pl.col("first").dt.strftime("%Y-%m").alias("mo"))
      .group_by("mo").len().sort("mo"))

# gap analysis: a "death" that is really an idle gap would resume later.
# check whether dead markets have internal multi-day gaps too (candles only
# print when the market is alive; long internal gaps = idle, not delisted)
g = d.with_columns((pl.col("date") - pl.col("date").shift(1).over("market")).dt.total_days().alias("gap"))
print("\nmax internal gap distribution (days), alive markets:")
alive_g = g.join(span.select("market", "last"), on="market").filter(pl.col("last") >= END)
print(alive_g.group_by("market").agg(pl.col("gap").max().alias("maxgap"))
      .group_by("maxgap").len().sort("maxgap").head(10))

# events vs death
ev = pl.read_parquet("data/reports/disc_check_events.parquet")
longs = ev.filter(pl.col("side") == 1).join(span.select("market", "last"), on="market")
longs = longs.with_columns((pl.col("last") - pl.col("date")).dt.total_days().alias("days_to_death"))
on_dead = longs.filter(pl.col("last") < END)
print(f"\nlong events total: {longs.height}; on markets dead before {END}: {on_dead.height} "
      f"({on_dead['market'].n_unique()} markets)")
print("long events by days-to-death bucket:")
print(longs.with_columns(
    pl.when(pl.col("days_to_death") <= 7).then(pl.lit("<=7d"))
    .when(pl.col("days_to_death") <= 21).then(pl.lit("8-21d"))
    .when(pl.col("last") < END).then(pl.lit(">21d, died"))
    .otherwise(pl.lit("survived")).alias("bucket"))
    .group_by("bucket").agg(pl.len(), pl.col("net_bp").mean().round(1)).sort("bucket"))

# silent dropouts: re-run signal generation and count signals with no entry or no exit
d2 = d.with_columns(pl.col("date").min().over("market").alias("first_date"))
d2 = d2.filter(pl.col("first_date") != pl.date(2026, 1, 1)).with_columns(
    (pl.col("date") - pl.col("first_date")).dt.total_days().alias("age"),
    (pl.col("close") / pl.col("close").shift(3).over("market") - 1).alias("ret3"),
    pl.col("ntl").shift(1).rolling_median(7).over("market").alias("liq7"))
sig = d2.filter((pl.col("age") >= 7) & (pl.col("age") < 56) & (pl.col("liq7") >= 1_000_000)
                & (pl.col("ret3") <= -0.08))
h = (pl.read_parquet("data/reports/study3_candles_1h.parquet").filter(pl.col("dex") != "main")
     .with_columns(pl.from_epoch("open_time_ms", time_unit="ms").alias("ts"))
     .select("market", "ts", "open").sort("market", "ts"))
sig = sig.with_columns((pl.col("date").cast(pl.Datetime) + pl.duration(days=1)).alias("signal_ts"))
e = sig.select("market", "date", "signal_ts").join_asof(
    h.rename({"ts": "entry_ts", "open": "entry_px"}), left_on="signal_ts", right_on="entry_ts",
    by="market", strategy="forward", tolerance=timedelta(hours=6))
e = e.with_columns((pl.col("entry_ts") + pl.duration(hours=24)).alias("exit_target"))
e = e.join_asof(h.rename({"ts": "exit_ts", "open": "exit_px"}), left_on="exit_target",
                right_on="exit_ts", by="market", strategy="forward", tolerance=timedelta(hours=6))
no_entry = e.filter(pl.col("entry_px").is_null())
no_exit = e.filter(pl.col("entry_px").is_not_null() & pl.col("exit_px").is_null())
print(f"\nlong signals: {e.height}; no entry candle within 6h: {no_entry.height}; "
      f"entered but no exit candle within 6h of +24h: {no_exit.height}")
if no_exit.height:
    print(no_exit.select("market", "date"))
    # what happened to those markets? last daily close vs entry
    ne = no_exit.join(span.select("market", "last"), on="market")
    lastpx = d.select("market", "date", "close").rename({"date": "last", "close": "last_close"})
    ne = ne.join(lastpx, on=["market", "last"])
    ne = ne.with_columns(((pl.col("last_close") / pl.col("entry_px") - 1) * 1e4).alias("to_last_bp"))
    print(ne.select("market", "date", "last", "entry_px", "last_close", "to_last_bp"))
