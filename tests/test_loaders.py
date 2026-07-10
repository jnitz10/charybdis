from datetime import date, datetime
from pathlib import Path

import polars as pl

from charybdis.loaders import (
    parse_flat_file_key,
    scan_book_events,
    scan_quotes,
    scan_trades,
)


FIXTURES = Path(__file__).parent / "fixtures"
BOOK_KEY = (
    "T-LIMITBOOK_FULL/D-20260408/E-HYPERLIQUID/"
    "IDDI-46924264+SC-HYPERLIQUID_DPERP_KM_SMALL2000_USDC"
    "+S-KM__003ASMALL2000.csv.gz"
)
TRADE_KEY = (
    "T-TRADES/D-20260408/E-HYPERLIQUID/"
    "IDDI-46924264+SC-HYPERLIQUID_DPERP_KM_SMALL2000_USDC"
    "+S-KM__003ASMALL2000.csv.gz"
)
QUOTE_KEY = (
    "T-QUOTES/D-2026051217/E-HYPERLIQUIDL4/"
    "IDDI-47427855+SC-HYPERLIQUIDL4_DPERP_KM_SMALL2000_USDC"
    "+S-KM__003ASMALL2000.csv.gz"
)


def test_parse_flat_file_key_detects_eras_and_decodes_coin() -> None:
    l2 = parse_flat_file_key(BOOK_KEY)
    l4 = parse_flat_file_key(QUOTE_KEY)

    assert (l2.dataset, l2.partition, l2.exchange_id, l2.era) == (
        "LIMITBOOK_FULL",
        "20260408",
        "HYPERLIQUID",
        "l2",
    )
    assert l2.partition_date == date(2026, 4, 8)
    assert l2.symbol_id == "HYPERLIQUID_DPERP_KM_SMALL2000_USDC"
    assert l2.coin == "KM:SMALL2000"
    assert l4.era == "l4"
    assert l4.partition == "2026051217"


def test_projected_loaders_read_real_trade_quote_and_book_slices() -> None:
    trades = scan_trades(
        FIXTURES / TRADE_KEY,
        columns=("time_exchange", "price", "base_amount", "taker_side"),
    ).collect()
    quotes = scan_quotes(
        FIXTURES / QUOTE_KEY,
        columns=("time_exchange", "ask_px", "ask_sx", "bid_px", "bid_sx"),
    ).collect()
    books = scan_book_events(
        FIXTURES / BOOK_KEY,
        columns=("time_exchange", "update_type", "is_buy", "entry_px", "entry_sx"),
    ).collect()

    assert trades.columns == ["time_exchange", "price", "base_amount", "taker_side"]
    assert trades.schema["time_exchange"] == pl.Datetime("ns")
    assert trades.row(0, named=True) == {
        "time_exchange": datetime(2026, 4, 8, 0, 10, 37, 662000),
        "price": 260.97,
        "base_amount": 0.767,
        "taker_side": "BUY",
    }
    assert quotes.columns == ["time_exchange", "ask_px", "ask_sx", "bid_px", "bid_sx"]
    assert quotes.row(0, named=True)["ask_px"] == 278.74
    assert quotes.row(0, named=True)["bid_sx"] == 281.501
    assert books[0, "time_exchange"].date() == date(2026, 4, 8)
    assert books[0, "update_type"] == "SNAPSHOT"
    assert books[0, "is_buy"] is False
    assert books[0, "entry_px"] == 261.75


def test_era_can_be_explicit_when_path_is_not_a_flat_file_key(tmp_path: Path) -> None:
    source = FIXTURES / QUOTE_KEY
    local = tmp_path / "quotes.csv.gz"
    local.write_bytes(source.read_bytes())

    quotes = scan_quotes(
        local,
        era="l4",
        columns=("time_exchange", "ask_px", "bid_px"),
    ).collect()

    assert quotes.height == 5
    assert quotes[0, "ask_px"] == 278.74
