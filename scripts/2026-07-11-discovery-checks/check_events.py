"""Reproduce the frozen exhaustion-reversal event set from strategy_discovery_2026-07-11.

Rule: HIP-3 contracts, age 7-55 days (first daily candle proxy, exclude
first-observed 2026-01-01), trailing 7-session median notional >= $1M
(signal day excluded), 3-session close return <= -8% (long) / >= +8% (short),
enter next hourly open after 00:00 UTC signal, exit at hourly open >= entry+24h.
Net = price return - 20bp round trip (funding ignored; report avg +2.1bp).

Output: data/reports/disc_check_events.parquet
"""
import polars as pl
from datetime import timedelta

d = (
    pl.read_parquet("data/reports/study3_candles_1d.parquet")
    .filter(pl.col("dex") != "main")
    .with_columns(
        pl.from_epoch("open_time_ms", time_unit="ms").dt.date().alias("date"),
        (pl.col("v") * pl.col("close")).alias("ntl"),
    )
    .sort("market", "date")
)

d = d.with_columns(
    pl.col("date").min().over("market").alias("first_date"),
    pl.col("date").max().over("market").alias("last_date"),
)
d = d.filter(pl.col("first_date") != pl.date(2026, 1, 1))
d = d.with_columns(
    (pl.col("date") - pl.col("first_date")).dt.total_days().alias("age"),
    (pl.col("close") / pl.col("close").shift(3).over("market") - 1).alias("ret3"),
    pl.col("ntl").shift(1).rolling_median(7).over("market").alias("liq7"),
)

sig = d.filter(
    (pl.col("age") >= 7)
    & (pl.col("age") < 56)
    & (pl.col("liq7") >= 1_000_000)
    & (pl.col("ret3").abs() >= 0.08)
).with_columns(pl.when(pl.col("ret3") <= -0.08).then(1).otherwise(-1).alias("side"))

h = (
    pl.read_parquet("data/reports/study3_candles_1h.parquet")
    .filter(pl.col("dex") != "main")
    .with_columns(pl.from_epoch("open_time_ms", time_unit="ms").alias("ts"))
    .select("market", "ts", "open")
    .sort("market", "ts")
)

sig = sig.with_columns(
    (pl.col("date").cast(pl.Datetime) + pl.duration(days=1)).alias("signal_ts")
)

entry = sig.select("market", "date", "side", "ret3", "age", "liq7", "last_date", "signal_ts").join_asof(
    h.rename({"ts": "entry_ts", "open": "entry_px"}),
    left_on="signal_ts", right_on="entry_ts", by="market", strategy="forward",
    tolerance=timedelta(hours=6),
)
entry = entry.with_columns((pl.col("entry_ts") + pl.duration(hours=24)).alias("exit_target"))
ev = entry.join_asof(
    h.rename({"ts": "exit_ts", "open": "exit_px"}),
    left_on="exit_target", right_on="exit_ts", by="market", strategy="forward",
    tolerance=timedelta(hours=6),
).filter(pl.col("entry_px").is_not_null() & pl.col("exit_px").is_not_null())

ev = ev.with_columns(
    (pl.col("side") * (pl.col("exit_px") / pl.col("entry_px") - 1) * 1e4 - 20).alias("net_bp")
)

ev.write_parquet("data/reports/disc_check_events.parquet")


def daystats(df, label):
    days = df.group_by("date").agg(pl.col("net_bp").mean().alias("day_bp"))
    n = days.height
    m = days["day_bp"].mean()
    s = days["day_bp"].std()
    t = m / s * n**0.5 if s else float("nan")
    print(f"{label}: events={df.height} days={n} mkts={df['market'].n_unique()} "
          f"mean_day={m:+.1f}bp t={t:.2f}")


longs = ev.filter(pl.col("side") == 1)
shorts = ev.filter(pl.col("side") == -1)
daystats(longs, "LONG  (fall<=-8%)")
daystats(shorts, "SHORT (rally>=+8%)")
daystats(ev, "BOTH")

top1 = ev.sort("ret3", descending=False).with_columns(pl.col("ret3").abs().alias("a")) \
        .sort(["date", "a"], descending=[False, True]).group_by("date", maintain_order=True).first()
daystats(top1, "TOP-1 per day (both sides)")

print("\nLong events by market (top 15):")
print(longs.group_by("market").agg(pl.len(), pl.col("net_bp").mean()).sort("len", descending=True).head(15))
print("\nLong events by month:")
print(longs.with_columns(pl.col("date").dt.strftime("%Y-%m").alias("mo"))
      .group_by("mo").agg(pl.len(), pl.col("net_bp").mean()).sort("mo"))
