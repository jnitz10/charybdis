"""Run Study 3 S-D using free cached REST candles and on-disk L4 data."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import polars as pl

from charybdis.hl_rest import HyperliquidInfo
from charybdis.loaders import parse_flat_file_key, scan_oracle_prices, scan_trades
from charybdis.markout import BootstrapCI, cluster_bootstrap_statistic
from charybdis.study3_clock import (
    BRACKET_MINUTES,
    aggregate_l4_trades_to_1m,
    estimate_harvest_calls,
    harvest_1m_candles,
    inside_bracket_return,
    select_candle_cache_file,
    settlement_control_window,
    wallet_window_events,
)


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"
CANDLE_CACHE = ROOT / "data" / "study3_sd_1m"
FUNDING_PATH = REPORTS / "study3_funding_all.parquet"
BRACKET_PATH = REPORTS / "study3_sd_brackets.parquet"
WALLET_PATH = REPORTS / "study3_sd_wallet_flow.parquet"
REPORT_PATH = ROOT / "docs" / "reports" / "study3_funding_clock_2026-07-10.md"

MARKETS = (
    "xyz:KIOXIA", "xyz:BIRD", "xyz:BOT", "xyz:SKHX", "xyz:SOFTBANK",
    "xyz:HYUNDAI", "xyz:SMSN", "xyz:KR200", "xyz:PURRDAT", "xyz:MINIMAX",
)
L4_MARKETS = ("xyz:SKHX", "xyz:SMSN")
CANDLE_ONLY_MARKETS = tuple(market for market in MARKETS if market not in L4_MARKETS)
START = datetime(2026, 2, 19)
END = datetime(2026, 7, 10, 20)


def _cluster(at: datetime, market: str) -> str:
    return f"{market}|{at:%Y-%m-%d}|{(at.hour // 6) * 6:02d}"


def _mean(frame: pl.DataFrame, column: str) -> float:
    return float(frame[column].mean())


def _ci(frame: pl.DataFrame, column: str) -> BootstrapCI:
    return cluster_bootstrap_statistic(
        frame.select("cluster_key", column).drop_nulls(),
        statistic=lambda sampled: _mean(sampled, column),
        n_resamples=2_000,
        seed=0,
        min_clusters=5,
    )


def _funding() -> pl.DataFrame:
    return (
        pl.scan_parquet(FUNDING_PATH)
        .select("market", "time_exchange", "funding_rate")
        .filter(pl.col("market").is_in(MARKETS))
        .with_columns(
            pl.col("time_exchange").dt.truncate("1h").alias("settlement_time"),
            pl.col("funding_rate").abs().alias("funding_abs"),
        )
        .sort(["market", "time_exchange"])
        .unique(["market", "settlement_time"], keep="last")
        .collect()
        .with_columns(
            pl.when(pl.col("funding_rate") > 0).then(pl.lit("positive"))
            .when(pl.col("funding_rate") < 0).then(pl.lit("negative"))
            .otherwise(pl.lit("zero")).alias("funding_sign"),
            (((pl.col("funding_abs").rank("ordinal") - 1) * 10 / pl.len()).floor() + 1)
            .cast(pl.Int8).clip(1, 10).alias("funding_size_decile"),
        )
    )


def _observations_from_bars(
    funding: pl.DataFrame,
    market: str,
    bars: pl.DataFrame,
    coverage_group: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    bars = bars.filter((pl.col("open") > 0) & (pl.col("close") > 0)).sort("time_close")
    times = bars["time_close"].to_list()
    opens = bars["open"].to_list()
    closes = bars["close"].to_list()
    market_funding = funding.filter(pl.col("market") == market)
    for item in market_funding.iter_rows(named=True):
        at = item["settlement_time"]
        control = at + timedelta(minutes=30)
        for bracket in BRACKET_MINUTES:
            width = timedelta(minutes=abs(bracket))
            if bracket < 0:
                event_start, event_end = at - width, at
            else:
                event_start, event_end = at, at + width
            baseline_window = settlement_control_window(at, bracket)
            event_return, event_n = inside_bracket_return(
                times, opens, closes, event_start, event_end
            )
            base_return, base_n = inside_bracket_return(
                times, opens, closes, baseline_window.start, baseline_window.end
            )
            if event_return is None or base_return is None:
                continue
            rows.append({
                "market": market, "coverage_group": coverage_group,
                "settlement_time": at, "bracket_minutes": bracket,
                "funding_rate": item["funding_rate"], "funding_sign": item["funding_sign"],
                "funding_size_decile": item["funding_size_decile"],
                "event_return": event_return, "baseline_return": base_return,
                "event_candles": event_n, "baseline_candles": base_n,
                "baseline_anchor": control, "cluster_key": _cluster(at, market),
            })
    return rows


def _l4_trade_paths() -> dict[str, list[Path]]:
    paths = {market: [] for market in L4_MARKETS}
    for path in sorted((ROOT / "data" / "T-TRADES").rglob("*.csv.gz")):
        try:
            key = parse_flat_file_key(path)
        except ValueError:
            continue
        market = key.coin.lower().split(":", 1)[0] + ":" + key.coin.split(":", 1)[1]
        if market in paths and key.exchange_id == "HYPERLIQUIDL4":
            paths[market].append(path)
    return paths


def _l4_minute_bars(paths: list[Path]) -> tuple[pl.DataFrame, int]:
    parts: list[pl.DataFrame] = []
    skipped = 0
    for path in paths:
        try:
            trades = scan_trades(path, columns=["time_exchange", "price"]).collect(
                engine="streaming"
            )
        except (ValueError, OSError) as error:
            if "corrupt deflate" in str(error):
                skipped += 1
                continue
            raise
        if not trades.is_empty():
            parts.append(aggregate_l4_trades_to_1m(trades))
    if not parts:
        return pl.DataFrame(
            schema={"time_open": pl.Datetime("us"), "time_close": pl.Datetime("us"),
                    "open": pl.Float64, "close": pl.Float64}
        ), skipped
    bars = pl.concat(parts, how="vertical_relaxed").sort(["time_open", "time_close"])
    return (
        bars.with_columns(pl.col("time_open").dt.truncate("1m").alias("minute"))
        .group_by("minute", maintain_order=True)
        .agg(
            pl.col("time_open").first(), pl.col("time_close").last(),
            pl.col("open").first(), pl.col("close").last(),
        )
        .select("time_open", "time_close", "open", "close"),
        skipped,
    )


def _candle_observations(funding: pl.DataFrame) -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    l4_paths = _l4_trade_paths()
    for market in L4_MARKETS:
        bars, skipped = _l4_minute_bars(l4_paths[market])
        print(f"L4_1M market={market} files={len(l4_paths[market])} skipped={skipped} bars={bars.height}")
        rows.extend(_observations_from_bars(funding, market, bars, "SKHX/SMSN full-window L4"))
    for market in CANDLE_ONLY_MARKETS:
        path = select_candle_cache_file(
            sorted(CANDLE_CACHE.glob(f"{market.replace(':', '__')}_*_1m.parquet"))
        )
        if path is None:
            print(f"CANDLE_CACHE_MISSING market={market}; skipping")
            continue
        candles = (
            pl.read_parquet(path, columns=["close_time_ms", "open", "close"])
            .with_columns(pl.from_epoch("close_time_ms", time_unit="ms").alias("time_close"))
        )
        rows.extend(_observations_from_bars(funding, market, candles, "8-market 3.5-day candles"))
    return pl.DataFrame(rows)


def _separation(event: BootstrapCI, baseline: BootstrapCI) -> str:
    if event.low_cluster or baseline.low_cluster:
        return "INSUFFICIENT CLUSTERS"
    assert event.ci_low is not None and event.ci_high is not None
    assert baseline.ci_low is not None and baseline.ci_high is not None
    return (
        "SEPARATES"
        if event.ci_high < baseline.ci_low or baseline.ci_high < event.ci_low
        else "DOES NOT SEPARATE"
    )


def summarize_brackets(observations: pl.DataFrame) -> pl.DataFrame:
    groups: list[tuple[str, str, str, object, pl.DataFrame]] = []
    for coverage_group in observations["coverage_group"].unique(maintain_order=True):
        cohort = observations.filter(pl.col("coverage_group") == coverage_group)
        for bracket in BRACKET_MINUTES:
            subset = cohort.filter(pl.col("bracket_minutes") == bracket)
            groups.append((coverage_group, "all", "all", "all", subset))
            for sign in sorted(subset["funding_sign"].unique().to_list()):
                groups.append((coverage_group, "funding_sign", "funding_sign", sign, subset.filter(pl.col("funding_sign") == sign)))
            for decile in range(1, 11):
                groups.append((coverage_group, "funding_size_decile", "funding_size_decile", decile, subset.filter(pl.col("funding_size_decile") == decile)))
    output: list[dict[str, object]] = []
    for coverage_group, group_type, split_column, split_value, frame in groups:
        if frame.is_empty():
            continue
        event = _ci(frame, "event_return")
        baseline = _ci(frame, "baseline_return")
        output.append({
            "coverage_group": coverage_group,
            "bracket_minutes": int(frame["bracket_minutes"][0]),
            "group_type": group_type, "split_column": split_column,
            "split_value": str(split_value), "mean_return": event.point_estimate,
            "ci_low": event.ci_low, "ci_high": event.ci_high,
            "baseline_mean_return": baseline.point_estimate,
            "baseline_ci_low": baseline.ci_low, "baseline_ci_high": baseline.ci_high,
            "separation_status": _separation(event, baseline), "n": event.n,
            "cluster_count": event.G, "bootstrap_resamples": 2_000,
            "bootstrap_seed": 0, "bootstrap_min_clusters": 5,
        })
    return pl.DataFrame(output).sort(["coverage_group", "group_type", "split_value", "bracket_minutes"])


def _projected_parts(paths: Iterable[Path], loader, columns: list[str]) -> tuple[list[pl.DataFrame], int]:
    parts: list[pl.DataFrame] = []
    skipped = 0
    for path in paths:
        try:
            part = loader(path, columns=columns).collect(engine="streaming")
        except (ValueError, OSError) as error:
            if "user_taker" in str(error) or "corrupt deflate" in str(error):
                skipped += 1
                continue
            raise
        if not part.is_empty():
            parts.append(part)
    return parts, skipped


def wallet_flow() -> tuple[pl.DataFrame, dict[str, int]]:
    paths: list[tuple[Path, str]] = []
    for path in sorted((ROOT / "data" / "T-TRADES").rglob("*.csv.gz")):
        try:
            key = parse_flat_file_key(path)
        except ValueError:
            continue
        market = key.coin.lower().split(":", 1)[0] + ":" + key.coin.split(":", 1)[1]
        if market in {"xyz:SKHX", "xyz:SMSN"} and key.exchange_id == "HYPERLIQUIDL4":
            paths.append((path, market))
    parts: list[pl.DataFrame] = []
    skipped = 0
    for path, market in paths:
        loaded, count = _projected_parts(
            [path], scan_trades,
            ["time_exchange", "price", "base_amount", "taker_side", "user_taker"],
        )
        skipped += count
        if loaded:
            parts.append(loaded[0].with_columns(pl.lit(market).alias("market")))
    trades = pl.concat(parts, how="vertical_relaxed").filter(
        pl.col("user_taker").is_not_null() & (pl.col("user_taker") != "")
    )
    trades = trades.with_columns(
        pl.when(pl.col("taker_side") == "BUY").then(1.0).otherwise(-1.0)
        .mul(pl.col("base_amount") * pl.col("price")).alias("signed_notional"),
    )
    events, wallet = wallet_window_events(trades)
    events = events.with_columns(
        pl.struct("market", "settlement_time").map_elements(
            lambda x: _cluster(x["settlement_time"], x["market"]), return_dtype=pl.String
        ).alias("cluster_key")
    )
    rows: list[dict[str, object]] = []
    for label, frame in [("all", events), *[(m, events.filter(pl.col("market") == m)) for m in ("xyz:SKHX", "xyz:SMSN")]]:
        for metric in (
            "pre_signed_notional", "post_signed_notional", "short_open_close_share",
            "baseline_short_open_close_share", "short_open_close_share_difference",
        ):
            ci = _ci(frame, metric)
            rows.append({"market_group": label, "metric": metric, "estimate": ci.point_estimate,
                         "ci_low": ci.ci_low, "ci_high": ci.ci_high, "n": ci.n,
                         "cluster_count": ci.G, "bootstrap_resamples": 2_000,
                         "bootstrap_seed": 0, "bootstrap_min_clusters": 5})
    event_wallet = wallet.filter(pl.col("window_kind") == "settlement")
    baseline_wallet = wallet.filter(pl.col("window_kind") == "baseline")
    return pl.DataFrame(rows), {"files_found": len(paths), "files_skipped_without_wallet_or_corrupt": skipped,
                                "repeat_wallet_settlements": events.height,
                                "repeat_wallet_rows": event_wallet.height,
                                "baseline_repeat_wallet_rows": baseline_wallet.height,
                                "paired_share_settlements": events["short_open_close_share_difference"].drop_nulls().len()}


def premium_decay() -> tuple[pl.DataFrame, dict[str, int]]:
    parts: list[pl.DataFrame] = []
    files = sorted((ROOT / "data" / "T-HLORACLEPRICES").rglob("*S-SKHX.csv.gz")) + sorted((ROOT / "data" / "T-HLORACLEPRICES").rglob("*S-SMSN.csv.gz"))
    for path in files:
        part = scan_oracle_prices(path, columns=["time_exchange", "coin_id", "mark_px", "oracle_px"]).collect(engine="streaming")
        if not part.is_empty():
            parts.append(part)
    oracle = pl.concat(parts, how="vertical_relaxed").filter((pl.col("oracle_px") > 0) & (pl.col("mark_px") > 0)).with_columns(
        (pl.col("mark_px") / pl.col("oracle_px") - 1).alias("premium"),
        (pl.col("time_exchange").dt.minute().cast(pl.Int16) - 60).alias("minute_to_settlement"),
    ).filter(pl.col("minute_to_settlement").is_between(-10, -1))
    summary = oracle.group_by("coin_id", "minute_to_settlement").agg(
        pl.col("premium").mean().alias("mean_premium"), pl.col("premium").median().alias("median_premium"), pl.len().alias("n")
    ).sort(["coin_id", "minute_to_settlement"])
    return summary, {"oracle_files": len(files), "oracle_rows_last_10m": oracle.height}


def _pct(value: float | None) -> str:
    return "NA" if value is None else f"{value * 100:.4f}%"


def write_report(
    brackets: pl.DataFrame,
    coverage: pl.DataFrame,
    wallets: pl.DataFrame,
    premium: pl.DataFrame,
    wallet_meta: dict[str, int],
    premium_meta: dict[str, int],
    calls: tuple[int, int],
) -> None:
    lines = [
        "# Study 3 S-D — Funding-clock effects", "", "**Analysis date:** 2026-07-10. **Mode:** research only; no orders, wallets, keys, or paid calls. Total study spend remains $116.92.", "",
        "## Settlement brackets and F-D interval geometry", "",
        "Returns are log first-open to last-close returns across 1m bars whose last-trade or candle-close timestamps lie strictly inside each open bracket. This makes the ±1m brackets measurable without borrowing an outside bar. Negative brackets end at settlement and never use a post-settlement trade; positive brackets begin at settlement. The baseline is a plain same-market `t+30m` within-hour placebo with the same directional width. It shares hour-level shocks with the event and is verified not to overlap the ±10m windows around the current or adjacent hourly settlements. No Study-2 calendar-day matching machinery is run.", "",
        "F-D is reported separately for the two full-window L4-derived markets and the eight markets limited to the cached 3.5-day candles.", "",
    ]
    for cohort in ("SKHX/SMSN full-window L4", "8-market 3.5-day candles"):
        headline = brackets.filter(
            (pl.col("group_type") == "all") & (pl.col("coverage_group") == cohort)
        ).sort("bracket_minutes")
        lines += [f"### {cohort}", "", "| bracket | return (95% CI) | +30m baseline (95% CI) | F-D separation | n | clusters |", "|---:|---:|---:|---|---:|---:|"]
        for row in headline.iter_rows(named=True):
            lines.append(f"| {row['bracket_minutes']:+d}m | {_pct(row['mean_return'])} [{_pct(row['ci_low'])}, {_pct(row['ci_high'])}] | {_pct(row['baseline_mean_return'])} [{_pct(row['baseline_ci_low'])}, {_pct(row['baseline_ci_high'])}] | {row['separation_status']} | {row['n']} | {row['cluster_count']} |")
        lines.append("")
    lines += ["### Per-market bracket coverage", "", "| market | source/window | first settlement | last settlement | -10m | -5m | -1m | +1m | +5m | +10m |", "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for market in MARKETS:
        subset = coverage.filter(pl.col("market") == market).sort("bracket_minutes")
        if subset.is_empty():
            continue
        counts = {row["bracket_minutes"]: row["settlements"] for row in subset.iter_rows(named=True)}
        first = min(subset["first_settlement"])
        last = max(subset["last_settlement"])
        cohort = subset["coverage_group"][0]
        lines.append(f"| {market} | {cohort} | {first:%Y-%m-%d %H:%M} | {last:%Y-%m-%d %H:%M} | " + " | ".join(str(counts.get(bracket, 0)) for bracket in BRACKET_MINUTES) + " |")
    lines += ["", "Funding-sign and funding-size-decile splits, each with the same event/baseline CIs and separation status, are in `data/reports/study3_sd_brackets.parquet`.", "", "## Premium decay into settlement", ""]
    for coin in ("SKHX", "SMSN"):
        subset = premium.filter(pl.col("coin_id") == coin)
        if subset.is_empty():
            lines.append(f"- {coin}: no usable on-disk oracle observations.")
            continue
        first, last = subset.row(0, named=True), subset.row(-1, named=True)
        lines.append(f"- {coin}: mean mark/oracle premium moved from {_pct(first['mean_premium'])} at minute {first['minute_to_settlement']} to {_pct(last['mean_premium'])} at minute {last['minute_to_settlement']} (n={int(subset['n'].sum())} observations across these minute buckets).")
    lines += ["", f"Coverage: {premium_meta['oracle_files']} on-disk oracle files; {premium_meta['oracle_rows_last_10m']} observations in minutes -10..-1.", "", "## Repeat-wallet signed taker flow", "",
        "Negative signed notional is sell-taker flow (short-opening proxy); positive is buy-taker flow (short-closing proxy). A repeat wallet has at least two trades across its ±10m settlement window. This is a flow proxy, not a reconstructed position.", "",
        "| market | metric | estimate (95% CI) | n settlements | clusters |", "|---|---|---:|---:|---:|"]
    for row in wallets.iter_rows(named=True):
        value = row['estimate']
        is_share = "share" in row['metric']
        formatted = _pct(value) if is_share else f"${value:,.0f}"
        low = _pct(row['ci_low']) if is_share else f"${row['ci_low']:,.0f}"
        high = _pct(row['ci_high']) if is_share else f"${row['ci_high']:,.0f}"
        lines.append(f"| {row['market_group']} | {row['metric']} | {formatted} [{low}, {high}] | {row['n']} | {row['cluster_count']} |")
    lines += ["", "`baseline_short_open_close_share` applies the identical repeat-wallet rule around `t+30m`; `short_open_close_share_difference` is the paired settlement share minus that baseline. A difference interval spanning zero indicates no measured settlement-specific wallet pattern.", "", f"Coverage: {wallet_meta['files_found']} SKHX/SMSN L4 files found; {wallet_meta['files_skipped_without_wallet_or_corrupt']} skipped for absent `user_taker` or corruption; {wallet_meta['repeat_wallet_rows']} settlement-window and {wallet_meta['baseline_repeat_wallet_rows']} baseline-window repeat-wallet rows; {wallet_meta['paired_share_settlements']} paired market-settlements.", "", "## Coverage and prediction framing", "",
        f"The scoped set is `{', '.join(MARKETS)}`. It is the top ten by share of funding hours at ≥100% APR among markets with at least 168 funding observations; SKHX and SMSN are included. The common REST span is {START.isoformat()} through {END.isoformat()} UTC. Estimated REST page calls before harvest: {calls[0]}; actual network calls: {calls[1]}. A cache-only rerun made zero network calls.", "",
        "SKHX/SMSN bracket inference uses full on-disk L4 coverage aggregated to 1m bars. The other eight markets remain explicitly limited to the most recent roughly 5,000 cached REST candles per market (about 3.5 days). That short window is not funding-poor: the original ten-market cached window contains 584 settlements at ≥100% compounded APR. The limitation is temporal breadth, not absence of the target regime. No paid source was used to fill older minutes.", "",
        "G-F2 keeps the prediction framing: T4 observed R² at minute 50 of 0.962 (≥0.95) with real iid-excess, consistent with premium-mechanical settlement funding. Long-lead predictability remains moderate, so these clock-conditioned measurements should not be read as uniformly knowable far ahead of settlement.", "",
        "All numeric CIs use the existing Study-1 nonparametric cluster bootstrap (2,000 resamples, seed 0, min G=5), clustered by market × UTC 6-hour bucket. `INSUFFICIENT CLUSTERS` replaces numeric interval claims below the minimum. F-D separation status is reported per bracket and coverage cohort; no pooled overall verdict is rendered.", "", "## KEY_DECISIONS", "",
        "- High-funding scope: top ten by ≥100% APR time share with at least one week of hourly observations, including SKHX/SMSN.",
        "- SKHX/SMSN: aggregate every usable on-disk L4 file by exchange-time minute; open is the first trade price, close is the last, and the bar timestamp is the last trade's `time_exchange`. The eight other markets retain their deterministic widest/latest cached 1m candle file.",
        "- Brackets: open intervals `(t−h,t)` for negative h and `(t,t+h)` for positive h; include only bars whose last-trade/candle-close timestamp is strictly inside and measure first open to last close. Controls mirror these around `t+:30`.",
        "- Settlement timestamps in funding history are normalized to their UTC hour because source rows carry small millisecond transport offsets.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("estimate", "harvest", "analyze", "all"))
    args = parser.parse_args()
    estimate = estimate_harvest_calls(MARKETS, START, END)
    print(f"1M_HARVEST_ESTIMATED_NETWORK_CALLS={estimate} markets={len(MARKETS)} start={START.isoformat()} end={END.isoformat()}")
    actual = 0
    if args.mode in {"harvest", "all"}:
        with HyperliquidInfo(cache_dir=ROOT / "data" / "rest_cache", requests_per_second=1.0) as client:
            result = harvest_1m_candles(client=client, markets=MARKETS, start=START, end=END, output_dir=CANDLE_CACHE)
            actual = result.actual_client_calls
            print(f"1M_HARVEST_ACTUAL_NETWORK_CALLS={actual} outer_cache_hits={result.cache_hits}")
    if args.mode in {"analyze", "all"}:
        funding = _funding()
        observations = _candle_observations(funding)
        brackets = summarize_brackets(observations)
        coverage = observations.group_by("market", "coverage_group", "bracket_minutes").agg(
            pl.col("settlement_time").n_unique().alias("settlements"),
            pl.col("settlement_time").min().alias("first_settlement"),
            pl.col("settlement_time").max().alias("last_settlement"),
        )
        brackets.write_parquet(BRACKET_PATH)
        wallets, wallet_meta = wallet_flow()
        wallets.write_parquet(WALLET_PATH)
        premium, premium_meta = premium_decay()
        write_report(brackets, coverage, wallets, premium, wallet_meta, premium_meta, (estimate, actual))
        print(f"WROTE {BRACKET_PATH} rows={brackets.height}")
        print(f"WROTE {WALLET_PATH} rows={wallets.height}")
        print(f"WROTE {REPORT_PATH}")


if __name__ == "__main__":
    main()
