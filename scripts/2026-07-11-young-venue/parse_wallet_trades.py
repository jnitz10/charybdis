"""Parse wallet-era L4 trade files into per-(market, date, wallet) volume panels.

Output: two parquets in data/reports/ —
  walletflow_taker_daily.parquet: market, date, user_taker, dollar_vol, trades
  walletflow_maker_daily.parquet: market, date, user_maker, dollar_vol, trades
Only files whose header carries user_taker are included (wallet era, ~Jun 1+).
Corrupt gzip files are skipped and counted.
"""

from __future__ import annotations

import gzip
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import polars as pl

from charybdis.loaders import parse_flat_file_key

ROOT = Path("/home/jnitz/Documents/trading/charybdis")
OUT_T = ROOT / "data/reports/walletflow_taker_daily.parquet"
OUT_M = ROOT / "data/reports/walletflow_maker_daily.parquet"

files = sorted(ROOT.glob("data/T-TRADES/D-*/E-HYPERLIQUIDL4/*.csv.gz"))
print(f"{len(files)} L4 trade files total", flush=True)

taker = defaultdict(lambda: [0.0, 0])
maker = defaultdict(lambda: [0.0, 0])
skipped_no_wallet = corrupt = parsed = 0

for i, path in enumerate(files):
    try:
        with gzip.open(path, "rt") as fh:
            header = fh.readline().strip().split(";")
    except Exception:
        corrupt += 1
        continue
    if "user_taker" not in header:
        skipped_no_wallet += 1
        continue
    key = parse_flat_file_key(path)
    market = key.coin.split(":", 1)[0].lower() + ":" + key.coin.split(":", 1)[1]
    date = datetime.strptime(key.partition[:8], "%Y%m%d").date()
    try:
        df = pl.read_csv(
            path, separator=";",
            columns=["price", "base_amount", "user_taker", "user_maker"],
            schema_overrides={"price": pl.Float64, "base_amount": pl.Float64,
                              "user_taker": pl.String, "user_maker": pl.String},
        )
    except Exception:
        corrupt += 1
        continue
    parsed += 1
    df = df.with_columns((pl.col("price") * pl.col("base_amount")).alias("dv"))
    for col, sink in (("user_taker", taker), ("user_maker", maker)):
        agg = df.filter(pl.col(col).is_not_null() & (pl.col(col) != "")).group_by(col).agg(
            pl.col("dv").sum(), pl.len())
        for w, dv, n in agg.iter_rows():
            entry = sink[(market, date, w)]
            entry[0] += dv
            entry[1] += n
    if (i + 1) % 1000 == 0:
        print(f"  {i+1}/{len(files)} (parsed {parsed})", flush=True)

print(f"parsed={parsed} no_wallet_era={skipped_no_wallet} corrupt={corrupt}", flush=True)

for sink, col, out in ((taker, "user_taker", OUT_T), (maker, "user_maker", OUT_M)):
    frame = pl.DataFrame(
        [{"market": m, "date": d, col: w, "dollar_vol": v[0], "trades": v[1]}
         for (m, d, w), v in sink.items()]
    ).sort(["market", "date", "dollar_vol"], descending=[False, False, True])
    frame.write_parquet(out)
    print(f"{out.name}: {frame.height} rows, {frame['market'].n_unique()} markets, "
          f"{frame[col].n_unique()} wallets, {frame['date'].min()} -> {frame['date'].max()}", flush=True)
