"""Lazy, column-projected readers for CoinAPI flat-file CSVs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Literal, Sequence

import polars as pl


Era = Literal["l2", "l4"]

_KEY_RE = re.compile(
    r"(?:^|/)T-(?P<dataset>[^/]+)/D-(?P<partition>\d{8}(?:\d{2})?)/"
    r"E-(?P<exchange_id>[^/]+)/"
    r"IDDI-(?P<iddi>[^+]+)\+SC-(?P<symbol_id>[^+]+)\+S-(?P<coin>.+?)\.csv\.gz$"
)

_FLOAT_COLUMNS = {
    "price",
    "base_amount",
    "ask_px",
    "ask_sx",
    "bid_px",
    "bid_sx",
    "entry_px",
    "entry_sx",
    "orig_size",
    "trigger_px",
}
_BOOLEAN_COLUMNS = {
    "is_buy",
    "reduce_only",
    "is_trigger",
    "is_position_tpsl",
    "is_child",
}


@dataclass(frozen=True)
class FlatFileKey:
    dataset: str
    partition: str
    exchange_id: str
    symbol_id: str
    coin: str
    iddi: str

    @property
    def era(self) -> Era:
        if self.exchange_id == "HYPERLIQUID":
            return "l2"
        if self.exchange_id == "HYPERLIQUIDL4":
            return "l4"
        raise ValueError(f"cannot infer era from exchange id {self.exchange_id!r}")

    @property
    def partition_date(self) -> date:
        return datetime.strptime(self.partition[:8], "%Y%m%d").date()


def parse_flat_file_key(key: str | Path) -> FlatFileKey:
    """Parse a CoinAPI object key or a local path ending in that key."""

    match = _KEY_RE.search(str(key).replace("\\", "/"))
    if match is None:
        raise ValueError(f"not a CoinAPI flat-file key: {key!s}")
    values = match.groupdict()
    return FlatFileKey(
        dataset=values["dataset"],
        partition=values["partition"],
        exchange_id=values["exchange_id"],
        symbol_id=values["symbol_id"],
        coin=values["coin"].replace("__003A", ":"),
        iddi=values["iddi"],
    )


def scan_trades(
    source: str | Path,
    *,
    key: str | Path | None = None,
    era: Era | None = None,
    columns: Sequence[str] | None = None,
) -> pl.LazyFrame:
    """Lazily scan an L2 or L4 trades file, parsing its timestamps."""

    return _scan_dataset(source, "TRADES", key=key, era=era, columns=columns)


def scan_quotes(
    source: str | Path,
    *,
    key: str | Path | None = None,
    era: Era | None = None,
    columns: Sequence[str] | None = None,
) -> pl.LazyFrame:
    """Lazily scan actual on-disk quote columns (ask_px/ask_sx/bid_px/bid_sx)."""

    return _scan_dataset(source, "QUOTES", key=key, era=era, columns=columns)


def scan_book_events(
    source: str | Path,
    *,
    key: str | Path | None = None,
    era: Era | None = None,
    columns: Sequence[str] | None = None,
) -> pl.LazyFrame:
    """Lazily scan book events and date-stamp L2 time-of-day timestamps."""

    return _scan_dataset(
        source,
        "LIMITBOOK_FULL",
        key=key,
        era=era,
        columns=columns,
    )


def _scan_dataset(
    source: str | Path,
    dataset: str,
    *,
    key: str | Path | None,
    era: Era | None,
    columns: Sequence[str] | None,
) -> pl.LazyFrame:
    metadata = _metadata_for(source, key)
    resolved_era = _resolve_era(metadata, era)
    if metadata is not None and metadata.dataset != dataset:
        raise ValueError(
            f"expected T-{dataset}, got T-{metadata.dataset} in supplied key"
        )

    scan = pl.scan_csv(
        source,
        separator=";",
        null_values="",
        schema_overrides={name: pl.Float64 for name in _FLOAT_COLUMNS},
        infer_schema_length=1000,
        low_memory=True,
        rechunk=False,
    )
    available = scan.collect_schema().names()
    selected = list(columns) if columns is not None else available
    missing = [name for name in selected if name not in available]
    if missing:
        raise ValueError(f"columns absent from {dataset} header: {missing}")

    frame = scan.select(selected)
    expressions: list[pl.Expr] = []
    for name in selected:
        if name in ("time_exchange", "time_coinapi"):
            value = pl.col(name).cast(pl.String)
            if dataset == "LIMITBOOK_FULL" and resolved_era == "l2":
                if metadata is None:
                    raise ValueError(
                        "an L2 book path/key with D-YYYYMMDD is required to date timestamps"
                    )
                prefix = metadata.partition_date.isoformat() + "T"
                value = pl.lit(prefix) + value
            expressions.append(
                value.str.to_datetime(time_unit="ns", strict=True).alias(name)
            )
        elif name in _FLOAT_COLUMNS:
            expressions.append(pl.col(name).cast(pl.Float64))
        elif name in _BOOLEAN_COLUMNS:
            expressions.append(pl.col(name).cast(pl.Int8).cast(pl.Boolean))
    return frame.with_columns(expressions)


def _metadata_for(
    source: str | Path, key: str | Path | None
) -> FlatFileKey | None:
    candidate = source if key is None else key
    try:
        return parse_flat_file_key(candidate)
    except ValueError:
        if key is not None:
            raise
        return None


def _resolve_era(metadata: FlatFileKey | None, explicit: Era | None) -> Era:
    if explicit not in (None, "l2", "l4"):
        raise ValueError(f"invalid era {explicit!r}; expected 'l2' or 'l4'")
    if explicit is not None:
        if metadata is not None and metadata.era != explicit:
            raise ValueError(
                f"explicit era {explicit!r} conflicts with {metadata.exchange_id!r}"
            )
        return explicit
    if metadata is None:
        raise ValueError("era is required when source/key does not contain E-<exchange>")
    return metadata.era
