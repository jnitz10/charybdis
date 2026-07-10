"""Run Study-3 S-C cross-sectional carry backtests from on-disk inputs only."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import math
from pathlib import Path
from statistics import median

import polars as pl

from charybdis.loaders import parse_flat_file_key, scan_quotes, scan_report_parquet
from charybdis.markout import cluster_bootstrap_panel_statistic
from charybdis.study3_carry import (
    funding_window,
    position_targets,
    signal_cross_section,
    trailing_hedge_beta,
    turnover_cost,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
BACKTEST_PATH = REPORTS / "study3_sc_backtest.parquet"
SUMMARY_PATH = REPORTS / "study3_sc_summary.parquet"
DOC_PATH = ROOT / "docs/reports/study3_carry_backtest_2026-07-10.md"
CUTOFF = datetime(2026, 6, 18)
ALLOWED_COVERAGE = {"complete", "candle_truncated", "funding_truncated"}
HEDGE_MARKETS = ["xyz:SMH", "xyz:KR200", "xyz:EWY"]
MEASURED_CANDIDATES = {
    "xyz:SP500", "km:US500", "flx:USA500", "cash:USA500",
    "km:USTECH", "xyz:XYZ100", "flx:USA100", "km:SMALL2000",
    "xyz:SKHX", "xyz:SMSN", "xyz:EWY", "xyz:KR200", "xyz:SMH",
}
STUDY1_MARKETS = {
    "xyz:SP500", "km:US500", "flx:USA500", "cash:USA500",
    "km:USTECH", "xyz:XYZ100", "flx:USA100", "km:SMALL2000",
}


def _collect(lazy: pl.LazyFrame) -> pl.DataFrame:
    return lazy.collect(engine="streaming")


def load_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    universe = _collect(scan_report_parquet(
        REPORTS / "study3_universe.parquet",
        columns=["market", "coverage_status", "passes_liquidity_floor", "liquidity_floor_usd"],
    ))
    selected = universe.filter(
        pl.col("passes_liquidity_floor")
        & pl.col("coverage_status").is_in(sorted(ALLOWED_COVERAGE))
    )["market"].to_list()
    needed = sorted(set(selected) | {"xyz:SKHX", *HEDGE_MARKETS})
    funding = _collect(scan_report_parquet(
        REPORTS / "study3_funding_all.parquet",
        columns=["market", "time_exchange", "funding_rate"],
    ).filter(pl.col("market").is_in(needed)))
    candles = _collect(scan_report_parquet(
        REPORTS / "study3_candles_1h.parquet",
        columns=["market", "open_time_ms", "close_time_ms", "time_open", "close"],
    ).filter(pl.col("market").is_in(needed))).with_columns(
        pl.from_epoch("close_time_ms", time_unit="ms").alias("time_close")
    )
    fees = _collect(scan_report_parquet(
        REPORTS / "study3_fee_table.parquet",
        columns=["dex", "effective_maker_bps", "effective_taker_bps", "source"],
    ))
    anatomy = _collect(scan_report_parquet(
        REPORTS / "forced_flow_event_anatomy_proxy.parquet",
        columns=["market", "direction", "overshoot_bps", "anatomy_covered"],
    ))
    return universe, funding, candles, fees, anatomy


def measured_half_spreads() -> dict[str, float]:
    """Median executable half-spread from pre-cutoff L4 quote books."""

    paths: dict[str, list[Path]] = defaultdict(list)
    for path in DATA.glob("T-QUOTES/D-*/E-HYPERLIQUIDL4/*.csv.gz"):
        key = parse_flat_file_key(path)
        market = key.coin.lower().split(":", 1)[0] + ":" + key.coin.split(":", 1)[1]
        partition_time = datetime.strptime(key.partition, "%Y%m%d%H")
        if market in MEASURED_CANDIDATES and partition_time < CUTOFF:
            paths[market].append(path)
    result: dict[str, float] = {}
    for market in sorted(MEASURED_CANDIDATES):
        market_paths = paths.get(market, [])
        if not market_paths:
            continue
        # Each hourly file is a pre-cutoff observed segment. Reducing one file
        # at a time bounds memory and makes the final value the exact median of
        # hourly-segment medians (not a row-weighted full-history median).
        segment_medians: list[float] = []
        for path in market_paths:
            spread = (
                scan_quotes(path, columns=["ask_px", "bid_px"])
                .filter(
                    pl.col("ask_px").is_finite() & pl.col("bid_px").is_finite()
                    & (pl.col("ask_px") > 0) & (pl.col("bid_px") > 0)
                    & (pl.col("ask_px") >= pl.col("bid_px"))
                )
                .select(
                    (((pl.col("ask_px") - pl.col("bid_px")) / ((pl.col("ask_px") + pl.col("bid_px")) / 2)) * 10_000 / 2)
                    .alias("half_spread_bps")
                )
                .select(pl.col("half_spread_bps").median())
            )
            value = _collect(spread)["half_spread_bps"][0]
            if value is not None and math.isfinite(float(value)):
                segment_medians.append(float(value))
        if segment_medians:
            result[market] = median(segment_medians)
    return result


def _market_class(market: str) -> str:
    return "study1_index_observed" if market in STUDY1_MARKETS else "hip3_fallback"


def build_spread_table(markets: list[str], measured: dict[str, float]) -> pl.DataFrame:
    study1_values = [measured[market] for market in STUDY1_MARKETS if market in measured]
    if len(study1_values) != len(STUDY1_MARKETS):
        missing = sorted(STUDY1_MARKETS - measured.keys())
        raise ValueError(f"missing pre-cutoff Study-1 spread books: {missing}")
    study1_class_median = median(study1_values)
    rows = []
    for market in sorted(set(markets) | {"xyz:SKHX", *HEDGE_MARKETS}):
        if market in measured:
            half_spread = measured[market]
            source = "measured_pre_2026-06-18_l4_books"
        else:
            half_spread = 2.0 * study1_class_median
            source = "assumed_2x_study1_class_median"
        rows.append({
            "market": market,
            "market_class": _market_class(market),
            "half_spread_bps": half_spread,
            "spread_source": source,
        })
    return pl.DataFrame(rows)


def _maps(funding: pl.DataFrame, candles: pl.DataFrame):
    funding_map = {
        market: sorted(zip(group["time_exchange"].to_list(), group["funding_rate"].to_list()))
        for (market,), group in funding.partition_by("market", as_dict=True).items()
    }
    candle_map = {
        market: sorted(zip(group["time_open"].to_list(), group["time_close"].to_list(), group["close"].to_list()))
        for (market,), group in candles.partition_by("market", as_dict=True).items()
    }
    return funding_map, candle_map


def _schedule(start: datetime, stop: datetime, hours: int) -> list[tuple[datetime, datetime]]:
    first = start.replace(minute=0, second=0, microsecond=0)
    if first < start:
        first += timedelta(hours=1)
    while first.hour % hours:
        first += timedelta(hours=1)
    result = []
    while first + timedelta(hours=hours) <= stop:
        result.append((first, first + timedelta(hours=hours)))
        first += timedelta(hours=hours)
    return result


def _cluster_key(market: str, timestamp: datetime) -> str:
    block = timestamp.replace(hour=(timestamp.hour // 6) * 6, minute=0, second=0, microsecond=0)
    return f"{market}|{block.isoformat()}"


def _price_known_at(rows, timestamp: datetime) -> bool:
    known = [row for row in rows if row[1] <= timestamp]
    return bool(known) and timestamp - known[-1][1] <= timedelta(seconds=1)


def _price_blocks(rows, rebalance: datetime, end: datetime):
    eligible = [row for row in rows if row[0] > rebalance and row[1] <= end]
    if not eligible:
        return [], False
    entry = float(eligible[0][2])
    prior = entry
    blocks = []
    complete = end - eligible[-1][1] <= timedelta(seconds=1)
    actual_stop = end if complete else eligible[-1][1]
    block_start = rebalance
    while block_start < actual_stop:
        hours_to_boundary = 6 - (block_start.hour % 6)
        block_end = min(block_start + timedelta(hours=hours_to_boundary), actual_stop)
        within = [row for row in eligible if row[1] <= block_end]
        if within:
            last = float(within[-1][2])
            blocks.append((block_start, block_end, (last - prior) / entry))
            prior = last
        block_start = block_end
    return blocks, complete


def _pre_rebalance_return(rows, rebalance: datetime, lookback: timedelta = timedelta(days=7)) -> float | None:
    """Close-to-close trailing return fully known at rebalance."""

    eligible = [row for row in rows if rebalance - lookback < row[1] <= rebalance]
    if len(eligible) < 2:
        return None
    return float(eligible[-1][2]) / float(eligible[0][2]) - 1.0


def _run_targets(
    *, strategy: str, periods: list[tuple[datetime, datetime]], candidates: list[str],
    funding_map, candle_map, fees: pl.DataFrame, spreads: pl.DataFrame,
    long_short: bool, candles: pl.DataFrame | None = None, hedged: bool | None = None,
) -> pl.DataFrame:
    spread_rows = {row["market"]: row for row in spreads.iter_rows(named=True)}
    previous: dict[str, float] = {}
    records: list[dict[str, object]] = []
    for rebalance, end in periods:
        known_markets = [market for market in candidates if _price_known_at(candle_map.get(market, []), rebalance)]
        if hedged is None:
            signals = signal_cross_section(funding_map, sorted(known_markets), rebalance)
            targets = position_targets(signals, long_short=long_short) if signals.height >= 2 else {}
            signal_lookup = dict(signals.select("market", "signal").iter_rows())
        else:
            required = ["xyz:SKHX", *HEDGE_MARKETS]
            targets = {}
            signal_lookup = {}
            if hedged:
                if all(market in known_markets for market in required):
                    assert candles is not None
                    beta = trailing_hedge_beta(
                        candles, rebalance, "xyz:SKHX", HEDGE_MARKETS,
                        min_observations=168,
                    )
                    if beta is not None:
                        targets = {"xyz:SKHX": -1.0, **{m: beta / len(HEDGE_MARKETS) for m in HEDGE_MARKETS}}
                        signal_lookup = {m: beta for m in targets}
            elif "xyz:SKHX" in known_markets:
                targets = {"xyz:SKHX": -1.0}
        touched = sorted(set(previous) | set(targets))
        surviving: dict[str, float] = {}
        for market in touched:
            position = targets.get(market, 0.0)
            prior = previous.get(market, 0.0)
            turnover = position - prior
            spread_row = spread_rows[market]
            pre_rebalance_return = _pre_rebalance_return(candle_map.get(market, []), rebalance) if position < 0 else None
            price_loss_path = (
                "unknown_pre_history" if pre_rebalance_return is None else
                "pre_rebalance_drop" if pre_rebalance_return < 0 else
                "forward_squeeze"
            ) if position < 0 else None
            entry_cost = turnover_cost(
                market, turnover=turnover,
                half_spread_bps=float(spread_row["half_spread_bps"]), fee_table=fees,
            )
            blocks, complete = _price_blocks(candle_map.get(market, []), rebalance, end) if position else ([], True)
            if position and not blocks:
                blocks = [(rebalance, rebalance, 0.0)]
                complete = False
            if not position:
                blocks = [(rebalance, rebalance, 0.0)]
            for block_index, (block_start, block_end, price_return) in enumerate(blocks):
                exit_cost = 0.0
                if position and not complete and block_index == len(blocks) - 1:
                    exit_cost = turnover_cost(
                        market, turnover=-position,
                        half_spread_bps=float(spread_row["half_spread_bps"]), fee_table=fees,
                    )
                cost = (entry_cost if block_index == 0 else 0.0) + exit_cost
                funding_pnl = -position * sum(funding_window(funding_map.get(market, []), block_start, block_end))
                price_pnl = position * price_return
                records.append({
                    "strategy": strategy, "rebalance_time": rebalance, "hold_end_time": end,
                    "block_start": block_start, "block_end": block_end,
                    "market": market, "position": position, "prior_position": prior,
                    "turnover": turnover if block_index == 0 else 0.0, "signal": signal_lookup.get(market),
                    "funding_pnl": funding_pnl, "price_pnl": price_pnl, "cost_pnl": -cost,
                    "net_pnl": funding_pnl + price_pnl - cost,
                    "pre_rebalance_return": pre_rebalance_return,
                    "price_loss_path": price_loss_path,
                    "fee_bps": float(fees.filter(pl.col("dex") == market.split(":", 1)[0])["effective_taker_bps"][0]),
                    "half_spread_bps": float(spread_row["half_spread_bps"]),
                    "spread_source": spread_row["spread_source"], "market_class": spread_row["market_class"],
                    "cluster_key": _cluster_key(market, block_start),
                    "period_hours": (block_end - block_start).total_seconds() / 3600,
                    "block_offset_hours": (block_start - rebalance).total_seconds() / 3600,
                    "block_start_hour_utc": block_start.hour,
                    "coverage_complete_for_hold": complete,
                })
            if position and complete:
                surviving[market] = position
        previous = surviving
    return pl.DataFrame(records)


def run_backtests(
    universe: pl.DataFrame, funding: pl.DataFrame, candles: pl.DataFrame,
    fees: pl.DataFrame, spreads: pl.DataFrame, *, measured_only: bool = False,
) -> pl.DataFrame:
    candidates = universe.filter(
        pl.col("passes_liquidity_floor") & pl.col("coverage_status").is_in(sorted(ALLOWED_COVERAGE))
    )["market"].to_list()
    if measured_only:
        measured_names = set(spreads.filter(pl.col("spread_source").str.starts_with("measured"))["market"].to_list())
        candidates = [market for market in candidates if market in measured_names]
    funding_map, candle_map = _maps(funding, candles)
    start = min(min(rows)[0] for market, rows in funding_map.items() if market in candidates) + timedelta(days=7)
    stop = max(row[1] for rows in candle_map.values() for row in rows)
    daily = _schedule(start, stop, 24)
    eight = _schedule(start, stop, 8)
    frames = [
        _run_targets(strategy="short-only-daily", periods=daily, candidates=candidates, funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=False),
        _run_targets(strategy="short-only-8h", periods=eight, candidates=candidates, funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=False),
        _run_targets(strategy="long-short-daily", periods=daily, candidates=candidates, funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=True),
        _run_targets(strategy="long-short-8h", periods=eight, candidates=candidates, funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=True),
        _run_targets(strategy="single-name-hedged", periods=daily, candidates=["xyz:SKHX", *HEDGE_MARKETS], funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=False, candles=candles, hedged=True),
        _run_targets(strategy="single-name-unhedged", periods=daily, candidates=["xyz:SKHX", *HEDGE_MARKETS], funding_map=funding_map, candle_map=candle_map, fees=fees, spreads=spreads, long_short=False, candles=candles, hedged=False),
    ]
    return pl.concat([frame for frame in frames if frame.height], how="diagonal_relaxed")


def _sharpe(frame: pl.DataFrame, annualization: float) -> float:
    periods = frame.group_by("rebalance_time").agg(pl.col("net_pnl").sum()).sort("rebalance_time")
    if periods.height < 2:
        return float("nan")
    std = periods["net_pnl"].std(ddof=1)
    return float(periods["net_pnl"].mean()) / float(std) * math.sqrt(annualization) if std else float("nan")


def summarize(backtest: pl.DataFrame, sensitivity: pl.DataFrame) -> pl.DataFrame:
    sensitivity_returns = {
        strategy: float(group["net_pnl"].sum())
        for (strategy,), group in sensitivity.partition_by("strategy", as_dict=True).items()
    }
    rows = []
    for (strategy,), group in backtest.partition_by("strategy", as_dict=True).items():
        annualization = 1095.0 if strategy.endswith("8h") else 365.0
        periods = group.group_by("rebalance_time").agg(
            pl.col("hold_end_time").first(),
            pl.col("funding_pnl").sum(), pl.col("price_pnl").sum(),
            pl.col("cost_pnl").sum(), pl.col("net_pnl").sum(),
        ).sort("rebalance_time").with_columns(
            pl.col("rebalance_time").cast(pl.String).alias("cluster_key"),
            pl.col("rebalance_time").dt.hour().alias("rebalance_hour_utc"),
            ((pl.col("hold_end_time") - pl.col("rebalance_time")).dt.total_seconds() / 3600).alias("hold_hours"),
        )
        bootstrap_args = {
            "strata_cols": ["rebalance_hour_utc", "hold_hours"],
            "destination_cols": ["rebalance_time", "hold_end_time"],
        }
        return_ci = cluster_bootstrap_panel_statistic(
            periods, statistic=lambda draw: float(draw["net_pnl"].sum()), **bootstrap_args,
        )
        sharpe_ci = cluster_bootstrap_panel_statistic(
            periods, statistic=lambda draw, a=annualization: _sharpe(draw, a), **bootstrap_args,
        )
        cumulative = periods["net_pnl"].cum_sum().to_list()
        running_peak = 0.0
        max_drawdown = 0.0
        for value in cumulative:
            running_peak = max(running_peak, float(value))
            max_drawdown = min(max_drawdown, float(value) - running_peak)
        worst = periods.sort("price_pnl").row(0, named=True)
        short_rows = group.filter(pl.col("position") < 0).sort("price_pnl")
        worst_short = short_rows.row(0, named=True) if short_rows.height else None
        price_losses = group.filter((pl.col("position") < 0) & (pl.col("price_pnl") < 0))
        losses_by_path = {
            path: -float(path_rows["price_pnl"].sum())
            for (path,), path_rows in price_losses.partition_by("price_loss_path", as_dict=True).items()
        }
        pre_drop_loss = losses_by_path.get("pre_rebalance_drop", 0.0)
        forward_squeeze_loss = losses_by_path.get("forward_squeeze", 0.0)
        unknown_pre_history_loss = losses_by_path.get("unknown_pre_history", 0.0)
        classified_loss = pre_drop_loss + forward_squeeze_loss
        lost = (
            group.filter(pl.col("position") != 0)
            .group_by("rebalance_time", "market")
            .agg(
                pl.col("period_hours").sum().alias("observed_hours"),
                ((pl.col("hold_end_time").first() - pl.col("rebalance_time").first()).dt.total_seconds() / 3600).alias("scheduled_hours"),
                pl.col("coverage_complete_for_hold").all().alias("complete"),
            )
            .filter(~pl.col("complete"))
            .select(((pl.col("scheduled_hours") - pl.col("observed_hours")).clip(lower_bound=0).sum() / 24).alias("lost"))["lost"][0]
        )
        rows.append({
            "strategy": strategy, "net_total_return": float(group["net_pnl"].sum()),
            "return_ci_low": return_ci.ci_low, "return_ci_high": return_ci.ci_high,
            "return_ci_includes_zero": bool(return_ci.ci_low <= 0 <= return_ci.ci_high),
            "sharpe": sharpe_ci.point_estimate, "sharpe_ci_low": sharpe_ci.ci_low,
            "sharpe_ci_high": sharpe_ci.ci_high, "funding_pnl": float(group["funding_pnl"].sum()),
            "price_pnl": float(group["price_pnl"].sum()), "cost_pnl": float(group["cost_pnl"].sum()),
            "max_drawdown": max_drawdown, "worst_single_squeeze_price_pnl": float(worst["price_pnl"]),
            "worst_single_squeeze_time": worst["rebalance_time"],
            "worst_short_market_price_pnl": None if worst_short is None else float(worst_short["price_pnl"]),
            "worst_short_market": None if worst_short is None else worst_short["market"],
            "worst_short_market_time": None if worst_short is None else worst_short["block_start"],
            "rebalance_count": periods.height,
            "markets_entered": group.filter(pl.col("position") != 0)["market"].n_unique(),
            "market_days_entered": float(group.filter(pl.col("position") != 0)["period_hours"].sum()) / 24,
            "market_days_lost_to_truncation": float(lost or 0.0),
            "bootstrap_G": return_ci.G, "sensitivity_measured_only_return": sensitivity_returns.get(strategy),
            "pre_drop_price_loss": pre_drop_loss,
            "forward_squeeze_price_loss": forward_squeeze_loss,
            "unknown_pre_history_price_loss": unknown_pre_history_loss,
            "pre_drop_loss_fraction": pre_drop_loss / classified_loss if classified_loss else None,
            "forward_squeeze_loss_fraction": forward_squeeze_loss / classified_loss if classified_loss else None,
            "cumulative_min": min([0.0, *map(float, cumulative)]),
            "cumulative_max": max([0.0, *map(float, cumulative)]),
        })
    return pl.DataFrame(rows).sort("strategy")


def _pct(value: float | None) -> str:
    return "NA" if value is None else f"{100 * value:.3f}%"


def write_report(
    summary: pl.DataFrame, backtest: pl.DataFrame, universe: pl.DataFrame,
    spreads: pl.DataFrame, anatomy: pl.DataFrame,
) -> None:
    measured = spreads.filter(pl.col("spread_source").str.starts_with("measured"))["market"].to_list()
    assumed = spreads.filter(pl.col("spread_source").str.starts_with("assumed"))["market"].to_list()
    selected = universe.filter(pl.col("passes_liquidity_floor") & pl.col("coverage_status").is_in(sorted(ALLOWED_COVERAGE)))
    truncated_lost = float(summary["market_days_lost_to_truncation"].sum())
    tails = anatomy.filter(
        pl.col("market").is_in(["SKHX", "SMSN"]) & (pl.col("direction") == "BUY")
        & pl.col("anatomy_covered") & pl.col("overshoot_bps").is_not_null()
    ).group_by("market").agg(pl.len().alias("n"), pl.col("overshoot_bps").quantile(0.95).alias("p95"), pl.col("overshoot_bps").max().alias("max"))
    lines = [
        "# Study 3 S-C: cross-sectional carry backtest", "",
        "Research-only measurement from on-disk T1/T2 inputs. Values are reported without an operator adjudication.", "",
        "## Portfolio decomposition and uncertainty", "",
        "Additive cross-sectional returns use gross-one portfolios (long-short is 0.5 per side). The hedged strategy uses a unit SKHX short plus its trailing-beta hedge basket, so its gross exposure varies with beta and is not normalized to gross one. Immediate scheduled rebalances use effective taker fees from `study3_fee_table.parquet`; initial entries and every transition are charged, while no unscheduled terminal liquidation is added. Intervals use a 2,000-draw, seed-0, 95% bootstrap of scalar portfolio holding-period returns after all markets, legs, and UTC-six-hour sub-blocks are netted within each rebalance period; resampling therefore preserves same-period cross-market dependence.", "",
        "| Strategy | Net total return (95% CI) | Sharpe (95% CI) | Funding | Price | Cost | Max drawdown |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {_pct(row['net_total_return'])} [{_pct(row['return_ci_low'])}, {_pct(row['return_ci_high'])}] | {row['sharpe']:.3f} [{row['sharpe_ci_low']:.3f}, {row['sharpe_ci_high']:.3f}] | {_pct(row['funding_pnl'])} | {_pct(row['price_pnl'])} | {_pct(row['cost_pnl'])} | {_pct(row['max_drawdown'])} |")
    hedged = summary.filter(pl.col("strategy") == "single-name-hedged").row(0, named=True)
    lines += [
        "", f"The hedged {_pct(hedged['net_total_return'])} result is price-residual dominated: funding {_pct(hedged['funding_pnl'])}, price {_pct(hedged['price_pnl'])}, and cost {_pct(hedged['cost_pnl'])}.",
    ]
    lines += ["", "## Cumulative curves, numerical description", "", "| Strategy | Rebalances | End | Minimum | Maximum | Worst price-PnL period (time) |", "|---|---:|---:|---:|---:|---:|"]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {row['rebalance_count']} | {_pct(row['net_total_return'])} | {_pct(row['cumulative_min'])} | {_pct(row['cumulative_max'])} | {_pct(row['worst_single_squeeze_price_pnl'])} ({row['worst_single_squeeze_time']}) |")
    lines += ["", "Worst individual short-leg price contributions (unoffset by other legs):", "", "| Strategy | Market | UTC block | Price PnL |", "|---|---|---:|---:|"]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {row['worst_short_market']} | {row['worst_short_market_time']} | {_pct(row['worst_short_market_price_pnl'])} |")
    lines += ["", "## Falsification F-C numbers", "", "| Strategy | Return CI includes 0 | Price PnL | −Funding PnL | Price <= −Funding |", "|---|:---:|---:|---:|:---:|"]
    for row in summary.iter_rows(named=True):
        comparison = row["price_pnl"] <= -row["funding_pnl"]
        lines.append(f"| {row['strategy']} | {row['return_ci_includes_zero']} | {_pct(row['price_pnl'])} | {_pct(-row['funding_pnl'])} | {comparison} |")
    lines += [
        "", "## Reverse-causation diagnostic", "",
        "Negative short-leg price PnL is split by the name's close-to-close return over the seven days known at rebalance. `pre_rebalance_drop` means that return was negative; `forward_squeeze` means it was non-negative. Fractions use classified loss only; unknown-history loss is shown separately.", "",
        "| Strategy | Pre-drop loss | Forward-squeeze loss | Pre-drop fraction | Forward-squeeze fraction | Unknown-history loss |", "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {_pct(row['pre_drop_price_loss'])} | {_pct(row['forward_squeeze_price_loss'])} | {_pct(row['pre_drop_loss_fraction'])} | {_pct(row['forward_squeeze_loss_fraction'])} | {_pct(row['unknown_pre_history_price_loss'])} |")
    lines += [
        "", "Interpretation A is that funding compensates forward squeeze risk; its diagnostic bucket is `forward_squeeze`. Interpretation B is reverse causation: the trailing funding signal selects names that had already fallen and subsequently recovered; its diagnostic bucket is `pre_rebalance_drop`. No verdict is rendered between these interpretations.",
        "", "The pre-registered +340% APR prior is retained as a prior only; the split above prevents treating the aggregate loss as evidence that the market prices funding correctly.",
        "", "## Cost sensitivity and spread provenance", "",
        "| Strategy | All eligible markets | Measured-spread markets only |", "|---|---:|---:|",
    ]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {_pct(row['net_total_return'])} | {_pct(row['sensitivity_measured_only_return'])} |")
    lines += [
        "", f"Measured pre-cutoff L4 half-spreads ({len(measured)}): {', '.join(measured)}.",
        "", f"Assumed half-spreads ({len(assumed)}), each explicitly set to 2× the median of the eight Study-1 markets' pre-cutoff hourly-segment median spreads: {', '.join(assumed)}.",
        "", "## Coverage and timing", "",
        f"The frozen filter is `passes_liquidity_floor == true` ($1,000,000/day) plus coverage status in {sorted(ALLOWED_COVERAGE)}; it selects {selected.height} markets and ignores `carry_relevant`. Coverage counts: " + ", ".join(f"{r['coverage_status']}={r['len']}" for r in selected.group_by('coverage_status').len().iter_rows(named=True)) + ".",
        f"Market-days lost specifically to candle truncation: {truncated_lost:.3f}. No stale close is forward-filled. Signals use raw settlements in (t−7d,t], requiring 168 observations; funding PnL uses settlements in (t,end]. Returns use actual close timestamps from candles whose opens are strictly after rebalance, excluding the candle at/containing rebalance. This creates a small 1–2-settlement asymmetry between the funding window and the later price entry. The final open positions incur no terminal-liquidation cost. Both mechanics leave reported net returns slightly higher than an exactly aligned, fully liquidated implementation. Hedge beta is an intercept OLS slope on synchronized hourly log returns in the trailing 30 days known by rebalance, with at least 168 observations; hedged and unhedged variants rebalance daily.",
        "", "| Strategy | Markets entered | Market-days entered | Market-days lost to truncation |", "|---|---:|---:|---:|",
    ]
    for row in summary.iter_rows(named=True):
        lines.append(f"| {row['strategy']} | {row['markets_entered']} | {row['market_days_entered']:.3f} | {row['market_days_lost_to_truncation']:.3f} |")
    lines += [
        "", "## Worst-squeeze intra-hour tail and named limitation", "",
    ]
    for row in tails.sort("market").iter_rows(named=True):
        lines.append(f"Study-2 BUY-event anatomy for {row['market']}: n={row['n']}, p95 overshoot={row['p95']:.3f} bps, maximum={row['max']:.3f} bps.")
    lines += [
        "", "Named limitation — candles miss sub-hour excursions: the hourly backtest cannot observe these intra-hour squeeze paths, so the Study-2 overshoot anatomy is linked explicitly rather than folded into hourly PnL.",
        "", "## Provenance", "",
        "Inputs: `study3_universe.parquet`, projected `study3_funding_all.parquet` settlement columns, projected `study3_candles_1h.parquet` close columns, `study3_fee_table.parquet`, pre-2026-06-18 L4 quote books, and `forced_flow_event_anatomy_proxy.parquet`. Outputs: `study3_sc_backtest.parquet` and `study3_sc_summary.parquet`. No network calls, orders, wallets, keys, or paid data were used; cumulative spend remains $116.92.",
    ]
    DOC_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    universe, funding, candles, fees, anatomy = load_inputs()
    selected = universe.filter(pl.col("passes_liquidity_floor") & pl.col("coverage_status").is_in(sorted(ALLOWED_COVERAGE)))["market"].to_list()
    measured = measured_half_spreads()
    spreads = build_spread_table(selected, measured)
    backtest = run_backtests(universe, funding, candles, fees, spreads)
    sensitivity = run_backtests(universe, funding, candles, fees, spreads, measured_only=True)
    summary = summarize(backtest, sensitivity)
    backtest.write_parquet(BACKTEST_PATH)
    summary.write_parquet(SUMMARY_PATH)
    write_report(summary, backtest, universe, spreads, anatomy)
    print(f"universe={len(selected)} backtest_rows={backtest.height} summaries={summary.height}")
    print(f"measured={len(measured)} assumed={spreads.filter(pl.col('spread_source').str.starts_with('assumed')).height}")


if __name__ == "__main__":
    main()
