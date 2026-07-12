"""Shadow forward test for the post-listing exhaustion-reversal candidates.

Implements the frozen specifications from
``docs/reports/strategy_discovery_2026-07-11.md`` (raw rule and the follow-up
round's residual variant, run side by side per its updated priorities) plus
the extra logging recommended by
``docs/reports/strategy_discovery_checks_2026-07-11.md`` (oracle/mark
decomposition, signal-time spread and depth on every qualifying name).
No parameter may change before the forward evaluation date; edit FROZEN_*
constants only with a new dated report.

Strategies:

- ``raw_lifecycle``: age 7-55d, liq >= $1M, 3-session return <= -8%, long
  only, top-1 by largest decline, 24h hold. Shorts recorded, never taken.
- ``residual_lifecycle``: same filters, but the signal is the 3-session
  return minus the same-day cross-sectional median 3-session return over all
  HIP-3 markets (the venue factor), <= -8%. Long only, top-1 by most
  negative residual, 24h hold.

Each strategy runs an independent shadow book (max one open position each).
The SPCX system-order reversal from the follow-up round is NOT implemented:
its signal requires wallet-attributed system-order flow, which exists only
in the historical CoinAPI L4 archive, not in the free live info API.

Designed to run as an hourly systemd/cron tick::

    uv run charybdis-forward tick     # hourly, minute :05
    uv run charybdis-forward report   # human summary of the ledger so far

All writes are append-only JSONL under ``data/forward/`` plus an atomically
rewritten ``state.json``; a missed tick delays marks but corrupts nothing.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from .hl_rest import EARLIEST_SANE_MS, HyperliquidInfo

logger = logging.getLogger("charybdis.forward_test")

FORWARD_DIR = Path("data/forward")
STATE_PATH = FORWARD_DIR / "state.json"
SIGNALS_PATH = FORWARD_DIR / "signals.jsonl"
MARKS_PATH = FORWARD_DIR / "marks.jsonl"
POSITIONS_PATH = FORWARD_DIR / "positions.jsonl"

# Frozen forward-test specification (strategy_discovery_2026-07-11.md).
FROZEN_AGE_MIN_DAYS = 7
FROZEN_AGE_MAX_DAYS = 56          # exclusive
FROZEN_LIQ_FLOOR_USD = 1_000_000  # trailing 7-session median notional
FROZEN_RETURN_THRESHOLD = -0.08   # 3-session close-to-close (raw rule)
FROZEN_RESIDUAL_THRESHOLD = -0.08  # 3-session return minus HIP-3 median
FROZEN_HOLD_HOURS = 24
FROZEN_MAX_CONCURRENT = 1          # per strategy
LEFT_CENSOR_FIRST_DATE = date(2026, 1, 1)
DIAGNOSTIC_HOURS = [1, 2, 6, 12, 18, 24]

STRATEGIES = ["raw_lifecycle", "residual_lifecycle"]

CTX_FIELDS = ["funding", "openInterest", "oraclePx", "markPx", "premium", "dayNtlVlm", "midPx"]
BOOK_DEPTH_LEVELS = 5


def _prepare_panel(panel: pl.DataFrame, signal_day: date) -> pl.DataFrame:
    """Shared feature frame: age, 3-session return, trailing liquidity."""

    return (
        panel.filter(pl.col("date") <= signal_day)
        .sort("market", "date")
        .with_columns((pl.col("volume") * pl.col("close")).alias("ntl"))
        .with_columns(pl.col("date").min().over("market").alias("first_date"))
        .with_columns(
            (pl.col("date") - pl.col("first_date")).dt.total_days().alias("age_days"),
            (pl.col("close") / pl.col("close").shift(3).over("market") - 1).alias("ret3"),
            pl.col("ntl").shift(1).rolling_median(7).over("market").alias("liq7_usd"),
        )
    )


def _apply_filters(frame: pl.DataFrame, signal_day: date) -> pl.DataFrame:
    return frame.filter(
        (pl.col("date") == signal_day)
        & (pl.col("first_date") != LEFT_CENSOR_FIRST_DATE)
        & (pl.col("age_days") >= FROZEN_AGE_MIN_DAYS)
        & (pl.col("age_days") < FROZEN_AGE_MAX_DAYS)
        & (pl.col("liq7_usd") >= FROZEN_LIQ_FLOOR_USD)
    )


def compute_signals(panel: pl.DataFrame, signal_day: date) -> pl.DataFrame:
    """Raw frozen rule at one 00:00 UTC boundary.

    ``panel`` needs columns ``market`` (str), ``date`` (pl.Date), ``close``,
    ``volume`` (base units). Returns one row per qualifying signal with
    ``side`` (1 long / -1 short) and ``selected`` marking the single
    largest-decline long.
    """

    frame = _prepare_panel(panel, signal_day)
    signals = _apply_filters(frame, signal_day).filter(
        pl.col("ret3").abs() >= abs(FROZEN_RETURN_THRESHOLD)
    ).with_columns(
        pl.when(pl.col("ret3") <= FROZEN_RETURN_THRESHOLD)
        .then(pl.lit(1))
        .otherwise(pl.lit(-1))
        .alias("side"),
        pl.col("ret3").alias("signal_value"),
    )
    longs = signals.filter(pl.col("side") == 1)
    chosen = longs.sort("signal_value").head(1)["market"].to_list() if longs.height else []
    return signals.with_columns(pl.col("market").is_in(chosen).alias("selected")).select(
        "market", "date", "side", "ret3", "signal_value", "age_days", "liq7_usd", "close", "selected"
    )


def compute_residual_signals(panel: pl.DataFrame, signal_day: date) -> pl.DataFrame:
    """Residual frozen rule: ret3 minus the same-day HIP-3 cross-sectional median.

    The median is taken over ALL HIP-3 markets with a valid 3-session return
    on the signal day (including left-censored markets -- the factor is a
    market property; the left-censor exclusion applies only to tradeable
    signal rows, where age is unknowable). Long only.
    """

    frame = _prepare_panel(panel, signal_day)
    day_rows = frame.filter(pl.col("date") == signal_day)
    median_ret3 = day_rows["ret3"].drop_nulls().median()
    if median_ret3 is None:
        return pl.DataFrame(
            schema={
                "market": pl.String, "date": pl.Date, "side": pl.Int32, "ret3": pl.Float64,
                "signal_value": pl.Float64, "age_days": pl.Int64, "liq7_usd": pl.Float64,
                "close": pl.Float64, "selected": pl.Boolean,
            }
        )
    signals = _apply_filters(frame, signal_day).with_columns(
        (pl.col("ret3") - median_ret3).alias("signal_value")
    ).filter(pl.col("signal_value") <= FROZEN_RESIDUAL_THRESHOLD).with_columns(
        pl.lit(1).alias("side")
    )
    chosen = signals.sort("signal_value").head(1)["market"].to_list() if signals.height else []
    return signals.with_columns(pl.col("market").is_in(chosen).alias("selected")).select(
        "market", "date", "side", "ret3", "signal_value", "age_days", "liq7_usd", "close", "selected"
    )


SIGNAL_FUNCTIONS = {
    "raw_lifecycle": compute_signals,
    "residual_lifecycle": compute_residual_signals,
}


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _book_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce an l2Book payload to top-of-book plus depth for the ledger."""

    bids, asks = payload.get("levels", [[], []])
    out: dict[str, Any] = {
        "book_time_ms": payload.get("time"),
        "bid_px": _to_float(bids[0]["px"]) if bids else None,
        "bid_sz": _to_float(bids[0]["sz"]) if bids else None,
        "ask_px": _to_float(asks[0]["px"]) if asks else None,
        "ask_sz": _to_float(asks[0]["sz"]) if asks else None,
        "bid_levels": [
            {"px": _to_float(l["px"]), "sz": _to_float(l["sz"])}
            for l in bids[:BOOK_DEPTH_LEVELS]
        ],
        "ask_levels": [
            {"px": _to_float(l["px"]), "sz": _to_float(l["sz"])}
            for l in asks[:BOOK_DEPTH_LEVELS]
        ],
    }
    if out["bid_px"] and out["ask_px"]:
        mid = (out["bid_px"] + out["ask_px"]) / 2
        out["mid_px"] = mid
        out["spread_bp"] = (out["ask_px"] - out["bid_px"]) / mid * 1e4
    else:
        out["mid_px"] = None
        out["spread_bp"] = None
    return out


def _default_strategy_state() -> dict[str, Any]:
    return {"last_signal_date": None, "open_position": None}


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "position_counter": 0,
            "strategies": {name: _default_strategy_state() for name in STRATEGIES},
        }
    state = json.loads(STATE_PATH.read_text())
    if "strategies" not in state:  # migrate single-strategy layout (pre 2026-07-12)
        state = {
            "position_counter": state.get("position_counter", 0),
            "strategies": {
                "raw_lifecycle": {
                    "last_signal_date": state.get("last_signal_date"),
                    "open_position": state.get("open_position"),
                },
            },
        }
        if state["strategies"]["raw_lifecycle"]["open_position"] is not None:
            state["strategies"]["raw_lifecycle"]["open_position"].setdefault(
                "strategy", "raw_lifecycle"
            )
    for name in STRATEGIES:
        state["strategies"].setdefault(name, _default_strategy_state())
    return state


def _save_state(state: dict[str, Any]) -> None:
    FORWARD_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".json.part")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    FORWARD_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _live_universe(api: HyperliquidInfo) -> dict[str, dict[str, Any]]:
    """Map live HIP-3 market name -> context snapshot (floats)."""

    contexts_by_market: dict[str, dict[str, Any]] = {}
    for dex in api.perp_dexs(refresh=True):
        metadata, contexts = api.meta_and_asset_ctxs(dex, refresh=True)
        for asset, context in zip(metadata.get("universe", []), contexts, strict=True):
            row = {field: _to_float(context.get(field)) for field in CTX_FIELDS}
            impact = context.get("impactPxs")
            if isinstance(impact, list) and len(impact) == 2:
                row["impact_bid"] = _to_float(impact[0])
                row["impact_ask"] = _to_float(impact[1])
            contexts_by_market[str(asset["name"])] = row
    return contexts_by_market


def _fetch_daily_panel(
    api: HyperliquidInfo, markets: list[str], boundary_ms: int
) -> pl.DataFrame:
    frames = []
    for number, market in enumerate(markets, 1):
        if number % 25 == 0:
            logger.info("daily candles %d/%d", number, len(markets))
        try:
            candles = api.candle_snapshot(market, "1d", EARLIEST_SANE_MS, boundary_ms)
        except Exception:
            logger.exception("daily candle fetch failed for %s", market)
            continue
        if candles.height:
            frames.append(candles.select("market", "time_open", "close", "volume"))
    if not frames:
        return pl.DataFrame(
            schema={"market": pl.String, "date": pl.Date, "close": pl.Float64, "volume": pl.Float64}
        )
    return (
        pl.concat(frames)
        .with_columns(pl.col("time_open").dt.date().alias("date"))
        .select("market", "date", "close", "volume")
    )


def _mark_positions(
    api: HyperliquidInfo,
    state: dict[str, Any],
    contexts: dict[str, dict[str, Any]],
    now: datetime,
) -> None:
    for strategy in STRATEGIES:
        strategy_state = state["strategies"][strategy]
        position = strategy_state.get("open_position")
        if position is None:
            continue
        market = position["market"]
        entry_ts = datetime.fromisoformat(position["entry_ts"])
        hours_held = (now - entry_ts).total_seconds() / 3600
        try:
            book = _book_summary(api.l2_book(market))
        except Exception:
            logger.exception("l2Book failed for open position %s", market)
            book = {}
        context = contexts.get(market, {})
        _append_jsonl(
            MARKS_PATH,
            {
                "strategy": strategy,
                "position_id": position["id"],
                "market": market,
                "ts": now.isoformat(),
                "hours_held": round(hours_held, 3),
                **book,
                **{f"ctx_{key}": value for key, value in context.items()},
            },
        )

        if hours_held >= FROZEN_HOLD_HOURS:
            exit_bid = book.get("bid_px")
            _append_jsonl(
                POSITIONS_PATH,
                {
                    **position,
                    "strategy": strategy,
                    "exit_ts": now.isoformat(),
                    "hours_held": round(hours_held, 3),
                    "exit_bid": exit_bid,
                    "exit_ask": book.get("ask_px"),
                    "exit_mid": book.get("mid_px"),
                    "exit_oracle": context.get("oraclePx"),
                    "exit_mark": context.get("markPx"),
                    "exit_late": hours_held > FROZEN_HOLD_HOURS + 1.5,
                    "executable_net_bp": (
                        (exit_bid / position["entry_ask"] - 1) * 1e4
                        if exit_bid and position.get("entry_ask")
                        else None
                    ),
                },
            )
            strategy_state["open_position"] = None
            logger.info("[%s] closed shadow position %s after %.1fh", strategy, market, hours_held)


def _generate_strategy_signals(
    api: HyperliquidInfo,
    state: dict[str, Any],
    strategy: str,
    signals: pl.DataFrame,
    contexts: dict[str, dict[str, Any]],
    now: datetime,
    signal_day: date,
) -> None:
    strategy_state = state["strategies"][strategy]
    for row in signals.iter_rows(named=True):
        market = row["market"]
        try:
            book = _book_summary(api.l2_book(market))
        except Exception:
            logger.exception("l2Book failed for signal %s", market)
            book = {}
        context = contexts.get(market, {})
        taken, reason = False, None
        if row["side"] == -1:
            reason = "short_leg_disabled"
        elif not row["selected"]:
            reason = "not_largest_decline"
        elif strategy_state.get("open_position") is not None:
            reason = "position_open"
        elif not book.get("ask_px"):
            reason = "no_ask_liquidity"
        else:
            taken = True

        _append_jsonl(
            SIGNALS_PATH,
            {
                "strategy": strategy,
                "signal_date": signal_day.isoformat(),
                "ts": now.isoformat(),
                "market": market,
                "side": row["side"],
                "ret3": row["ret3"],
                "signal_value": row["signal_value"],
                "age_days": row["age_days"],
                "liq7_usd": row["liq7_usd"],
                "signal_close": row["close"],
                "selected": row["selected"],
                "taken": taken,
                "skip_reason": reason,
                **book,
                **{f"ctx_{key}": value for key, value in context.items()},
            },
        )

        if taken:
            state["position_counter"] += 1
            strategy_state["open_position"] = {
                "id": state["position_counter"],
                "strategy": strategy,
                "market": market,
                "signal_date": signal_day.isoformat(),
                "entry_ts": now.isoformat(),
                "entry_bid": book.get("bid_px"),
                "entry_ask": book.get("ask_px"),
                "entry_mid": book.get("mid_px"),
                "entry_spread_bp": book.get("spread_bp"),
                "entry_oracle": context.get("oraclePx"),
                "entry_mark": context.get("markPx"),
                "ret3": row["ret3"],
                "signal_value": row["signal_value"],
                "age_days": row["age_days"],
            }
            logger.info("[%s] opened shadow long %s at ask %s", strategy, market, book.get("ask_px"))

    strategy_state["last_signal_date"] = (signal_day + timedelta(days=1)).isoformat()


def _generate_signals(
    api: HyperliquidInfo,
    state: dict[str, Any],
    contexts: dict[str, dict[str, Any]],
    now: datetime,
) -> None:
    today = now.date()
    due = [
        strategy for strategy in STRATEGIES
        if state["strategies"][strategy].get("last_signal_date") != today.isoformat()
    ]
    if not due:
        return
    signal_day = today - timedelta(days=1)
    boundary_ms = int(datetime(today.year, today.month, today.day, tzinfo=UTC).timestamp() * 1000)
    markets = sorted(contexts)
    logger.info("signal run for %s over %d live markets (%s)", signal_day, len(markets), due)
    panel = _fetch_daily_panel(api, markets, boundary_ms)
    for strategy in due:
        signals = SIGNAL_FUNCTIONS[strategy](panel, signal_day)
        logger.info("[%s] qualifying signals: %d", strategy, signals.height)
        _generate_strategy_signals(api, state, strategy, signals, contexts, now, signal_day)


def tick() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    state = _load_state()
    with HyperliquidInfo(requests_per_second=1.0) as api:
        contexts = _live_universe(api)
        # marks first: open positions get their hour mark even on signal days
        _mark_positions(api, state, contexts, now)
        _generate_signals(api, state, contexts, now)
        logger.info("tick complete: %d rest calls", api.rest_calls)
    _save_state(state)


def _read_jsonl(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame()
    frame = pl.read_ndjson(path, infer_schema_length=None)
    if frame.height and "strategy" not in frame.columns:
        frame = frame.with_columns(pl.lit("raw_lifecycle").alias("strategy"))
    elif "strategy" in frame.columns:
        frame = frame.with_columns(pl.col("strategy").fill_null("raw_lifecycle"))
    return frame


def report() -> None:
    signals = _read_jsonl(SIGNALS_PATH)
    marks = _read_jsonl(MARKS_PATH)
    positions = _read_jsonl(POSITIONS_PATH)
    state = _load_state()

    for strategy in STRATEGIES:
        strategy_state = state["strategies"][strategy]
        open_position = strategy_state.get("open_position") or {}
        print(f"[{strategy}] last_signal_date={strategy_state.get('last_signal_date')} "
              f"open={open_position.get('market', 'none')}")
    if signals.is_empty():
        print("no signals recorded yet")
        return

    for strategy in STRATEGIES:
        s_signals = signals.filter(pl.col("strategy") == strategy)
        if s_signals.is_empty():
            continue
        longs = s_signals.filter(pl.col("side") == 1)
        print(f"\n=== {strategy}: {s_signals.height} signals, {longs.height} long, "
              f"{s_signals.filter(pl.col('taken')).height} taken ===")
        print("signal-time spread by market:")
        print(longs.group_by("market").agg(
            pl.len().alias("signals"),
            pl.col("spread_bp").median().round(1).alias("med_spread_bp"),
            (pl.col("bid_sz") * pl.col("bid_px")).median().round(0).alias("med_bid_depth_usd"),
        ).sort("signals", descending=True))

        s_positions = positions.filter(pl.col("strategy") == strategy) if not positions.is_empty() else positions
        if s_positions.is_empty():
            continue
        print(f"closed positions: {s_positions.height}")
        rows = []
        for position in s_positions.iter_rows(named=True):
            row = {key: position.get(key) for key in
                   ("id", "market", "signal_date", "entry_ask", "exit_bid",
                    "executable_net_bp", "exit_late")}
            if not marks.is_empty():
                pmarks = marks.filter(pl.col("position_id") == position["id"])
                for hour in DIAGNOSTIC_HOURS:
                    nearest = pmarks.with_columns(
                        (pl.col("hours_held") - hour).abs().alias("gap")
                    ).sort("gap").head(1)
                    if nearest.height and nearest["gap"][0] <= 0.75:
                        mid = nearest["mid_px"][0]
                        entry_mid = position.get("entry_mid")
                        row[f"h{hour}_bp"] = (
                            round((mid / entry_mid - 1) * 1e4, 1)
                            if mid and entry_mid else None
                        )
            rows.append(row)
        print(pl.DataFrame(rows))
        net = s_positions["executable_net_bp"].drop_nulls()
        if len(net):
            print(f"executable net (bid-to-ask, pre-fee): mean {net.mean():+.1f}bp "
                  f"over {len(net)} positions")

    print("\nreminder: subtract fees (~9bp RT) and add funding from marks; "
          "do not promote on early wins (frozen spec).")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["tick", "report"])
    arguments = parser.parse_args()
    if arguments.command == "tick":
        tick()
    else:
        report()


if __name__ == "__main__":
    main()
