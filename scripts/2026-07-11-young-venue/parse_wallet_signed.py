"""Second parse pass: SIGNED taker flow per (market, date, wallet).

Output: data/reports/walletflow_taker_signed_daily.parquet
  market, date, user_taker, buy_dv, sell_dv, trades
"""

from __future__ import annotations

import gzip
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl

from charybdis.loaders import parse_flat_file_key

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
OUT = ROOT / "data/reports/walletflow_taker_signed_daily.parquet"

files = sorted(ROOT.glob("data/T-TRADES/D-*/E-HYPERLIQUIDL4/*.csv.gz"))
sink = defaultdict(lambda: [0.0, 0.0, 0])
parsed = skipped = corrupt = 0
for i, path in enumerate(files):
    try:
        with gzip.open(path, "rt") as fh:
            header = fh.readline().strip().split(";")
    except Exception:
        corrupt += 1
        continue
    if "user_taker" not in header:
        skipped += 1
        continue
    key = parse_flat_file_key(path)
    market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
    date = datetime.strptime(key.partition[:8], "%Y%m%d").date()
    try:
        df = pl.read_csv(path, separator=";",
                         columns=["price", "base_amount", "taker_side", "user_taker"],
                         schema_overrides={"price": pl.Float64, "base_amount": pl.Float64,
                                           "taker_side": pl.String, "user_taker": pl.String})
    except Exception:
        corrupt += 1
        continue
    parsed += 1
    agg = (df.filter(pl.col("user_taker").is_not_null() & (pl.col("user_taker") != ""))
           .with_columns((pl.col("price") * pl.col("base_amount")).alias("dv"))
           .group_by("user_taker", "taker_side").agg(pl.col("dv").sum(), pl.len()))
    for w, side, dv, n in agg.iter_rows():
        e = sink[(market, date, w)]
        if side == "BUY":
            e[0] += dv
        else:
            e[1] += dv
        e[2] += n
    if (i + 1) % 2000 == 0:
        print(f"  {i+1}/{len(files)}", flush=True)

frame = pl.DataFrame([
    {"market": m, "date": d, "user_taker": w, "buy_dv": v[0], "sell_dv": v[1], "trades": v[2]}
    for (m, d, w), v in sink.items()
]).sort(["market", "date"])
frame.write_parquet(OUT)
print(f"parsed={parsed} skipped={skipped} corrupt={corrupt}; {frame.height} rows -> {OUT.name}", flush=True)
