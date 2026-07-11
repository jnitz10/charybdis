"""Generic schema/rows access for the data browser."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import polars as pl

from charybdis.console import datasets

_OPS = {"eq", "ne", "gt", "ge", "lt", "le", "contains"}


def json_value(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [json_value(x) for x in v]
    return v


def dataset_schema(name: str) -> dict:
    schema = pl.read_parquet_schema(datasets.dataset_path(name))
    return {
        "name": name,
        "columns": [{"name": c, "dtype": str(t)} for c, t in schema.items()],
    }


def _filter_expr(schema: dict[str, pl.DataType], spec: str) -> pl.Expr:
    parts = spec.split(":", 2)
    if len(parts) != 3 or parts[1] not in _OPS:
        raise ValueError(f"bad filter: {spec!r} (want col:op:value)")
    col, op, raw = parts
    if col not in schema:
        raise ValueError(f"unknown column: {col}")
    dtype = schema[col]
    value: Any
    if op == "contains":
        return pl.col(col).cast(pl.String).str.contains(raw, literal=True)
    if dtype.is_numeric():
        value = float(raw)
    elif dtype == pl.Boolean:
        value = raw.lower() in ("true", "1")
    else:
        value = raw
    c = pl.col(col)
    return {"eq": c == value, "ne": c != value, "gt": c > value,
            "ge": c >= value, "lt": c < value, "le": c <= value}[op]


def dataset_rows(
    name: str,
    page: int = 1,
    page_size: int = 100,
    sort: str | None = None,
    order: str = "asc",
    filters: list[str] | None = None,
) -> dict:
    page = max(1, page)
    page_size = min(max(1, page_size), 500)
    lf = datasets.scan_dataset(name)
    schema = dict(pl.read_parquet_schema(datasets.dataset_path(name)))
    for spec in filters or []:
        lf = lf.filter(_filter_expr(schema, spec))
    if sort:
        if sort not in schema:
            raise ValueError(f"unknown column: {sort}")
        lf = lf.sort(sort, descending=(order == "desc"), nulls_last=True)
    total = lf.select(pl.len()).collect().item()
    df = lf.slice((page - 1) * page_size, page_size).collect()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "columns": df.columns,
        "rows": [[json_value(v) for v in row] for row in df.rows()],
    }
