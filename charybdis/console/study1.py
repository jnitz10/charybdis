"""Study 1 markout aggregation. study1_fills_l2 is ~274 MB: lazy scan, cached payload."""
from __future__ import annotations

import re

import polars as pl

from charybdis.console import datasets
from charybdis.console.tables import json_value

_HORIZON_RE = re.compile(r"^net_markout_(\w+)_bps$")
_DATASET = "study1_fills_l2"
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0}


def _horizon_seconds(h: str) -> float:
    m = re.match(r"([0-9.]+)([smh])$", h)
    if not m:
        return float("inf")
    return float(m.group(1)) * _UNIT_SECONDS[m.group(2)]


def markout_summary() -> dict:
    def build() -> dict:
        schema = pl.read_parquet_schema(datasets.dataset_path(_DATASET))
        horizons = sorted(
            (m.group(1) for c in schema if (m := _HORIZON_RE.match(c))),
            key=_horizon_seconds,
        )
        aggs = []
        for h in horizons:
            valid = pl.when(~pl.col(f"stale_{h}")).then(pl.col(f"net_markout_{h}_bps"))
            aggs.append(valid.mean().alias(f"mean_{h}"))
            aggs.append(valid.count().alias(f"n_{h}"))
        df = datasets.scan_dataset(_DATASET).group_by("market", "segment").agg(aggs).collect()
        cells = [
            {
                "market": row["market"],
                "segment": row["segment"],
                "horizon": h,
                "mean_bps": json_value(row[f"mean_{h}"]),
                "n": row[f"n_{h}"],
            }
            for row in df.rows(named=True)
            for h in horizons
        ]
        return {
            "horizons": horizons,
            "markets": sorted(df["market"].unique().to_list()),
            "segments": sorted(df["segment"].unique().to_list()),
            "cells": cells,
        }

    return datasets.cached_payload("study1_markout", _DATASET, build)
