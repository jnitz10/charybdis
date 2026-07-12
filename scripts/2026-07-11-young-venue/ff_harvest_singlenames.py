"""Forced-flow passive-harvester backtest on the 17 newly-pulled xyz single names.

Same conservative trades-only fill model as ff_harvest_all.py: a resting bid at
P counts as filled only when a print occurs strictly below P; symmetric asks.
Quotes re-peg each minute to the trailing 5-minute median trade price; no
quoting after 30 trade-silent minutes; one fill per side per 60-minute
cooldown. Markouts at +5m/+30m/+4h vs first traded minute at/after the offset.

Stage 1 is resumable: per-name minute bars flush to data/reports/ff_bars_sn/
and are skipped on rerun.
"""

from __future__ import annotations

import math
import re
from datetime import timedelta
from pathlib import Path

import polars as pl

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
SHARD_DIR = ROOT / "data/reports/ff_bars_sn"
SHARD_DIR.mkdir(exist_ok=True)
OUT = ROOT / "data/reports/ff_harvest_fills_singlenames.parquet"
NAMES = ["INTC", "HIMS", "MSTR", "CRCL", "HOOD", "COIN", "MU", "MRVL",
         "TSLA", "NVDA", "PLTR", "RKLB", "NBIS", "AMD", "ARM", "BE", "RIVN"]
DELTAS = [0.0025, 0.005, 0.01, 0.02]
COOLDOWN_MIN = 60
HORIZONS = {"m5": 5, "m30": 30, "h4": 240}
TOL_MIN = 30

PAT = re.compile(r"_DPERP_XYZ_([A-Z0-9]+)_USDC")

# ---- stage 1: per-name minute bars (resumable) ----
files_by_name: dict[str, list[Path]] = {n: [] for n in NAMES}
for path in ROOT.glob("data/T-TRADES/D-*/E-HYPERLIQUIDL4/**/*.csv.gz"):
    m = PAT.search(path.name)
    if m and m.group(1) in files_by_name:
        files_by_name[m.group(1)].append(path)

for n in NAMES:
    files_by_name[n].sort()
    shard = SHARD_DIR / f"{n}.parquet"
    if shard.exists():
        print(f"{n}: shard exists, skip ({len(files_by_name[n])} files)", flush=True)
        continue
    sink: dict = {}
    corrupt = 0
    for fi, path in enumerate(files_by_name[n]):
        if fi % 200 == 0:
            print(f"  {n} parse {fi}/{len(files_by_name[n])}", flush=True)
        try:
            df = pl.read_csv(path, separator=";", columns=["time_exchange", "price"],
                             schema_overrides={"time_exchange": pl.String, "price": pl.Float64})
        except Exception:
            corrupt += 1
            continue
        if df.height == 0:
            continue
        df = df.with_columns(
            pl.col("time_exchange").str.slice(0, 16).str.to_datetime("%Y-%m-%dT%H:%M").alias("minute"))
        agg = df.group_by("minute").agg(
            pl.col("price").min().alias("lo"), pl.col("price").max().alias("hi"),
            pl.col("price").median().alias("med"), pl.len().alias("n"))
        for mnt, lo, hi, med, cnt in agg.iter_rows():
            row = sink.get(mnt)
            if row is None:
                sink[mnt] = [lo, hi, med, cnt]
            else:
                row[0] = min(row[0], lo); row[1] = max(row[1], hi)
                row[2] = (row[2] * row[3] + med * cnt) / (row[3] + cnt); row[3] += cnt
    bars = pl.DataFrame({
        "minute": sorted(sink),
        "lo": [sink[t][0] for t in sorted(sink)],
        "hi": [sink[t][1] for t in sorted(sink)],
        "med": [sink[t][2] for t in sorted(sink)],
        "n": [sink[t][3] for t in sorted(sink)],
    })
    bars.write_parquet(shard)
    print(f"{n}: {bars.height} minute bars -> shard (corrupt={corrupt})", flush=True)

# ---- stage 2: fill simulation ----
fee_table = pl.read_parquet(ROOT / "data/reports/study3_fee_table.parquet")
fee_by_dex = dict(fee_table.select("dex", "effective_maker_bps").iter_rows())
maker_fee = fee_by_dex.get("xyz", 1.5)
print(f"xyz maker fee: {maker_fee}bp", flush=True)

records = []
for n in NAMES:
    bars = pl.read_parquet(SHARD_DIR / f"{n}.parquet")
    times = bars["minute"].to_list()
    lo_l, hi_l, med_l = bars["lo"].to_list(), bars["hi"].to_list(), bars["med"].to_list()
    market = f"xyz:{n}"
    for delta in DELTAS:
        for side in ("bid", "ask"):
            cooldown_until = None
            for i, t in enumerate(times):
                if i < 5:
                    continue
                if cooldown_until is not None and t < cooldown_until:
                    continue
                if (t - times[i - 1]).total_seconds() > 1800:
                    continue
                window = sorted(med_l[i - 5:i])
                ref = window[2]
                if side == "bid":
                    px = ref * (1 - delta)
                    filled = lo_l[i] < px
                else:
                    px = ref * (1 + delta)
                    filled = hi_l[i] > px
                if not filled:
                    continue
                mk = {}
                for hname, off in HORIZONS.items():
                    target = None
                    for j in range(i + 1, len(times)):
                        dt_min = (times[j] - t).total_seconds() / 60
                        if dt_min >= off:
                            if dt_min <= off + TOL_MIN:
                                target = med_l[j]
                            break
                    if target is None:
                        mk[hname] = None
                    else:
                        raw = (target - px) / px if side == "bid" else (px - target) / px
                        mk[hname] = raw * 1e4
                records.append({
                    "market": market, "side": side, "delta_bps": delta * 1e4,
                    "fill_time": t, "fill_px": px, "ref": ref,
                    "markout_m5_bps": mk["m5"], "markout_m30_bps": mk["m30"], "markout_h4_bps": mk["h4"],
                })
                cooldown_until = t + timedelta(minutes=COOLDOWN_MIN)

fills = pl.DataFrame(records)
fills.write_parquet(OUT)
print(f"{fills.height} fills -> {OUT.name}", flush=True)


def stats(v):
    v = [x for x in v if x is not None]
    n = len(v)
    if n < 2:
        return float("nan"), float("nan"), n
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))
    return m, (m / sd * math.sqrt(n) if sd > 0 else float("nan")), n


print(f"\n{'mkt':10s} {'side':4s} {'δbp':>4s} {'fills':>6s} | {'m5':>7s} {'t':>5s} | {'m30':>7s} {'t':>5s} | {'h4':>7s} {'t':>5s} | {'m30 p5':>7s} {'net30':>6s}")
for (mkt, side, db), g in sorted(fills.partition_by(["market", "side", "delta_bps"], as_dict=True).items()):
    daily = g.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(
        pl.col("markout_m5_bps").mean(), pl.col("markout_m30_bps").mean(), pl.col("markout_h4_bps").mean())
    m5, t5, _ = stats(daily["markout_m5_bps"].to_list())
    m30, t30, nd = stats(daily["markout_m30_bps"].to_list())
    h4, t4, _ = stats(daily["markout_h4_bps"].to_list())
    p5 = g["markout_m30_bps"].drop_nulls().quantile(0.05) if g["markout_m30_bps"].drop_nulls().len() else None
    net30 = (m30 - maker_fee) if m30 == m30 else float("nan")
    print(f"{mkt:10s} {side:4s} {db:4.0f} {g.height:>6d} | "
          f"{m5:>7.1f} {t5:>5.1f} | {m30:>7.1f} {t30:>5.1f} | {h4:>7.1f} {t4:>5.1f} | "
          f"{p5 if p5 is None else round(p5, 1):>7} {net30:>6.1f}")

# pooled wide-delta cells (the live pocket from the 13-market study)
print("\npooled cells (day-clustered):", flush=True)
for label, flt in [
    ("bids δ>=100", (pl.col("side") == "bid") & (pl.col("delta_bps") >= 100)),
    ("asks δ>=100", (pl.col("side") == "ask") & (pl.col("delta_bps") >= 100)),
    ("both δ>=100", pl.col("delta_bps") >= 100),
    ("bids δ=25", (pl.col("side") == "bid") & (pl.col("delta_bps") == 25)),
]:
    g = fills.filter(flt)
    if g.height == 0:
        print(f"  {label}: no fills")
        continue
    daily = g.with_columns(pl.col("fill_time").dt.date().alias("d")).group_by("d").agg(
        pl.col("markout_m30_bps").mean())
    m30, t30, nd = stats(daily["markout_m30_bps"].to_list())
    print(f"  {label}: {g.height} fills over {nd} fill-days, m30 {m30:+.1f}bp (net {m30 - maker_fee:+.1f}) t={t30:.2f}")
