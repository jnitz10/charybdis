"""S-C-bis gate variant: long-top-daily gated by trailing 7d universe tape >= 0.

Gate is causal (trailing close-to-close universe return known at rebalance).
Implemented by wrapping signal_cross_section: on risk-off rebalances the
cross-section is empty, so the harness closes all positions and charges the
exit turnover. Gated long-universe is run as a control to separate gate value
from funding-selection value.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import polars as pl

from charybdis import run_study3_carry as sc
from charybdis.markout import cluster_bootstrap_panel_statistic
from charybdis.study3_carry import assign_deciles, signal_cross_section

import importlib.util
spec = importlib.util.spec_from_file_location(
    "run_scbis", Path(__file__).with_name("run_scbis.py"))
bis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bis)  # reuse spread_table_from_prior, targets, summarize

REPORTS = Path(sc.ROOT) / "data/reports"


def main() -> None:
    universe, funding, candles, fees, anatomy = sc.load_inputs()
    candidates = universe.filter(
        pl.col("passes_liquidity_floor") & pl.col("coverage_status").is_in(sorted(sc.ALLOWED_COVERAGE))
    )["market"].to_list()
    spreads = bis.spread_table_from_prior(candidates)
    funding_map, candle_map = sc._maps(funding, candles)
    start = min(min(rows)[0] for m, rows in funding_map.items() if m in candidates) + timedelta(days=7)
    stop = max(row[1] for rows in candle_map.values() for row in rows)
    daily = sc._schedule(start, stop, 24)

    # causal gate: trailing 7d equal-weight universe return >= 0
    gate: dict[object, bool] = {}
    for rebalance, _end in daily:
        rets = [
            r for m in candidates
            if (r := sc._pre_rebalance_return(candle_map.get(m, []), rebalance)) is not None
        ]
        gate[rebalance] = bool(rets) and (sum(rets) / len(rets)) >= 0
    on = sum(gate.values())
    flips = sum(1 for a, b in zip(list(gate.values()), list(gate.values())[1:]) if a != b)
    print(f"gate: risk-on {on}/{len(gate)} rebalances, {flips} flips")

    def gated_signals(fmap, markets, rebalance_time, **kw):
        if not gate.get(rebalance_time, False):
            return pl.DataFrame(schema={"market": pl.String, "signal": pl.Float64})
        return signal_cross_section(fmap, markets, rebalance_time, **kw)

    frames = []
    for name, target_fn in [
        ("long-top-daily-gated", bis.long_top_targets),
        ("long-universe-daily-gated", bis.long_universe_targets),
    ]:
        sc.position_targets = target_fn
        sc.signal_cross_section = gated_signals
        frames.append(sc._run_targets(
            strategy=name, periods=daily, candidates=candidates,
            funding_map=funding_map, candle_map=candle_map,
            fees=fees, spreads=spreads, long_short=False,
        ))
        print(f"ran {name}: {frames[-1].height} rows")
    backtest = pl.concat(frames, how="diagonal_relaxed")
    backtest.write_parquet(REPORTS / "study3_scbis_gated_backtest.parquet")

    def pct(x):
        return "NA" if x is None else f"{100 * x:.3f}%"

    rows_out = []
    for (name,), group in backtest.partition_by("strategy", as_dict=True).items():
        s = bis.summarize_strategy(group, 365.0)
        rows_out.append((name, s))
        print(f"| {name} | {pct(s['net'])} [{pct(s['ci'][0])}, {pct(s['ci'][1])}] | "
              f"{s['sharpe']:.3f} [{s['sharpe_ci'][0]:.3f}, {s['sharpe_ci'][1]:.3f}] | "
              f"{pct(s['funding'])} | {pct(s['price'])} | {pct(s['cost'])} | {pct(s['max_dd'])} |")

    # paired gated-top vs gated-universe alpha
    top_p = rows_out[[i for i, (n, _) in enumerate(rows_out) if n == "long-top-daily-gated"][0]][1]["periods"]
    uni_p = rows_out[[i for i, (n, _) in enumerate(rows_out) if n == "long-universe-daily-gated"][0]][1]["periods"]
    paired = top_p.join(
        uni_p.select("rebalance_time", pl.col("net_pnl").alias("net_uni")),
        on="rebalance_time", how="inner",
    ).with_columns((pl.col("net_pnl") - pl.col("net_uni")).alias("diff"))
    alpha_ci = cluster_bootstrap_panel_statistic(
        paired.drop("net_pnl").rename({"diff": "net_pnl"}),
        statistic=lambda d: float(d["net_pnl"].sum()), **bis.BOOT,
    )
    print(f"gated selection alpha: {pct(float(paired['diff'].sum()))} "
          f"CI [{pct(alpha_ci.ci_low)}, {pct(alpha_ci.ci_high)}]")

    # monthly for gated top
    monthly = (
        top_p.with_columns(pl.col("rebalance_time").dt.strftime("%Y-%m").alias("month"))
        .group_by("month").agg(pl.col("net_pnl").sum()).sort("month")
    )
    for r in monthly.iter_rows(named=True):
        print(f"  {r['month']}  {pct(r['net_pnl'])}")


if __name__ == "__main__":
    main()
