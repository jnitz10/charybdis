"""Oracle-conditioning of harvester fills, full sample (13 mkts + 17 single names).

For each wide (δ≥100bp) fill after 2026-06-17, measure the oracle's move over
the 30 minutes ending at the fill minute and classify:
  confirmed  — oracle moved in the fill's direction by ≥25% of quote distance δ
  perp_only  — |oracle move| < 25% of δ (dislocation with a flat anchor)
  opposed    — oracle moved the other way by ≥25% of δ
Question: does oracle confirmation isolate the winning subset (as in the
164-fill pilot: confirmed +17bp, perp-only −26bp), and does it rescue a
positive pocket in the otherwise-flat single names?

Scale guard: fills whose price is >30% away from the oracle (bare-symbol
multi-dex scale wart) are dropped and counted.
"""

from __future__ import annotations

import bisect
import math
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
ORACLE_DIR = ROOT / "data/reports/oracle_bars"
ORACLE_START = datetime(2026, 6, 17)
PRE_MIN = 30
CONFIRM_FRAC = 0.25

fills13 = pl.read_parquet(ROOT / "data/reports/ff_harvest_fills_all.parquet").with_columns(
    pl.lit("mkts13").alias("cohort"))
fillsSN = pl.read_parquet(ROOT / "data/reports/ff_harvest_fills_singlenames.parquet").with_columns(
    pl.lit("singles").alias("cohort"))
fills = pl.concat([fills13, fillsSN]).filter(
    (pl.col("delta_bps") >= 100) & (pl.col("fill_time") >= ORACLE_START))
print(f"{fills.height} wide fills in oracle window "
      f"(13mkt {fills.filter(pl.col('cohort')=='mkts13').height}, "
      f"singles {fills.filter(pl.col('cohort')=='singles').height})", flush=True)

oracle: dict[str, tuple[list, list]] = {}
for shard in ORACLE_DIR.glob("*.parquet"):
    df = pl.read_parquet(shard)
    oracle[shard.stem] = (df["minute"].to_list(), df["oracle_px"].to_list())
print(f"oracle shards: {sorted(oracle)}", flush=True)


def oracle_at(sym, t):
    times, px = oracle[sym]
    i = bisect.bisect_right(times, t) - 1
    if i < 0 or (t - times[i]) > timedelta(minutes=10):
        return None
    return px[i]


rows = []
no_shard, stale, scale_drop = set(), 0, 0
for r in fills.iter_rows(named=True):
    sym = r["market"].split(":", 1)[1]
    if sym not in oracle:
        no_shard.add(r["market"])
        continue
    o_now = oracle_at(sym, r["fill_time"])
    o_pre = oracle_at(sym, r["fill_time"] - timedelta(minutes=PRE_MIN))
    if o_now is None or o_pre is None:
        stale += 1
        continue
    if abs(r["fill_px"] / o_now - 1) > 0.30:
        scale_drop += 1
        continue
    omove = (o_now - o_pre) / o_pre * 1e4  # bps, signed
    delta = r["delta_bps"]
    toward = -omove if r["side"] == "bid" else omove  # bps in fill direction
    if toward >= CONFIRM_FRAC * delta:
        cls = "confirmed"
    elif toward <= -CONFIRM_FRAC * delta:
        cls = "opposed"
    else:
        cls = "perp_only"
    rows.append({**{k: r[k] for k in ("market", "side", "delta_bps", "fill_time",
                                      "markout_m30_bps", "cohort")},
                 "oracle_move_bps": omove, "toward_bps": toward, "cls": cls})

out = pl.DataFrame(rows)
out.write_parquet(ROOT / "data/reports/ff_oracle_condition_full.parquet")
print(f"classified {out.height} fills; dropped: no-oracle-shard markets={sorted(no_shard)}, "
      f"stale={stale}, scale={scale_drop}", flush=True)


def stats(v):
    v = [x for x in v if x is not None]
    n = len(v)
    if n < 2:
        return float("nan"), float("nan"), n
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, (m / sd * math.sqrt(n) if sd > 0 else float("nan")), n


def report(label, g):
    if g.height == 0:
        print(f"  {label:28s} —")
        return
    daily = g.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(
        pl.col("markout_m30_bps").mean())
    m, t, nd = stats(daily["markout_m30_bps"].to_list())
    print(f"  {label:28s} {g.height:5d} fills {nd:3d} days  m30 {m:+7.1f}bp  t={t:+5.2f}", flush=True)


for cohort in ("mkts13", "singles", None):
    base = out if cohort is None else out.filter(pl.col("cohort") == cohort)
    print(f"\n=== {'POOLED' if cohort is None else cohort} ===", flush=True)
    for side in ("bid", "ask"):
        for cls in ("confirmed", "perp_only", "opposed"):
            report(f"{side} {cls}", base.filter((pl.col("side") == side) & (pl.col("cls") == cls)))
