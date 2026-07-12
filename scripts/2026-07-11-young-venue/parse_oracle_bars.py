"""Parse T-HLORACLEPRICES files to per-symbol minute bars (resumable shards).

Output: data/reports/oracle_bars/{SYM}.parquet with per-minute last oracle_px,
last mark_px, last external_perp_px, and update count. Oracle table exists in
the archive only from 2026-06-17.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import polars as pl

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
OUT_DIR = ROOT / "data/reports/oracle_bars"
OUT_DIR.mkdir(exist_ok=True)

PAT = re.compile(r"\+S-([A-Z0-9]+)\.csv\.gz$")

files_by_sym: dict[str, list[Path]] = defaultdict(list)
for path in ROOT.glob("data/T-HLORACLEPRICES/D-*/E-HYPERLIQUIDL4/*.csv.gz"):
    m = PAT.search(path.name)
    if m:
        files_by_sym[m.group(1)].append(path)

print(f"{sum(len(v) for v in files_by_sym.values())} files, {len(files_by_sym)} symbols", flush=True)

for sym in sorted(files_by_sym):
    shard = OUT_DIR / f"{sym}.parquet"
    if shard.exists():
        print(f"{sym}: shard exists, skip", flush=True)
        continue
    paths = sorted(files_by_sym[sym])
    frames = []
    corrupt = 0
    for fi, path in enumerate(paths):
        if fi % 200 == 0:
            print(f"  {sym} parse {fi}/{len(paths)}", flush=True)
        try:
            df = pl.read_csv(path, separator=";",
                             columns=["time_exchange", "oracle_px", "mark_px", "external_perp_px"],
                             schema_overrides={"time_exchange": pl.String, "oracle_px": pl.Float64,
                                               "mark_px": pl.Float64, "external_perp_px": pl.Float64})
        except Exception:
            corrupt += 1
            continue
        if df.height == 0:
            continue
        frames.append(df)
    if not frames:
        print(f"{sym}: no data (corrupt={corrupt})", flush=True)
        continue
    allrows = pl.concat(frames).with_columns(
        pl.col("time_exchange").str.slice(0, 16).str.to_datetime("%Y-%m-%dT%H:%M").alias("minute"))
    bars = (allrows.sort("time_exchange")
            .group_by("minute")
            .agg(pl.col("oracle_px").last(), pl.col("mark_px").last(),
                 pl.col("external_perp_px").last(), pl.len().alias("n_updates"))
            .sort("minute"))
    bars.write_parquet(shard)
    print(f"{sym}: {bars.height} minute bars -> shard (corrupt={corrupt})", flush=True)

print("done", flush=True)
