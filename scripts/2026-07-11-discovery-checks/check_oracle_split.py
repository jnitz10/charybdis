"""Oracle-basis split for the exhaustion-reversal events.

Question: is the -8% three-day perp decline a noisy proxy for a large
perp-minus-oracle residual (basis convergence), the same object as the
harvester's oracle conditioning?

For each long event on a market with an oracle shard (archive starts
2026-06-17, so events from 2026-06-20):
  oracle_ret3    = oracle close-to-close over the same three sessions
  resid3         = perp ret3 - oracle_ret3   (negative => perp fell more)
  entry_basis_bp = perp entry price vs oracle at entry minute

Split 24h outcomes by whether the oracle confirmed the decline, and
correlate entry basis with outcome. Output: disc_check_oracle.parquet
"""
from datetime import timedelta
from pathlib import Path

import polars as pl

SHARDS = {p.stem: p for p in Path("data/reports/oracle_bars").glob("*.parquet")}

ev = (pl.read_parquet("data/reports/disc_check_events.parquet")
      .filter((pl.col("side") == 1) & (pl.col("date") >= pl.date(2026, 6, 20)))
      .with_columns(pl.col("market").str.split(":").list.last().alias("bare")))
ev = ev.filter(pl.col("bare").is_in(list(SHARDS)))
print(f"events with oracle coverage: {ev.height} on {ev['bare'].n_unique()} names")

rows = []
for r in ev.iter_rows(named=True):
    o = pl.read_parquet(SHARDS[r["bare"]]).sort("minute")

    def asof(ts):
        s = o.filter(pl.col("minute") <= ts).tail(1)
        return None if s.height == 0 else s["oracle_px"][0]

    t_close = r["date"] + timedelta(days=1)          # close of day t = 00:00 t+1
    o_now, o_then = asof(t_close), asof(t_close - timedelta(days=3))
    o_entry = asof(r["entry_ts"] + timedelta(minutes=1))
    if not (o_now and o_then and o_entry):
        continue
    if abs(r["entry_px"] / o_entry - 1) > 0.3:       # wrong-dex price scale
        continue
    oracle_ret3 = o_now / o_then - 1
    rows.append({**{k: r[k] for k in ("market", "date", "ret3", "net_bp")},
                 "oracle_ret3": oracle_ret3,
                 "resid3": r["ret3"] - oracle_ret3,
                 "entry_basis_bp": (r["entry_px"] / o_entry - 1) * 1e4})

df = pl.DataFrame(rows).sort("date")
df.write_parquet("data/reports/disc_check_oracle.parquet")
print(df.with_columns(pl.col("ret3", "oracle_ret3", "resid3").round(4),
                      pl.col("net_bp", "entry_basis_bp").round(1)))

conf = df.filter(pl.col("oracle_ret3") <= 0.5 * pl.col("ret3"))  # oracle fell >= half as far
over = df.filter(pl.col("oracle_ret3") > 0.5 * pl.col("ret3"))
for label, g in [("oracle-CONFIRMED (underlying fell too)", conf),
                 ("perp OVERSHOOT (oracle fell < half)", over)]:
    if g.height:
        m, s = g["net_bp"].mean(), g["net_bp"].std()
        t = m / s * g.height ** 0.5 if s else float("nan")
        print(f"{label}: n={g.height} mean={m:+.1f}bp t={t:.2f}")

print("\ncorrelations with 24h net:")
for c in ("resid3", "entry_basis_bp", "oracle_ret3", "ret3"):
    print(f"  {c:15s} r={df.select(pl.corr(c, 'net_bp')).item():+.3f}")

neg = df.filter(pl.col("entry_basis_bp") < df["entry_basis_bp"].median())
pos = df.filter(pl.col("entry_basis_bp") >= df["entry_basis_bp"].median())
print(f"\nentry basis below median ({df['entry_basis_bp'].median():.0f}bp): "
      f"n={neg.height} mean={neg['net_bp'].mean():+.1f}bp")
print(f"entry basis above median: n={pos.height} mean={pos['net_bp'].mean():+.1f}bp")
