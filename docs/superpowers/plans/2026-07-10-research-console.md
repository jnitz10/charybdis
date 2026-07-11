# Charybdis Research Console + AI Notebooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web dashboard (`uv run charybdis-console` → http://localhost:8787) that visualizes the study findings from `data/reports/*.parquet` with interactive charts, plus JupyterLab wired to Claude Code via notebook-intelligence.

**Architecture:** FastAPI backend inside the existing `charybdis` package (`charybdis/console/`), reading parquet read-only with polars. Vite + React + TypeScript + Tailwind frontend in `console/` at repo root; the backend serves `console/dist/` statically. Charting: TradingView lightweight-charts (candles, equity), Apache ECharts (everything else). Spec: `docs/superpowers/specs/2026-07-10-research-console-design.md`.

**Tech Stack:** Python ≥3.11, uv, polars, FastAPI, uvicorn, PyYAML, pytest; Node ≥20, Vite 6, React 18, TypeScript, Tailwind v4, echarts 5, lightweight-charts 5; JupyterLab + notebook-intelligence.

## Global Constraints

- Python invocations always via `uv run …` from the repo root (`/home/jnitz/Documents/trading/charybdis`).
- Backend is READ-ONLY over `data/reports/`. Never write into `data/`.
- A missing parquet must never produce a 500: list endpoints return empty lists; detail endpoints raise HTTP 404 with detail `"dataset not present: <name>"`.
- Backend port: **8787**. Vite dev server proxies `/api` → `http://localhost:8787`.
- Dataset names are parquet stems under `data/reports/` (e.g. `study3_sa_census`). Reject names containing `/`, `\`, or `..`.
- Tests get their data dir via env var `CHARYBDIS_DATA_DIR` (tiny fixture parquets built in `tmp_path`); production default is `<repo>/data/reports`.
- Frontend: dark theme only. Colors come from `console/src/theme.ts` (single source of truth).
- Frontend commands run in `console/` (`npm run …`). Verification gate for frontend tasks: `npm run typecheck && npm run build` (no component-test suite in v1).
- Commit after every task with a conventional-commit message; include the harness-required trailers (Co-Authored-By + Claude-Session) on every commit.
- Existing pytest suite must stay green: `uv run pytest -q` at the end of every backend task.

## Data facts (verified against the real files — do not re-derive)

- `study3_candles_1h` / `study3_candles_1d` columns: `dex, market, interval, open_time_ms, close_time_ms, time_open, open, high, low, close, v, n`. The `market` column already includes the dex prefix (`"xyz:SP500"`, `"hyna:LINK"`) except 3 main-dex rows (`"SOL"` …). Use the `market` column as the symbol key.
- `study3_sc_backtest` columns include: `strategy, rebalance_time, market, net_pnl, funding_pnl, price_pnl, cost_pnl, turnover`. Six strategies exist: `single-name-hedged, short-only-daily, single-name-unhedged, long-short-daily, long-short-8h, short-only-8h`. `net_pnl` is an additive per-row return contribution; period return = sum of `net_pnl` grouped by `rebalance_time`.
- `study3_sc_summary` has one row per `strategy` with `net_total_return, return_ci_low/high, sharpe, sharpe_ci_low/high, funding_pnl, price_pnl, cost_pnl, max_drawdown, rebalance_count, markets_entered`.
- `study1_fills_l2` (274 MB — always use `pl.scan_parquet`) has per-horizon column families `net_markout_<h>_bps` + `stale_<h>` for h ∈ {1s, 5s, 30s, …} (discover horizons by regex, don't hardcode), plus `market, segment` (segment values are RTH/off-hours/weekend style labels).
- `forced_flow_vs_baseline_markout_proxy` (small): `market, window_type, horizon, point_estimate_bps, ci_low_bps, ci_high_bps, n, G, …`.
- `study3_sa_census` (small): `market, mean_apr, mean_apr_ci_low, mean_apr_ci_high, shock_half_life_hours, ar1_phi, n_funding_hours, carry_relevant, coverage_status, …`.
- `study3_sd_brackets` (small): `coverage_group, bracket_minutes, group_type, mean_return, ci_low, ci_high, baseline_mean_return, baseline_ci_low, baseline_ci_high, separation_status, n`.
- `study3_se_spreads` (small): `pair_id, market_a, market_b, mean_abs_diff_apr, persistence_half_life_hours, pct_time_gt_maker_breakeven, pct_time_gt_taker_breakeven, maker_never_exceeds_breakeven, taker_never_exceeds_breakeven, basis_p95_abs_excursion, p95_diff_horizon_return, …`.
- `study3_sf_event_rates` (small): `analysis_cut, bucket_order, funding_bucket, event_rate_per_market_hour, ci_low, ci_high`.
- `study3_sf_hazard` (small): `scope, bucket_order, funding_bucket, probability_event_within_horizon, hazard_horizon_hours, coverage_saturated`.

---

### Task 1: Backend skeleton — datasets module, app factory, entry point

**Files:**
- Modify: `pyproject.toml` (add deps + script entry)
- Create: `charybdis/console/__init__.py`
- Create: `charybdis/console/datasets.py`
- Create: `charybdis/console/server.py`
- Create: `tests/conftest.py`
- Test: `tests/test_console_datasets.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `charybdis.console.datasets.data_dir() -> Path`
  - `charybdis.console.datasets.dataset_path(name: str) -> Path` (raises `ValueError` on bad names)
  - `charybdis.console.datasets.dataset_exists(name: str) -> bool`
  - `charybdis.console.datasets.list_datasets() -> list[dict]` (keys: `name, columns, size_bytes, mtime`)
  - `charybdis.console.datasets.scan_dataset(name: str) -> pl.LazyFrame` (raises `FileNotFoundError` if absent)
  - `charybdis.console.datasets.cached_payload(key: str, name: str, builder: Callable[[], Any]) -> Any` (mtime-keyed cache)
  - `charybdis.console.server.create_app() -> FastAPI` with `GET /api/health`, `GET /api/datasets`
  - `charybdis.console.server.main()` — uvicorn runner, `charybdis-console` script
  - pytest fixture `console_data_dir` in `tests/conftest.py` (builds fixture parquets, sets `CHARYBDIS_DATA_DIR`)

- [ ] **Step 1: Add dependencies and script entry to `pyproject.toml`**

In the `dependencies` list add three entries (keep alphabetical order):

```toml
dependencies = [
    "boto3",
    "exchange-calendars",
    "fastapi",
    "httpx",
    "polars",
    "pyarrow",
    "pytest",
    "pyyaml",
    "uvicorn",
    "zstandard",
]
```

In `[project.scripts]` add:

```toml
[project.scripts]
charybdis-ffs3 = "charybdis.ffs3:main"
charybdis-console = "charybdis.console.server:main"
```

Run: `uv sync`
Expected: resolves and installs fastapi, uvicorn, pyyaml without errors.

- [ ] **Step 2: Write the shared test fixture**

Create `tests/conftest.py`:

```python
"""Shared fixtures for console tests: tiny parquet datasets in a temp data dir."""
from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest


def _candles(market: str, n: int = 60, start_price: float = 100.0) -> pl.DataFrame:
    t0 = datetime(2026, 6, 1)
    rows = []
    price = start_price
    for i in range(n):
        o = price
        c = price + (1.0 if i % 3 else -1.5)
        rows.append(
            {
                "dex": market.split(":")[0] if ":" in market else "main",
                "market": market,
                "interval": "1h",
                "open_time_ms": int((t0 + timedelta(hours=i)).timestamp() * 1000),
                "close_time_ms": int((t0 + timedelta(hours=i + 1)).timestamp() * 1000),
                "time_open": t0 + timedelta(hours=i),
                "open": o,
                "high": max(o, c) + 0.5,
                "low": min(o, c) - 0.5,
                "close": c,
                "v": 10.0 + i,
                "n": 5,
            }
        )
        price = c
    return pl.DataFrame(rows)


@pytest.fixture()
def console_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "reports"
    d.mkdir()

    pl.concat([_candles("xyz:AAA"), _candles("km:BBB", start_price=50.0)]).write_parquet(
        d / "study3_candles_1h.parquet"
    )

    t0 = datetime(2026, 6, 1)
    bt_rows = []
    for i in range(40):
        for mkt, pnl in [("xyz:AAA", 0.001 * ((i % 5) - 2)), ("km:BBB", 0.0005)]:
            bt_rows.append(
                {
                    "strategy": "short-only-daily",
                    "rebalance_time": t0 + timedelta(days=i),
                    "market": mkt,
                    "net_pnl": pnl,
                    "funding_pnl": pnl / 2,
                    "price_pnl": pnl / 2,
                    "cost_pnl": 0.0,
                    "turnover": 1.0,
                }
            )
    pl.DataFrame(bt_rows).write_parquet(d / "study3_sc_backtest.parquet")

    pl.DataFrame(
        {
            "strategy": ["short-only-daily"],
            "net_total_return": [-0.70],
            "return_ci_low": [-1.43],
            "return_ci_high": [-0.002],
            "sharpe": [-2.654],
            "sharpe_ci_low": [-5.625],
            "sharpe_ci_high": [-0.007],
            "funding_pnl": [0.185],
            "price_pnl": [-0.838],
            "cost_pnl": [-0.047],
            "max_drawdown": [-0.8],
            "rebalance_count": [40],
            "markets_entered": [2],
        }
    ).write_parquet(d / "study3_sc_summary.parquet")

    fills = []
    for mkt in ["xyz:AAA", "km:BBB"]:
        for seg in ["RTH", "off-hours"]:
            for i in range(10):
                fills.append(
                    {
                        "market": mkt,
                        "segment": seg,
                        "net_markout_1s_bps": -1.0 - i * 0.1,
                        "stale_1s": i == 9,
                        "net_markout_30s_bps": -2.0 - i * 0.1,
                        "stale_30s": False,
                    }
                )
    pl.DataFrame(fills).write_parquet(d / "study1_fills_l2.parquet")

    monkeypatch.setenv("CHARYBDIS_DATA_DIR", str(d))
    # datasets module caches by mtime; clear between tests
    from charybdis.console import datasets

    datasets._PAYLOAD_CACHE.clear()
    return d
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_console_datasets.py`:

```python
from __future__ import annotations

import polars as pl
import pytest
from fastapi.testclient import TestClient

from charybdis.console import datasets
from charybdis.console.server import create_app


def test_list_datasets(console_data_dir):
    names = {d["name"] for d in datasets.list_datasets()}
    assert "study3_candles_1h" in names
    assert "study3_sc_backtest" in names
    entry = next(d for d in datasets.list_datasets() if d["name"] == "study3_candles_1h")
    assert entry["columns"] == 12
    assert entry["size_bytes"] > 0


def test_dataset_path_rejects_traversal(console_data_dir):
    with pytest.raises(ValueError):
        datasets.dataset_path("../evil")
    with pytest.raises(ValueError):
        datasets.dataset_path("a/b")


def test_scan_dataset_missing_raises(console_data_dir):
    with pytest.raises(FileNotFoundError):
        datasets.scan_dataset("nope")


def test_scan_dataset_reads(console_data_dir):
    df = datasets.scan_dataset("study3_candles_1h").collect()
    assert df.height == 120
    assert "close" in df.columns


def test_cached_payload_reuses_until_mtime_changes(console_data_dir):
    calls = []

    def build():
        calls.append(1)
        return {"x": 1}

    assert datasets.cached_payload("k", "study3_candles_1h", build) == {"x": 1}
    assert datasets.cached_payload("k", "study3_candles_1h", build) == {"x": 1}
    assert len(calls) == 1


def test_health_and_datasets_endpoints(console_data_dir):
    client = TestClient(create_app())
    assert client.get("/api/health").json() == {"status": "ok"}
    body = client.get("/api/datasets").json()
    assert any(d["name"] == "study1_fills_l2" for d in body)


def test_datasets_endpoint_empty_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARYBDIS_DATA_DIR", str(tmp_path / "absent"))
    client = TestClient(create_app())
    assert client.get("/api/datasets").json() == []
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_datasets.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'charybdis.console'`

- [ ] **Step 5: Implement the datasets module**

Create `charybdis/console/__init__.py` (empty file).

Create `charybdis/console/datasets.py`:

```python
"""Read-only access to the report parquet tables in data/reports/."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import polars as pl

# key -> (mtime, payload); cleared by tests via _PAYLOAD_CACHE.clear()
_PAYLOAD_CACHE: dict[str, tuple[float, Any]] = {}


def data_dir() -> Path:
    env = os.environ.get("CHARYBDIS_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "reports"


def dataset_path(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"invalid dataset name: {name}")
    return data_dir() / f"{name}.parquet"


def dataset_exists(name: str) -> bool:
    return dataset_path(name).is_file()


def list_datasets() -> list[dict]:
    root = data_dir()
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.glob("*.parquet")):
        stat = p.stat()
        out.append(
            {
                "name": p.stem,
                "columns": len(pl.read_parquet_schema(p)),
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return out


def scan_dataset(name: str) -> pl.LazyFrame:
    p = dataset_path(name)
    if not p.is_file():
        raise FileNotFoundError(name)
    return pl.scan_parquet(p)


def cached_payload(key: str, name: str, builder: Callable[[], Any]) -> Any:
    """Cache a computed payload, invalidated when the backing parquet's mtime changes."""
    mtime = dataset_path(name).stat().st_mtime
    hit = _PAYLOAD_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    payload = builder()
    _PAYLOAD_CACHE[key] = (mtime, payload)
    return payload
```

- [ ] **Step 6: Implement the app factory and entry point**

Create `charybdis/console/server.py`:

```python
"""FastAPI app for the charybdis research console."""
from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from charybdis.console import datasets


def create_app() -> FastAPI:
    app = FastAPI(title="charybdis console", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/datasets")
    def list_datasets() -> list[dict]:
        return datasets.list_datasets()

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    dist = Path(__file__).resolve().parents[2] / "console" / "dist"
    if not dist.is_dir():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="charybdis research console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_datasets.py -q` then `uv run pytest -q`
Expected: all PASS (new file and full suite).

- [ ] **Step 8: Smoke-test the entry point**

Run: `uv run charybdis-console --help`
Expected: prints usage with `--host` and `--port`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock charybdis/console tests/conftest.py tests/test_console_datasets.py
git commit -m "feat(console): backend skeleton — datasets module, app factory, charybdis-console entry"
```

---

### Task 2: Data browser API — schema + paginated/filtered rows

**Files:**
- Create: `charybdis/console/tables.py`
- Modify: `charybdis/console/server.py` (add two routes)
- Test: `tests/test_console_tables.py`

**Interfaces:**
- Consumes: `datasets.scan_dataset`, `datasets.dataset_path`.
- Produces:
  - `charybdis.console.tables.dataset_schema(name: str) -> dict` — `{"name": str, "columns": [{"name": str, "dtype": str}]}`
  - `charybdis.console.tables.dataset_rows(name, page, page_size, sort, order, filters) -> dict` — `{"total": int, "page": int, "page_size": int, "columns": [str], "rows": [[json-safe]]}`
  - Routes: `GET /api/datasets/{name}/schema`, `GET /api/datasets/{name}/rows?page=&page_size=&sort=&order=&filter=col:op:value` (filter repeatable; ops: `eq, ne, gt, ge, lt, le, contains`)
  - `charybdis.console.tables.json_value(v) -> Any` — datetime/date → ISO string, NaN/±inf → None, lists converted element-wise (reused by later tasks)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_tables.py`:

```python
from __future__ import annotations

import math

from fastapi.testclient import TestClient

from charybdis.console.server import create_app
from charybdis.console.tables import json_value


def _client():
    return TestClient(create_app())


def test_schema(console_data_dir):
    body = _client().get("/api/datasets/study3_candles_1h/schema").json()
    assert body["name"] == "study3_candles_1h"
    cols = {c["name"]: c["dtype"] for c in body["columns"]}
    assert cols["close"] == "Float64"
    assert cols["market"] == "String"


def test_schema_missing_dataset_404(console_data_dir):
    r = _client().get("/api/datasets/nope/schema")
    assert r.status_code == 404
    assert "not present" in r.json()["detail"]


def test_rows_pagination(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?page=2&page_size=50").json()
    assert r["total"] == 120
    assert r["page"] == 2
    assert len(r["rows"]) == 50
    assert r["columns"][0] == "dex"


def test_rows_filter_and_sort(console_data_dir):
    r = _client().get(
        "/api/datasets/study3_candles_1h/rows"
        "?filter=market:eq:xyz%3AAAA&sort=close&order=desc&page_size=5"
    ).json()
    assert r["total"] == 60
    closes = [row[r["columns"].index("close")] for row in r["rows"]]
    assert closes == sorted(closes, reverse=True)


def test_rows_contains_filter(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=market:contains:BBB").json()
    assert r["total"] == 60


def test_rows_numeric_filter(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=v:gt:50").json()
    assert 0 < r["total"] < 120


def test_rows_bad_filter_column_400(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=nope:eq:1")
    assert r.status_code == 400


def test_json_value():
    from datetime import datetime

    assert json_value(datetime(2026, 6, 1)) == "2026-06-01T00:00:00"
    assert json_value(math.nan) is None
    assert json_value(math.inf) is None
    assert json_value([math.nan, 1.0]) == [None, 1.0]
    assert json_value("x") == "x"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_tables.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'charybdis.console.tables'`

- [ ] **Step 3: Implement the tables module**

Create `charybdis/console/tables.py`:

```python
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
```

- [ ] **Step 4: Add the routes to `server.py`**

In `charybdis/console/server.py`, add imports at the top:

```python
from fastapi import FastAPI, HTTPException, Query

from charybdis.console import datasets, tables
```

Inside `create_app()`, after the `list_datasets` route add:

```python
    @app.get("/api/datasets/{name}/schema")
    def dataset_schema(name: str) -> dict:
        _check_present(name)
        return tables.dataset_schema(name)

    @app.get("/api/datasets/{name}/rows")
    def dataset_rows(
        name: str,
        page: int = 1,
        page_size: int = 100,
        sort: str | None = None,
        order: str = "asc",
        filter: list[str] = Query(default=[]),  # noqa: A002
    ) -> dict:
        _check_present(name)
        try:
            return tables.dataset_rows(name, page, page_size, sort, order, filter)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
```

And add a module-level helper (above `create_app`):

```python
def _check_present(name: str) -> None:
    try:
        present = datasets.dataset_exists(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not present:
        raise HTTPException(status_code=404, detail=f"dataset not present: {name}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_tables.py tests/test_console_datasets.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add charybdis/console/tables.py charybdis/console/server.py tests/test_console_tables.py
git commit -m "feat(console): dataset schema + paginated/filtered rows API"
```

---

### Task 3: Indicator registry + seven indicators

**Files:**
- Create: `charybdis/console/indicators.py`
- Test: `tests/test_console_indicators.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure polars).
- Produces:
  - `charybdis.console.indicators.REGISTRY: dict[str, IndicatorSpec]` where `IndicatorSpec` has `name: str`, `params: dict[str, int | float]` (ordered defaults), `display: str` (`"overlay" | "pane"`), `fn: Callable[..., pl.DataFrame]`
  - `charybdis.console.indicators.compute(spec_str: str, ohlcv: pl.DataFrame) -> tuple[IndicatorSpec, pl.DataFrame]` — parses `"ema:20"` / `"macd:12:26:9"` (positional params in declared order, missing → defaults; raises `ValueError` on unknown name/bad params)
  - `charybdis.console.indicators.registry_meta() -> list[dict]` — `[{"name", "params", "display"}]`
  - Indicator fns receive an OHLCV `pl.DataFrame` with columns `open, high, low, close, volume` and return a `pl.DataFrame` of output series (same height)
  - Registered names: `sma, ema, rsi, macd, bbands, vwap, atr`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_indicators.py`:

```python
from __future__ import annotations

import polars as pl
import pytest

from charybdis.console import indicators


def _ohlcv(closes: list[float], highs=None, lows=None, vols=None) -> pl.DataFrame:
    n = len(closes)
    return pl.DataFrame(
        {
            "open": closes,
            "high": highs or [c + 1 for c in closes],
            "low": lows or [c - 1 for c in closes],
            "close": closes,
            "volume": vols or [1.0] * n,
        }
    )


def test_registry_contents():
    assert set(indicators.REGISTRY) == {"sma", "ema", "rsi", "macd", "bbands", "vwap", "atr"}
    assert indicators.REGISTRY["ema"].display == "overlay"
    assert indicators.REGISTRY["rsi"].display == "pane"


def test_sma_golden():
    _, out = indicators.compute("sma:3", _ohlcv([1, 2, 3, 4, 5]))
    assert out["sma_3"].to_list() == [None, None, 2.0, 3.0, 4.0]


def test_ema_golden():
    # period 3 -> alpha 0.5, adjust=False: 1, 1.5, 2.25, 3.125, 4.0625
    _, out = indicators.compute("ema:3", _ohlcv([1, 2, 3, 4, 5]))
    assert out["ema_3"].to_list() == pytest.approx([1.0, 1.5, 2.25, 3.125, 4.0625])


def test_rsi_bounds():
    up = [float(i) for i in range(1, 30)]
    _, out = indicators.compute("rsi:14", _ohlcv(up))
    assert out["rsi_14"][-1] == pytest.approx(100.0)
    down = [float(30 - i) for i in range(1, 30)]
    _, out = indicators.compute("rsi:14", _ohlcv(down))
    assert out["rsi_14"][-1] == pytest.approx(0.0)


def test_macd_constant_is_zero():
    _, out = indicators.compute("macd", _ohlcv([5.0] * 60))
    assert out["macd"][-1] == pytest.approx(0.0)
    assert out["macd_signal"][-1] == pytest.approx(0.0)
    assert out["macd_hist"][-1] == pytest.approx(0.0)
    assert set(out.columns) == {"macd", "macd_signal", "macd_hist"}


def test_bbands_constant_collapses():
    _, out = indicators.compute("bbands:5:2", _ohlcv([7.0] * 10))
    assert out["bb_mid_5"][-1] == pytest.approx(7.0)
    assert out["bb_upper_5"][-1] == pytest.approx(7.0)
    assert out["bb_lower_5"][-1] == pytest.approx(7.0)


def test_vwap_equal_volume_is_cumulative_mean_of_typical():
    df = _ohlcv([2.0, 4.0], highs=[3.0, 5.0], lows=[1.0, 3.0])
    # typical prices: 2.0 and 4.0 -> vwap: 2.0, 3.0
    _, out = indicators.compute("vwap", df)
    assert out["vwap"].to_list() == pytest.approx([2.0, 3.0])


def test_atr_golden():
    df = _ohlcv([9.5, 10.5], highs=[10.0, 11.0], lows=[9.0, 10.0])
    # TR: [1.0, max(1.0, |11-9.5|, |10-9.5|)=1.5]; alpha=0.5 -> [1.0, 1.25]
    _, out = indicators.compute("atr:2", df)
    assert out["atr_2"].to_list() == pytest.approx([1.0, 1.25])


def test_compute_parsing_errors():
    with pytest.raises(ValueError):
        indicators.compute("nope:3", _ohlcv([1, 2, 3]))
    with pytest.raises(ValueError):
        indicators.compute("sma:abc", _ohlcv([1, 2, 3]))


def test_registry_meta_shape():
    meta = {m["name"]: m for m in indicators.registry_meta()}
    assert meta["macd"]["params"] == {"fast": 12, "slow": 26, "signal": 9}
    assert meta["vwap"]["params"] == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_indicators.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'charybdis.console.indicators'`

- [ ] **Step 3: Implement the indicators module**

Create `charybdis/console/indicators.py`:

```python
"""Technical-indicator registry. Add an indicator = write one decorated function.

Indicator functions take an OHLCV DataFrame (open, high, low, close, volume)
and their params, and return a DataFrame of output series (same height).
`display` controls Chart Lab placement: "overlay" on the price chart,
"pane" in its own sub-chart.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import polars as pl

REGISTRY: dict[str, "IndicatorSpec"] = {}


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    params: dict[str, int | float]  # ordered defaults; order = positional parse order
    display: str  # "overlay" | "pane"
    fn: Callable[..., pl.DataFrame]


def indicator(name: str, params: dict[str, int | float], display: str):
    def deco(fn: Callable[..., pl.DataFrame]):
        REGISTRY[name] = IndicatorSpec(name, params, display, fn)
        return fn

    return deco


def registry_meta() -> list[dict]:
    return [
        {"name": s.name, "params": s.params, "display": s.display}
        for s in REGISTRY.values()
    ]


def compute(spec_str: str, ohlcv: pl.DataFrame) -> tuple[IndicatorSpec, pl.DataFrame]:
    parts = spec_str.split(":")
    name, raw_params = parts[0], parts[1:]
    spec = REGISTRY.get(name)
    if spec is None:
        raise ValueError(f"unknown indicator: {name}")
    if len(raw_params) > len(spec.params):
        raise ValueError(f"{name}: too many params (max {len(spec.params)})")
    kwargs: dict[str, int | float] = dict(spec.params)
    for (pname, default), raw in zip(spec.params.items(), raw_params):
        try:
            kwargs[pname] = type(default)(raw)
        except ValueError as e:
            raise ValueError(f"{name}: bad param {pname}={raw!r}") from e
    return spec, spec.fn(ohlcv, **kwargs)


def _ema(s: pl.Series, period: int) -> pl.Series:
    return s.ewm_mean(alpha=2.0 / (period + 1.0), adjust=False)


def _wilder(s: pl.Series, period: int) -> pl.Series:
    return s.ewm_mean(alpha=1.0 / period, adjust=False)


@indicator("sma", params={"period": 20}, display="overlay")
def sma(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    return pl.DataFrame({f"sma_{period}": ohlcv["close"].rolling_mean(window_size=period)})


@indicator("ema", params={"period": 20}, display="overlay")
def ema(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    return pl.DataFrame({f"ema_{period}": _ema(ohlcv["close"], period)})


@indicator("rsi", params={"period": 14}, display="pane")
def rsi(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    delta = ohlcv["close"].diff().fill_null(0.0)
    gain = _wilder(delta.clip(lower_bound=0.0), period)
    loss = _wilder((-delta).clip(lower_bound=0.0), period)
    return pl.DataFrame({f"rsi_{period}": 100.0 * gain / (gain + loss)})


@indicator("macd", params={"fast": 12, "slow": 26, "signal": 9}, display="pane")
def macd(ohlcv: pl.DataFrame, fast: int, slow: int, signal: int) -> pl.DataFrame:
    line = _ema(ohlcv["close"], fast) - _ema(ohlcv["close"], slow)
    sig = _ema(line, signal)
    return pl.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


@indicator("bbands", params={"period": 20, "mult": 2.0}, display="overlay")
def bbands(ohlcv: pl.DataFrame, period: int, mult: float) -> pl.DataFrame:
    mid = ohlcv["close"].rolling_mean(window_size=period)
    sd = ohlcv["close"].rolling_std(window_size=period)
    return pl.DataFrame(
        {
            f"bb_mid_{period}": mid,
            f"bb_upper_{period}": mid + mult * sd,
            f"bb_lower_{period}": mid - mult * sd,
        }
    )


@indicator("vwap", params={}, display="overlay")
def vwap(ohlcv: pl.DataFrame) -> pl.DataFrame:
    tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3.0
    pv = (tp * ohlcv["volume"]).cum_sum()
    return pl.DataFrame({"vwap": pv / ohlcv["volume"].cum_sum()})


@indicator("atr", params={"period": 14}, display="pane")
def atr(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    prev_close = ohlcv["close"].shift(1)
    tr = pl.DataFrame(
        {
            "a": ohlcv["high"] - ohlcv["low"],
            "b": (ohlcv["high"] - prev_close).abs(),
            "c": (ohlcv["low"] - prev_close).abs(),
        }
    ).select(pl.max_horizontal("a", "b", "c").alias("tr"))["tr"]
    return pl.DataFrame({f"atr_{period}": _wilder(tr, period)})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_indicators.py -q`
Expected: all PASS. If `test_bbands_constant_collapses` fails on the first `period-1` nulls, that is expected behavior for the last-row assertions used here; only debug if the LAST values differ.

- [ ] **Step 5: Commit**

```bash
git add charybdis/console/indicators.py tests/test_console_indicators.py
git commit -m "feat(console): indicator registry with sma/ema/rsi/macd/bbands/vwap/atr + golden tests"
```

---

### Task 4: Candles API

**Files:**
- Create: `charybdis/console/candles.py`
- Modify: `charybdis/console/server.py` (add three routes)
- Test: `tests/test_console_candles.py`

**Interfaces:**
- Consumes: `datasets.scan_dataset` / `dataset_exists`, `indicators.compute` / `registry_meta`.
- Produces:
  - `charybdis.console.candles.SOURCES: dict[str, dict]` — `{"study3_1h": {"dataset": "study3_candles_1h", "interval": "1h"}, "study3_1d": {"dataset": "study3_candles_1d", "interval": "1d"}}` (extending sources = adding an entry)
  - `charybdis.console.candles.list_sources() -> list[dict]` — `[{"id", "interval", "markets": [str]}]`, absent datasets omitted
  - `charybdis.console.candles.get_candles(source: str, market: str, ind: list[str]) -> dict` — `{"source", "market", "interval", "time": [unix_sec], "open": [...], "high": [...], "low": [...], "close": [...], "volume": [...], "indicators": [{"id", "name", "display", "series": {col: [float|None]}}]}` (raises `KeyError` on unknown source, `FileNotFoundError` if dataset absent, `ValueError` if market has no rows or indicator spec bad)
  - Routes: `GET /api/indicators`, `GET /api/candles/sources`, `GET /api/candles?source=&market=&ind=` (`ind` = comma-joined specs, optional)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_candles.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_indicators_endpoint(console_data_dir):
    body = _client().get("/api/indicators").json()
    names = {m["name"] for m in body}
    assert {"sma", "ema", "rsi", "macd", "bbands", "vwap", "atr"} <= names


def test_sources_lists_only_present(console_data_dir):
    body = _client().get("/api/candles/sources").json()
    ids = {s["id"] for s in body}
    assert ids == {"study3_1h"}  # fixture has no 1d file
    src = body[0]
    assert src["interval"] == "1h"
    assert src["markets"] == ["km:BBB", "xyz:AAA"]


def test_candles_payload(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=ema:5,rsi:14").json()
    assert r["market"] == "xyz:AAA"
    assert len(r["time"]) == 60
    assert len(r["close"]) == 60
    assert r["time"] == sorted(r["time"])
    inds = {i["id"]: i for i in r["indicators"]}
    assert inds["ema:5"]["display"] == "overlay"
    assert "ema_5" in inds["ema:5"]["series"]
    assert len(inds["ema:5"]["series"]["ema_5"]) == 60
    assert inds["rsi:14"]["display"] == "pane"


def test_candles_unknown_source_404(console_data_dir):
    assert _client().get("/api/candles?source=nope&market=x").status_code == 404


def test_candles_unknown_market_404(console_data_dir):
    assert (
        _client().get("/api/candles?source=study3_1h&market=xyz%3AZZZ").status_code == 404
    )


def test_candles_bad_indicator_400(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=nope:1")
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_candles.py -q`
Expected: FAIL (`/api/indicators` 404 — routes don't exist yet).

- [ ] **Step 3: Implement the candles module**

Create `charybdis/console/candles.py`:

```python
"""Candle sources for the Chart Lab. Add a source = add a SOURCES entry."""
from __future__ import annotations

import polars as pl

from charybdis.console import datasets, indicators
from charybdis.console.tables import json_value

SOURCES: dict[str, dict] = {
    "study3_1h": {"dataset": "study3_candles_1h", "interval": "1h"},
    "study3_1d": {"dataset": "study3_candles_1d", "interval": "1d"},
}


def list_sources() -> list[dict]:
    out = []
    for sid, cfg in SOURCES.items():
        if not datasets.dataset_exists(cfg["dataset"]):
            continue
        markets = (
            datasets.scan_dataset(cfg["dataset"])
            .select(pl.col("market").unique().sort())
            .collect()["market"]
            .to_list()
        )
        out.append({"id": sid, "interval": cfg["interval"], "markets": markets})
    return out


def get_candles(source: str, market: str, ind: list[str]) -> dict:
    cfg = SOURCES[source]  # KeyError -> 404 in route
    df = (
        datasets.scan_dataset(cfg["dataset"])
        .filter(pl.col("market") == market)
        .sort("open_time_ms")
        .select(["open_time_ms", "open", "high", "low", "close", "v"])
        .collect()
    )
    if df.height == 0:
        raise ValueError(f"no rows for market {market!r} in {source}")
    ohlcv = df.rename({"v": "volume"}).select(["open", "high", "low", "close", "volume"])
    payload = {
        "source": source,
        "market": market,
        "interval": cfg["interval"],
        "time": (df["open_time_ms"] // 1000).to_list(),
        "open": df["open"].to_list(),
        "high": df["high"].to_list(),
        "low": df["low"].to_list(),
        "close": df["close"].to_list(),
        "volume": df["volume" if "volume" in df.columns else "v"].to_list(),
        "indicators": [],
    }
    for spec_str in ind:
        spec, out = indicators.compute(spec_str, ohlcv)
        payload["indicators"].append(
            {
                "id": spec_str,
                "name": spec.name,
                "display": spec.display,
                "series": {c: [json_value(v) for v in out[c].to_list()] for c in out.columns},
            }
        )
    return payload
```

- [ ] **Step 4: Add the routes to `server.py`**

Add to the imports in `charybdis/console/server.py`:

```python
from charybdis.console import candles, datasets, indicators, tables
```

Inside `create_app()` add:

```python
    @app.get("/api/indicators")
    def indicator_registry() -> list[dict]:
        return indicators.registry_meta()

    @app.get("/api/candles/sources")
    def candle_sources() -> list[dict]:
        return candles.list_sources()

    @app.get("/api/candles")
    def get_candles(source: str, market: str, ind: str = "") -> dict:
        specs = [s for s in ind.split(",") if s]
        try:
            return candles.get_candles(source, market, specs)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source: {source}")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"dataset not present: {e}")
        except ValueError as e:
            detail = str(e)
            status = 404 if "no rows" in detail else 400
            raise HTTPException(status_code=status, detail=detail)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_candles.py -q` then `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Sanity-check against the real data**

Run: `uv run python -c "
from charybdis.console import candles
srcs = candles.list_sources()
print([s['id'] for s in srcs])
p = candles.get_candles('study3_1h', srcs[0]['markets'][0], ['ema:20','rsi:14'])
print(p['market'], len(p['time']), [i['id'] for i in p['indicators']])
"`
Expected: prints both source ids, a market name, a row count in the hundreds+, and the two indicator ids.

- [ ] **Step 7: Commit**

```bash
git add charybdis/console/candles.py charybdis/console/server.py tests/test_console_candles.py
git commit -m "feat(console): candles API with pluggable sources and indicator computation"
```

---

### Task 5: Backtests API

**Files:**
- Create: `charybdis/console/backtests.py`
- Modify: `charybdis/console/server.py` (add two routes)
- Test: `tests/test_console_backtests.py`

**Interfaces:**
- Consumes: `datasets.scan_dataset` / `dataset_exists` / `cached_payload`, `tables.json_value`.
- Produces:
  - `charybdis.console.backtests.PERIOD_RETURN_LOADERS: dict[str, Callable[[str], pl.DataFrame]]` — source id → loader returning DataFrame `[time: datetime, ret: float]` sorted by time. V1 entry: `"study3-carry"`. Registering a new backtest = adding one loader + one entry in `_list_strategies`.
  - `charybdis.console.backtests.list_backtests() -> list[dict]` — `[{"id": "study3-carry:<strategy>", "source": "study3-carry", "strategy", "title"}]`
  - `charybdis.console.backtests.get_backtest(bt_id: str) -> dict` — `{"id", "title", "stats": {"total_return", "sharpe", "max_drawdown", "periods", "start", "end"}, "equity": [{"t": unix_sec, "v": float}], "drawdown": [...], "rolling_sharpe": [...], "monthly": [{"ym": "2026-06", "ret": float}], "summary": dict | None}` (raises `KeyError` unknown id, `FileNotFoundError` absent dataset)
  - Routes: `GET /api/backtests`, `GET /api/backtests/{bt_id}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_backtests.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_list_backtests(console_data_dir):
    body = _client().get("/api/backtests").json()
    ids = {b["id"] for b in body}
    assert "study3-carry:short-only-daily" in ids
    entry = body[0]
    assert entry["source"] == "study3-carry"
    assert entry["strategy"] == "short-only-daily"


def test_get_backtest_detail(console_data_dir):
    r = _client().get("/api/backtests/study3-carry:short-only-daily").json()
    assert r["stats"]["periods"] == 40
    assert len(r["equity"]) == 40
    # equity is the cumulative sum of period returns
    assert r["equity"][-1]["v"] != 0
    # drawdown is <= 0 everywhere
    assert all(p["v"] <= 1e-12 for p in r["drawdown"])
    assert r["stats"]["max_drawdown"] <= 0
    # monthly buckets cover jun+jul 2026 (40 daily periods from 2026-06-01)
    yms = [m["ym"] for m in r["monthly"]]
    assert yms == ["2026-06", "2026-07"]
    # sc_summary row is merged
    assert r["summary"]["sharpe"] == -2.654


def test_get_backtest_unknown_404(console_data_dir):
    assert _client().get("/api/backtests/nope:x").status_code == 404


def test_backtests_empty_when_dataset_absent(console_data_dir):
    (console_data_dir / "study3_sc_backtest.parquet").unlink()
    assert _client().get("/api/backtests").json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_backtests.py -q`
Expected: FAIL (404 route not found on `/api/backtests`).

- [ ] **Step 3: Implement the backtests module**

Create `charybdis/console/backtests.py`:

```python
"""Generic backtest viewer backend.

A backtest source is a loader producing per-period returns [time, ret].
Register new backtests by adding a loader to PERIOD_RETURN_LOADERS and a
strategy lister to _STRATEGY_LISTERS.
"""
from __future__ import annotations

import math
from typing import Callable

import polars as pl

from charybdis.console import datasets
from charybdis.console.tables import json_value

_ROLLING_WINDOW = 30
_SECONDS_PER_YEAR = 365 * 24 * 3600


def _load_study3_carry(strategy: str) -> pl.DataFrame:
    return (
        datasets.scan_dataset("study3_sc_backtest")
        .filter(pl.col("strategy") == strategy)
        .group_by("rebalance_time")
        .agg(pl.col("net_pnl").sum().alias("ret"))
        .sort("rebalance_time")
        .rename({"rebalance_time": "time"})
        .collect()
    )


def _list_study3_strategies() -> list[str]:
    if not datasets.dataset_exists("study3_sc_backtest"):
        return []
    return (
        datasets.scan_dataset("study3_sc_backtest")
        .select(pl.col("strategy").unique().sort())
        .collect()["strategy"]
        .to_list()
    )


PERIOD_RETURN_LOADERS: dict[str, Callable[[str], pl.DataFrame]] = {
    "study3-carry": _load_study3_carry,
}

_STRATEGY_LISTERS: dict[str, Callable[[], list[str]]] = {
    "study3-carry": _list_study3_strategies,
}

_TITLES = {"study3-carry": "Study 3 — funding carry"}


def list_backtests() -> list[dict]:
    out = []
    for source, lister in _STRATEGY_LISTERS.items():
        for strategy in lister():
            out.append(
                {
                    "id": f"{source}:{strategy}",
                    "source": source,
                    "strategy": strategy,
                    "title": f"{_TITLES[source]} · {strategy}",
                }
            )
    return out


def _summary_row(source: str, strategy: str) -> dict | None:
    if source != "study3-carry" or not datasets.dataset_exists("study3_sc_summary"):
        return None
    df = (
        datasets.scan_dataset("study3_sc_summary")
        .filter(pl.col("strategy") == strategy)
        .collect()
    )
    if df.height == 0:
        return None
    return {k: json_value(v) for k, v in df.row(0, named=True).items()}


def get_backtest(bt_id: str) -> dict:
    source, _, strategy = bt_id.partition(":")
    loader = PERIOD_RETURN_LOADERS[source]  # KeyError -> 404 in route
    df = loader(strategy)
    if df.height == 0:
        raise KeyError(bt_id)

    times = [int(t.timestamp()) for t in df["time"].to_list()]
    rets = df["ret"].to_list()

    equity, dd, peak, acc = [], [], -math.inf, 0.0
    for r in rets:
        acc += r
        peak = max(peak, acc)
        equity.append(acc)
        dd.append(acc - peak)

    dt = _median_dt_seconds(times)
    ppy = _SECONDS_PER_YEAR / dt if dt else 0.0
    rolling = _rolling_sharpe(rets, ppy)

    monthly = (
        df.group_by(pl.col("time").dt.strftime("%Y-%m").alias("ym"))
        .agg(pl.col("ret").sum())
        .sort("ym")
    )

    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    sharpe = mean / math.sqrt(var) * math.sqrt(ppy) if var > 0 else None

    return {
        "id": bt_id,
        "title": f"{_TITLES.get(source, source)} · {strategy}",
        "stats": {
            "total_return": equity[-1],
            "sharpe": json_value(sharpe) if sharpe is not None else None,
            "max_drawdown": min(dd),
            "periods": len(rets),
            "start": times[0],
            "end": times[-1],
        },
        "equity": [{"t": t, "v": v} for t, v in zip(times, equity)],
        "drawdown": [{"t": t, "v": v} for t, v in zip(times, dd)],
        "rolling_sharpe": [
            {"t": t, "v": v} for t, v in zip(times, rolling) if v is not None
        ],
        "monthly": [{"ym": ym, "ret": r} for ym, r in monthly.rows()],
        "summary": _summary_row(source, strategy),
    }


def _median_dt_seconds(times: list[int]) -> float:
    if len(times) < 2:
        return 0.0
    diffs = sorted(b - a for a, b in zip(times, times[1:]))
    return float(diffs[len(diffs) // 2])


def _rolling_sharpe(rets: list[float], ppy: float) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(rets)):
        if i + 1 < _ROLLING_WINDOW:
            out.append(None)
            continue
        window = rets[i + 1 - _ROLLING_WINDOW : i + 1]
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
        out.append(mean / math.sqrt(var) * math.sqrt(ppy) if var > 0 else None)
    return out
```

- [ ] **Step 4: Add the routes to `server.py`**

Add `backtests` to the console imports, then inside `create_app()`:

```python
    @app.get("/api/backtests")
    def list_backtests() -> list[dict]:
        return backtests.list_backtests()

    @app.get("/api/backtests/{bt_id}")
    def get_backtest(bt_id: str) -> dict:
        try:
            return backtests.get_backtest(bt_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown backtest: {bt_id}")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"dataset not present: {e}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_backtests.py -q` then `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 6: Sanity-check against the real data**

Run: `uv run python -c "
from charybdis.console import backtests
bts = backtests.list_backtests()
print([b['id'] for b in bts])
d = backtests.get_backtest('study3-carry:short-only-daily')
print(d['stats'], len(d['equity']), d['summary']['net_total_return'])
"`
Expected: six strategy ids; stats dict with a total_return near -0.70 for short-only-daily; summary net_total_return ≈ -0.70.

- [ ] **Step 7: Commit**

```bash
git add charybdis/console/backtests.py charybdis/console/server.py tests/test_console_backtests.py
git commit -m "feat(console): generic backtest API with study3 carry as first source"
```

---

### Task 6: Findings + Study 1 markout endpoints

**Files:**
- Create: `charybdis/console/findings.yaml`
- Create: `charybdis/console/findings.py`
- Create: `charybdis/console/study1.py`
- Modify: `charybdis/console/server.py` (add two routes)
- Test: `tests/test_console_findings_study1.py`

**Interfaces:**
- Consumes: `datasets.scan_dataset` / `dataset_path` / `cached_payload`, `tables.json_value`.
- Produces:
  - `charybdis.console.findings.load_findings() -> dict` — parsed `findings.yaml`
  - `charybdis.console.study1.markout_summary() -> dict` — `{"horizons": [str], "markets": [str], "segments": [str], "cells": [{"market", "segment", "horizon", "mean_bps": float|None, "n": int}]}` (horizons discovered by regex `net_markout_(\w+)_bps`, stale rows excluded, cached by mtime)
  - Routes: `GET /api/findings`, `GET /api/study1/markout` (404 when `study1_fills_l2` absent)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_console_findings_study1.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_findings_endpoint(console_data_dir):
    body = _client().get("/api/findings").json()
    ids = [s["id"] for s in body["studies"]]
    assert ids == ["study1", "study2", "study3"]
    s3 = body["studies"][2]
    assert s3["verdict"]
    assert s3["numbers"]
    assert s3["page"].startswith("/")


def test_study1_markout(console_data_dir):
    body = _client().get("/api/study1/markout").json()
    assert body["horizons"] == ["1s", "30s"]  # fixture has these two families
    assert set(body["segments"]) == {"RTH", "off-hours"}
    assert set(body["markets"]) == {"xyz:AAA", "km:BBB"}
    cell = next(
        c
        for c in body["cells"]
        if c["market"] == "xyz:AAA" and c["segment"] == "RTH" and c["horizon"] == "1s"
    )
    # fixture: 10 rows, one stale_1s row excluded -> n=9, mean of -1.0..-1.8
    assert cell["n"] == 9
    assert abs(cell["mean_bps"] - (-1.4)) < 1e-9


def test_study1_markout_absent_404(console_data_dir):
    (console_data_dir / "study1_fills_l2.parquet").unlink()
    assert _client().get("/api/study1/markout").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_console_findings_study1.py -q`
Expected: FAIL (404 on `/api/findings` — route missing).

- [ ] **Step 3: Write the curated findings file**

Create `charybdis/console/findings.yaml` (content is curated from `docs/reports/summary_studies_1_2_2026-07-09.md` and `docs/reports/summary_study3_2026-07-10.md` — copy verbatim):

```yaml
studies:
  - id: study1
    title: "Study 1 — Off-hours maker markout"
    date: "2026-07-09"
    verdict: "NULL — off-hours passive-maker markout is not better than RTH"
    summary: >-
      Net 30s passive-maker markout is negative in every market and session.
      Off-hours CIs overlap RTH in 8/8 markets; the only separations are two
      weekend cells better than RTH by under 0.1 bps. The L2 fill rule is an
      optimistic upper bound.
    numbers:
      - { label: "Simulated fills", value: "2,204,391 across 694 market-days" }
      - { label: "xyz:SP500 net 30s (RTH)", value: "-2.00 bps [-2.03, -1.97]" }
      - { label: "Off-hours vs RTH", value: "CI overlap in 8/8 markets" }
      - { label: "Assumed maker fee", value: "1.5 bps, 60s quote-age ceiling" }
    page: "/studies-1-2"
    report: "docs/reports/study1_offhours_markout_2026-07-09.md"
  - id: study2
    title: "Study 2 — Forced-flow proxy vs baseline"
    date: "2026-07-09"
    verdict: "NULL (confounded) — forced-flow markout indistinguishable from baseline"
    summary: >-
      No confirmed liquidations exist in HLSYSTEMEVENTS (0 of 1,070,342 rows);
      all 2,573 events are heuristic proxy tags on SKHX/SMSN. Pooled 30s
      forced-flow markout -1.56 bps vs baseline -1.79 bps, CIs overlap.
      39.5% of windows dropped after 2026-06-18 quote poisoning; the
      comparison is confounded and conservative.
    numbers:
      - { label: "Proxy events", value: "1,367 SKHX + 1,206 SMSN (0 confirmed liq.)" }
      - { label: "Pooled forced-flow 30s", value: "-1.56 bps [-2.01, -1.13]" }
      - { label: "Pooled baseline 30s", value: "-1.79 bps [-3.11, -0.85]" }
      - { label: "Reversion half-life", value: "116.8 s mean (1,312 events)" }
    page: "/studies-1-2"
    report: "docs/reports/study2_forced_flow_2026-07-09.md"
  - id: study3
    title: "Study 3 — HIP-3 funding deep dive"
    date: "2026-07-10"
    verdict: "Funding is large but efficiently priced — no carry, no clock edge, no spread arb"
    summary: >-
      Mean APRs reach 203% (xyz:SHAZ) but persistence is short: 0/183 markets
      pass the 24h half-life bar (median 1.3h, max 9.9h). Naive carry loses
      badly (short-only-daily -70%); the hedged variant is NULL. Funding-clock
      brackets do not separate in 12/12 cells. Twin-basis swamps the funding
      edge in 57/57 cross-dex pairs. Funding does not time forced flow.
    numbers:
      - { label: "Top mean APR", value: "xyz:SHAZ 203.2% [123.4, 284.2]" }
      - { label: "Carry-relevant markets", value: "0 of 183 (24h half-life bar)" }
      - { label: "short-only-daily net", value: "-70.0% [-143.3, -0.2]" }
      - { label: "single-name-hedged net", value: "+3.2% [-15.7, +19.2] (NULL)" }
      - { label: "Cross-dex pairs viable", value: "0 of 57 (basis > funding edge)" }
    page: "/study-3"
    report: "docs/reports/summary_study3_2026-07-10.md"
```

- [ ] **Step 4: Implement the findings and study1 modules**

Create `charybdis/console/findings.py`:

```python
"""Curated overview content, hand-written in findings.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


def load_findings() -> dict:
    return yaml.safe_load((Path(__file__).with_name("findings.yaml")).read_text())
```

Create `charybdis/console/study1.py`:

```python
"""Study 1 markout aggregation. study1_fills_l2 is ~274 MB: lazy scan, cached payload."""
from __future__ import annotations

import re

import polars as pl

from charybdis.console import datasets
from charybdis.console.tables import json_value

_HORIZON_RE = re.compile(r"^net_markout_(\w+)_bps$")
_DATASET = "study1_fills_l2"


def _horizon_seconds(h: str) -> float:
    m = re.match(r"([0-9.]+)s$", h)
    return float(m.group(1)) if m else float("inf")


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
```

- [ ] **Step 5: Add the routes to `server.py`**

Add `findings, study1` to the console imports, then inside `create_app()`:

```python
    @app.get("/api/findings")
    def get_findings() -> dict:
        return findings.load_findings()

    @app.get("/api/study1/markout")
    def study1_markout() -> dict:
        _check_present("study1_fills_l2")
        return study1.markout_summary()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_console_findings_study1.py -q` then `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 7: Sanity-check study1 aggregation against the real 274 MB file**

Run: `uv run python -c "
from charybdis.console import study1
s = study1.markout_summary()
print(s['horizons'], len(s['markets']), s['segments'], len(s['cells']))
"`
Expected: several horizons (at least 1s/5s/30s), 8 markets, RTH/off-hours/weekend-style segments; completes in seconds.

- [ ] **Step 8: Commit**

```bash
git add charybdis/console/findings.yaml charybdis/console/findings.py charybdis/console/study1.py charybdis/console/server.py tests/test_console_findings_study1.py
git commit -m "feat(console): curated findings endpoint + study1 markout aggregation"
```

---

### Task 7: Frontend skeleton — Vite/React/Tailwind shell, theme, API client, nav

**Files:**
- Create: `console/package.json`, `console/tsconfig.json`, `console/vite.config.ts`, `console/index.html`
- Create: `console/src/main.tsx`, `console/src/index.css`, `console/src/theme.ts`, `console/src/api.ts`, `console/src/ui.tsx`, `console/src/App.tsx`
- Create: `console/src/pages/Overview.tsx`, `Study12.tsx`, `Study3.tsx`, `ChartLab.tsx`, `Backtests.tsx`, `DataBrowser.tsx` (minimal stubs, replaced by Tasks 8–12)
- Modify: `.gitignore` (add console build artifacts), `README.md` (console run instructions)

**Interfaces:**
- Consumes: backend routes from Tasks 1–6.
- Produces (used by all page tasks):
  - `theme.ts`: `export const C = { bg, panel, border, text, muted, accent, up, down, series: string[] }`
  - `api.ts`: `apiGet<T>(path): Promise<T>`, `class ApiError { status: number }`, `useApi<T>(path: string | null): { data?: T; error?: ApiError; loading: boolean }`, plus the TS interfaces `DatasetInfo, SchemaCol, RowsPage, IndicatorMeta, CandleSource, CandlePayload, BacktestEntry, TimePoint, BacktestDetail, Findings, Study1Markout, MarkoutCell`
  - `ui.tsx`: `PageHeader({title, sub?})`, `Card({children, className?})`, `StatCard({label, value, sub?, tone?})`, `EmptyState({error?, note?})`, `Spinner()`, `Select({label, value, options, onChange})`
  - Routes registered in `App.tsx`: `/` Overview, `/studies-1-2` Study12, `/study-3` Study3, `/chart-lab` ChartLab, `/backtests` Backtests, `/data` DataBrowser

- [ ] **Step 1: Scaffold config files**

Create `console/package.json`:

```json
{
  "name": "charybdis-console",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "typecheck": "tsc --noEmit",
    "build": "vite build"
  },
  "dependencies": {
    "echarts": "^5.5.1",
    "lightweight-charts": "^5.0.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^7.1.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.4",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.6.3",
    "vite": "^6.0.0"
  }
}
```

Create `console/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "skipLibCheck": true,
    "noEmit": true,
    "isolatedModules": true
  },
  "include": ["src"]
}
```

Create `console/vite.config.ts`:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': 'http://localhost:8787' },
  },
})
```

Create `console/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>charybdis console</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Run: `cd console && npm install`
Expected: installs cleanly (Node 25 is available).

- [ ] **Step 2: Theme, CSS, API client**

Create `console/src/index.css`:

```css
@import "tailwindcss";

:root {
  color-scheme: dark;
}
html,
body,
#root {
  height: 100%;
}
body {
  background-color: #09090b;
  color: #d4d4d8;
  font-family: ui-sans-serif, system-ui, sans-serif;
}
```

Create `console/src/theme.ts`:

```ts
/** Single source of truth for console colors (dark theme only). */
export const C = {
  bg: '#09090b',
  panel: '#18181b',
  border: '#27272a',
  text: '#d4d4d8',
  muted: '#71717a',
  accent: '#22d3ee',
  up: '#10b981',
  down: '#f43f5e',
  series: ['#22d3ee', '#a78bfa', '#f59e0b', '#34d399', '#f472b6', '#60a5fa', '#facc15', '#fb923c'],
}
```

Create `console/src/api.ts`:

```ts
import { useEffect, useState } from 'react'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, detail)
  }
  return r.json() as Promise<T>
}

export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({
    loading: path !== null,
  })
  useEffect(() => {
    if (path === null) {
      setState({ loading: false })
      return
    }
    let live = true
    setState({ loading: true })
    apiGet<T>(path).then(
      (data) => live && setState({ data, loading: false }),
      (error: ApiError) => live && setState({ error, loading: false }),
    )
    return () => {
      live = false
    }
  }, [path])
  return state
}

export interface DatasetInfo {
  name: string
  columns: number
  size_bytes: number
  mtime: number
}
export interface SchemaCol {
  name: string
  dtype: string
}
export type Cell = string | number | boolean | null
export interface RowsPage {
  total: number
  page: number
  page_size: number
  columns: string[]
  rows: Cell[][]
}
export interface IndicatorMeta {
  name: string
  params: Record<string, number>
  display: 'overlay' | 'pane'
}
export interface CandleSource {
  id: string
  interval: string
  markets: string[]
}
export interface CandlePayload {
  source: string
  market: string
  interval: string
  time: number[]
  open: number[]
  high: number[]
  low: number[]
  close: number[]
  volume: number[]
  indicators: {
    id: string
    name: string
    display: 'overlay' | 'pane'
    series: Record<string, (number | null)[]>
  }[]
}
export interface BacktestEntry {
  id: string
  source: string
  strategy: string
  title: string
}
export interface TimePoint {
  t: number
  v: number
}
export interface BacktestDetail {
  id: string
  title: string
  stats: {
    total_return: number
    sharpe: number | null
    max_drawdown: number
    periods: number
    start: number
    end: number
  }
  equity: TimePoint[]
  drawdown: TimePoint[]
  rolling_sharpe: TimePoint[]
  monthly: { ym: string; ret: number }[]
  summary: Record<string, unknown> | null
}
export interface Findings {
  studies: {
    id: string
    title: string
    date: string
    verdict: string
    summary: string
    numbers: { label: string; value: string }[]
    page: string
    report: string
  }[]
}
export interface MarkoutCell {
  market: string
  segment: string
  horizon: string
  mean_bps: number | null
  n: number
}
export interface Study1Markout {
  horizons: string[]
  markets: string[]
  segments: string[]
  cells: MarkoutCell[]
}
```

- [ ] **Step 3: Shared UI components**

Create `console/src/ui.tsx`:

```tsx
import type { ReactNode } from 'react'
import { ApiError } from './api'

export function PageHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-semibold tracking-tight text-zinc-100">{title}</h1>
      {sub && <p className="mt-1 text-sm text-zinc-500">{sub}</p>}
    </div>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 ${className}`}>
      {children}
    </div>
  )
}

export function StatCard({
  label,
  value,
  sub,
  tone = 'flat',
}: {
  label: string
  value: string
  sub?: string
  tone?: 'up' | 'down' | 'flat'
}) {
  const toneCls =
    tone === 'up' ? 'text-emerald-400' : tone === 'down' ? 'text-rose-400' : 'text-zinc-100'
  return (
    <Card>
      <div className="text-xs uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${toneCls}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </Card>
  )
}

export function EmptyState({ error, note }: { error?: ApiError; note?: string }) {
  const msg =
    error?.status === 404
      ? error.message
      : (error?.message ?? note ?? 'No data available')
  return (
    <Card className="flex min-h-32 items-center justify-center">
      <div className="text-center">
        <div className="text-sm text-zinc-400">{msg}</div>
        {error?.status === 404 && (
          <div className="mt-1 text-xs text-zinc-600">
            This view needs a parquet that is not present in data/reports/.
          </div>
        )}
      </div>
    </Card>
  )
}

export function Spinner() {
  return (
    <div className="flex min-h-32 items-center justify-center">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-700 border-t-cyan-400" />
    </div>
  )
}

export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (v: string) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-zinc-400">
      {label}
      <select
        className="rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-cyan-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}
```

- [ ] **Step 4: App shell, router, page stubs**

Create `console/src/App.tsx`:

```tsx
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import Overview from './pages/Overview'
import Study12 from './pages/Study12'
import Study3 from './pages/Study3'
import ChartLab from './pages/ChartLab'
import Backtests from './pages/Backtests'
import DataBrowser from './pages/DataBrowser'

const NAV = [
  { to: '/', label: 'Overview' },
  { to: '/studies-1-2', label: 'Studies 1–2' },
  { to: '/study-3', label: 'Study 3' },
  { to: '/chart-lab', label: 'Chart Lab' },
  { to: '/backtests', label: 'Backtests' },
  { to: '/data', label: 'Data Browser' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full">
        <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950 p-4">
          <div className="mb-6 px-2">
            <span className="text-sm font-bold tracking-[0.2em] text-cyan-400">CHARYBDIS</span>
            <div className="text-[10px] uppercase tracking-wider text-zinc-600">
              research console
            </div>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === '/'}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm ${
                    isActive
                      ? 'bg-zinc-800/80 font-medium text-zinc-100'
                      : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200'
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="min-w-0 flex-1 overflow-y-auto p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/studies-1-2" element={<Study12 />} />
            <Route path="/study-3" element={<Study3 />} />
            <Route path="/chart-lab" element={<ChartLab />} />
            <Route path="/backtests" element={<Backtests />} />
            <Route path="/data" element={<DataBrowser />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

Create `console/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

Create each of the six page stubs (`console/src/pages/Overview.tsx`, `Study12.tsx`, `Study3.tsx`, `ChartLab.tsx`, `Backtests.tsx`, `DataBrowser.tsx`) with this pattern — replace `Overview` with the page name in each file:

```tsx
import { PageHeader } from '../ui'

export default function Overview() {
  return <PageHeader title="Overview" sub="Coming in a later task." />
}
```

- [ ] **Step 5: Ignore rules and README**

Append to `.gitignore`:

```
# console frontend
console/node_modules/
console/dist/
```

Append to `README.md`:

```markdown
## Research console

Interactive dashboard over `data/reports/*.parquet`.

```bash
cd console && npm install && npm run build && cd ..   # first time / after frontend changes
uv run charybdis-console                              # serves http://localhost:8787
```

Frontend development: `uv run charybdis-console` in one shell, `cd console && npm run dev` in another (Vite proxies `/api`).
```

- [ ] **Step 6: Verify typecheck + build + serving**

Run: `cd console && npm run typecheck && npm run build`
Expected: both succeed; `console/dist/index.html` exists.

Run:

```bash
uv run charybdis-console --port 8899 & SRV=$!
sleep 2
curl -s localhost:8899/api/health
curl -s localhost:8899/ | head -3
kill $SRV
```

Expected: `{"status":"ok"}` and the built `index.html` served at `/`.

- [ ] **Step 7: Commit**

```bash
git add console .gitignore README.md
git commit -m "feat(console): frontend skeleton — Vite/React/Tailwind shell, dark theme, nav, API client"
```

---

### Task 8: Chart primitives — ECharts wrapper + options, lightweight-charts components

**Files:**
- Create: `console/src/charts/EChart.tsx`
- Create: `console/src/charts/options.ts`
- Create: `console/src/charts/CandleChart.tsx`
- Create: `console/src/charts/TimeSeriesChart.tsx`

**Interfaces:**
- Consumes: `theme.ts` `C`.
- Produces (used by Tasks 9–12):
  - `EChart({ option, height? })` — renders any `EChartsOption`, dark-styled, resize-aware
  - `options.ts`: `base: EChartsOption`, `axis()`, `lineOption({categories, series: {name, data}[], yName})`, `scatterOption({points: {x, y, name}[], xName, yName})`, `dotWhisker(groups: {name, color, items: CIItem[]}[], xLabel)` with `CIItem = {label, value, lo, hi}`, `monthlyHeatmap(monthly: {ym, ret}[])`
  - `CandleChart({ time, open, high, low, close, overlays: OverlaySeries[], panes: Pane[], height? })` with `OverlaySeries = {name, values: (number|null)[]}`, `Pane = {name, series: OverlaySeries[]}`
  - `TimeSeriesChart({ points: TimePoint[], height?, percent? })` — baseline area chart (equity/drawdown)

- [ ] **Step 1: ECharts wrapper**

Create `console/src/charts/EChart.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'

export default function EChart({ option, height = 340 }: { option: EChartsOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const key = JSON.stringify(option)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = echarts.init(el, undefined, { renderer: 'canvas' })
    chart.setOption(option)
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
      chart.dispose()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return <div ref={ref} style={{ height }} />
}
```

- [ ] **Step 2: Shared option builders**

Create `console/src/charts/options.ts`:

```ts
import type { EChartsOption, SeriesOption } from 'echarts'
import { C } from '../theme'

export const base: EChartsOption = {
  backgroundColor: 'transparent',
  textStyle: { color: C.text, fontFamily: 'inherit' },
  tooltip: {
    trigger: 'axis',
    backgroundColor: C.panel,
    borderColor: C.border,
    textStyle: { color: C.text },
  },
  grid: { left: 64, right: 24, top: 36, bottom: 44 },
}

export function axis() {
  return {
    axisLine: { lineStyle: { color: C.border } },
    axisTick: { lineStyle: { color: C.border } },
    axisLabel: { color: C.muted },
    splitLine: { lineStyle: { color: C.border } },
    nameTextStyle: { color: C.muted },
  }
}

export function lineOption(cfg: {
  categories: string[]
  series: { name: string; data: (number | null)[] }[]
  yName: string
}): EChartsOption {
  return {
    ...base,
    legend: { textStyle: { color: C.muted }, top: 0 },
    xAxis: { type: 'category', data: cfg.categories, ...axis() },
    yAxis: { type: 'value', name: cfg.yName, ...axis() },
    series: cfg.series.map((s, i) => ({
      name: s.name,
      type: 'line' as const,
      data: s.data,
      smooth: false,
      symbolSize: 6,
      lineStyle: { width: 2 },
      itemStyle: { color: C.series[i % C.series.length] },
    })),
  }
}

export function scatterOption(cfg: {
  points: { x: number; y: number; name: string }[]
  xName: string
  yName: string
}): EChartsOption {
  return {
    ...base,
    tooltip: {
      ...base.tooltip,
      trigger: 'item',
      formatter: (p: unknown) => {
        const q = p as { data: { name: string; value: [number, number] } }
        return `${q.data.name}<br/>${cfg.xName}: ${q.data.value[0].toFixed(2)}<br/>${cfg.yName}: ${q.data.value[1].toFixed(2)}`
      },
    },
    xAxis: { type: 'value', name: cfg.xName, ...axis() },
    yAxis: { type: 'value', name: cfg.yName, ...axis() },
    series: [
      {
        type: 'scatter',
        symbolSize: 9,
        itemStyle: { color: C.accent, opacity: 0.75 },
        data: cfg.points.map((p) => ({ name: p.name, value: [p.x, p.y] })),
      },
    ],
  }
}

export interface CIItem {
  label: string
  value: number
  lo: number
  hi: number
}

/** Horizontal dot-and-whisker chart for point estimates with confidence intervals. */
export function dotWhisker(
  groups: { name: string; color: string; items: CIItem[] }[],
  xLabel: string,
): EChartsOption {
  // Category order = first appearance across ALL groups; items are matched by
  // label (not array position), so groups may list categories in any order.
  const cats: string[] = []
  for (const g of groups)
    for (const it of g.items) if (!cats.includes(it.label)) cats.push(it.label)
  const offset = (gi: number) => (gi - (groups.length - 1) / 2) * 8
  const series: SeriesOption[] = groups.flatMap((g, gi) => [
    {
      name: g.name,
      type: 'custom' as const,
      silent: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      renderItem: (_p: any, api: any) => {
        const y = api.coord([0, api.value(2)])[1] + offset(gi)
        const x0 = api.coord([api.value(0), 0])[0]
        const x1 = api.coord([api.value(1), 0])[0]
        const style = { stroke: g.color, lineWidth: 1.5 }
        return {
          type: 'group',
          children: [
            { type: 'line', shape: { x1: x0, y1: y, x2: x1, y2: y }, style },
            { type: 'line', shape: { x1: x0, y1: y - 4, x2: x0, y2: y + 4 }, style },
            { type: 'line', shape: { x1: x1, y1: y - 4, x2: x1, y2: y + 4 }, style },
          ],
        }
      },
      data: g.items.map((it) => [it.lo, it.hi, cats.indexOf(it.label)]),
      z: 1,
    },
    {
      name: g.name,
      type: 'scatter' as const,
      symbolSize: 8,
      itemStyle: { color: g.color },
      data: g.items.map((it) => ({
        name: it.label,
        value: [it.value, cats.indexOf(it.label)] as [number, number],
      })),
      z: 2,
    },
  ])
  return {
    ...base,
    tooltip: { ...base.tooltip, trigger: 'item' },
    legend: groups.length > 1 ? { textStyle: { color: C.muted }, top: 0 } : undefined,
    grid: { left: 170, right: 30, top: groups.length > 1 ? 32 : 12, bottom: 44 },
    xAxis: { type: 'value', name: xLabel, ...axis() },
    yAxis: { type: 'category', data: cats, inverse: true, ...axis() },
    series,
  }
}

export function monthlyHeatmap(monthly: { ym: string; ret: number }[]): EChartsOption {
  const years = [...new Set(monthly.map((m) => m.ym.slice(0, 4)))].sort()
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const data = monthly.map((m) => [
    Number(m.ym.slice(5, 7)) - 1,
    years.indexOf(m.ym.slice(0, 4)),
    Number((m.ret * 100).toFixed(2)),
  ])
  const maxAbs = Math.max(0.01, ...monthly.map((m) => Math.abs(m.ret * 100)))
  return {
    ...base,
    tooltip: { ...base.tooltip, trigger: 'item' },
    grid: { left: 64, right: 24, top: 12, bottom: 64 },
    xAxis: { type: 'category', data: months, ...axis(), splitLine: { show: false } },
    yAxis: { type: 'category', data: years, ...axis(), splitLine: { show: false } },
    visualMap: {
      min: -maxAbs,
      max: maxAbs,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: { color: C.muted },
      inRange: { color: [C.down, '#3f3f46', C.up] },
    },
    series: [
      {
        type: 'heatmap',
        data,
        label: { show: true, color: C.text, formatter: (p: { data: number[] }) => `${p.data[2]}%` },
      },
    ],
  }
}
```

- [ ] **Step 3: lightweight-charts components**

Create `console/src/charts/CandleChart.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type Time,
} from 'lightweight-charts'
import { C } from '../theme'

export interface OverlaySeries {
  name: string
  values: (number | null)[]
}
export interface Pane {
  name: string
  series: OverlaySeries[]
}

export default function CandleChart({
  time,
  open,
  high,
  low,
  close,
  overlays,
  panes,
  height = 520,
}: {
  time: number[]
  open: number[]
  high: number[]
  low: number[]
  close: number[]
  overlays: OverlaySeries[]
  panes: Pane[]
  height?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: C.muted,
        panes: { separatorColor: C.border },
      },
      grid: {
        vertLines: { color: C.border },
        horzLines: { color: C.border },
      },
      timeScale: { timeVisible: true, borderColor: C.border },
      rightPriceScale: { borderColor: C.border },
    })
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: C.up,
      downColor: C.down,
      borderVisible: false,
      wickUpColor: C.up,
      wickDownColor: C.down,
    })
    candle.setData(
      time.map((t, i) => ({
        time: t as Time,
        open: open[i],
        high: high[i],
        low: low[i],
        close: close[i],
      })),
    )
    const lineData = (values: (number | null)[]) =>
      time.map((t, i) =>
        values[i] == null ? { time: t as Time } : { time: t as Time, value: values[i] as number },
      )
    let ci = 0
    const nextColor = () => C.series[ci++ % C.series.length]
    for (const o of overlays) {
      chart
        .addSeries(LineSeries, {
          color: nextColor(),
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          title: o.name,
        })
        .setData(lineData(o.values))
    }
    panes.forEach((p, pi) => {
      for (const s of p.series) {
        chart
          .addSeries(
            LineSeries,
            {
              color: nextColor(),
              lineWidth: 2,
              priceLineVisible: false,
              lastValueVisible: false,
              title: s.name,
            },
            pi + 1,
          )
          .setData(lineData(s.values))
      }
    })
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [time, open, high, low, close, overlays, panes])
  return <div ref={ref} style={{ height }} />
}
```

Create `console/src/charts/TimeSeriesChart.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import { BaselineSeries, ColorType, createChart, type Time } from 'lightweight-charts'
import type { TimePoint } from '../api'
import { C } from '../theme'

export default function TimeSeriesChart({
  points,
  height = 280,
  percent = false,
}: {
  points: TimePoint[]
  height?: number
  percent?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: C.muted,
      },
      grid: { vertLines: { color: C.border }, horzLines: { color: C.border } },
      timeScale: { timeVisible: true, borderColor: C.border },
      rightPriceScale: { borderColor: C.border },
    })
    const series = chart.addSeries(BaselineSeries, {
      baseValue: { type: 'price', price: 0 },
      topLineColor: C.up,
      topFillColor1: 'rgba(16, 185, 129, 0.25)',
      topFillColor2: 'rgba(16, 185, 129, 0.02)',
      bottomLineColor: C.down,
      bottomFillColor1: 'rgba(244, 63, 94, 0.02)',
      bottomFillColor2: 'rgba(244, 63, 94, 0.25)',
      priceLineVisible: false,
      priceFormat: percent
        ? { type: 'custom', formatter: (v: number) => `${(v * 100).toFixed(1)}%` }
        : { type: 'price', precision: 4, minMove: 0.0001 },
    })
    series.setData(points.map((p) => ({ time: p.t as Time, value: p.v })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [points, percent])
  return <div ref={ref} style={{ height }} />
}
```

- [ ] **Step 4: Verify typecheck + build**

Run: `cd console && npm run typecheck && npm run build`
Expected: both succeed (components are not yet imported by pages; `noUnusedLocals` only applies within files).

- [ ] **Step 5: Commit**

```bash
git add console/src/charts
git commit -m "feat(console): chart primitives — ECharts wrapper/options, candle + baseline charts"
```

---

### Task 9: Data Browser page

**Files:**
- Modify: `console/src/pages/DataBrowser.tsx` (replace stub with full implementation)

**Interfaces:**
- Consumes: `useApi`, `DatasetInfo`, `SchemaCol`, `RowsPage` from `api.ts`; `PageHeader, Card, EmptyState, Spinner, Select` from `ui.tsx`; `EChart` + `scatterOption` from charts.
- Produces: the `/data` route content. No exports consumed elsewhere.

- [ ] **Step 1: Implement the page**

Replace `console/src/pages/DataBrowser.tsx` with:

```tsx
import { useMemo, useState } from 'react'
import {
  useApi,
  type Cell,
  type DatasetInfo,
  type RowsPage,
  type SchemaCol,
} from '../api'
import EChart from '../charts/EChart'
import { scatterOption } from '../charts/options'
import { Card, EmptyState, PageHeader, Select, Spinner } from '../ui'

const PAGE_SIZE = 50

function fmtBytes(n: number) {
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`
  return `${(n / 1e3).toFixed(1)} KB`
}

function fmtCell(v: Cell) {
  if (v === null) return '∅'
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toPrecision(6)
  return String(v)
}

export default function DataBrowser() {
  const [selected, setSelected] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState<{ col: string; desc: boolean } | null>(null)
  const [xCol, setXCol] = useState('')
  const [yCol, setYCol] = useState('')

  const datasets = useApi<DatasetInfo[]>('/api/datasets')
  const schema = useApi<{ name: string; columns: SchemaCol[] }>(
    selected ? `/api/datasets/${selected}/schema` : null,
  )
  const rowsPath = selected
    ? `/api/datasets/${selected}/rows?page=${page}&page_size=${PAGE_SIZE}` +
      (sort ? `&sort=${sort.col}&order=${sort.desc ? 'desc' : 'asc'}` : '')
    : null
  const rows = useApi<RowsPage>(rowsPath)

  const numericCols = useMemo(
    () =>
      (schema.data?.columns ?? [])
        .filter((c) => c.dtype.startsWith('Float') || c.dtype.startsWith('Int') || c.dtype.startsWith('UInt'))
        .map((c) => c.name),
    [schema.data],
  )

  const plotPath =
    selected && xCol && yCol
      ? `/api/datasets/${selected}/rows?page_size=500&sort=${xCol}`
      : null
  const plotRows = useApi<RowsPage>(plotPath)
  const plotOption = useMemo(() => {
    if (!plotRows.data || !xCol || !yCol) return null
    const xi = plotRows.data.columns.indexOf(xCol)
    const yi = plotRows.data.columns.indexOf(yCol)
    const points = plotRows.data.rows
      .filter((r) => typeof r[xi] === 'number' && typeof r[yi] === 'number')
      .map((r, i) => ({ x: r[xi] as number, y: r[yi] as number, name: `row ${i}` }))
    return scatterOption({ points, xName: xCol, yName: yCol })
  }, [plotRows.data, xCol, yCol])

  const select = (name: string) => {
    setSelected(name)
    setPage(1)
    setSort(null)
    setXCol('')
    setYCol('')
  }

  return (
    <div>
      <PageHeader title="Data Browser" sub="Every parquet in data/reports/ — schema, rows, quick plots." />
      <div className="flex gap-6">
        <Card className="max-h-[80vh] w-80 shrink-0 overflow-y-auto">
          {datasets.loading && <Spinner />}
          {datasets.error && <EmptyState error={datasets.error} />}
          {datasets.data?.map((d) => (
            <button
              key={d.name}
              onClick={() => select(d.name)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                selected === d.name
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:bg-zinc-900'
              }`}
            >
              <div className="truncate font-medium">{d.name}</div>
              <div className="text-xs text-zinc-600">
                {d.columns} cols · {fmtBytes(d.size_bytes)}
              </div>
            </button>
          ))}
        </Card>
        <div className="min-w-0 flex-1 space-y-6">
          {!selected && <EmptyState note="Select a dataset on the left." />}
          {selected && rows.loading && <Spinner />}
          {selected && rows.error && <EmptyState error={rows.error} />}
          {selected && rows.data && (
            <>
              <Card>
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-sm text-zinc-400">
                    {rows.data.total.toLocaleString()} rows
                  </div>
                  <div className="flex items-center gap-3 text-sm text-zinc-400">
                    <button
                      className="rounded-md border border-zinc-800 px-2 py-1 disabled:opacity-40"
                      disabled={page <= 1}
                      onClick={() => setPage(page - 1)}
                    >
                      ← Prev
                    </button>
                    <span>
                      page {rows.data.page} / {Math.max(1, Math.ceil(rows.data.total / PAGE_SIZE))}
                    </span>
                    <button
                      className="rounded-md border border-zinc-800 px-2 py-1 disabled:opacity-40"
                      disabled={page * PAGE_SIZE >= rows.data.total}
                      onClick={() => setPage(page + 1)}
                    >
                      Next →
                    </button>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-500">
                        {rows.data.columns.map((c) => (
                          <th
                            key={c}
                            className="cursor-pointer whitespace-nowrap px-2 py-2 font-medium hover:text-zinc-300"
                            onClick={() =>
                              setSort(
                                sort?.col === c
                                  ? { col: c, desc: !sort.desc }
                                  : { col: c, desc: false },
                              )
                            }
                          >
                            {c}
                            {sort?.col === c ? (sort.desc ? ' ↓' : ' ↑') : ''}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.data.rows.map((r, i) => (
                        <tr key={i} className="border-b border-zinc-900 text-zinc-300">
                          {r.map((v, j) => (
                            <td key={j} className="whitespace-nowrap px-2 py-1.5 tabular-nums">
                              {fmtCell(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
              {numericCols.length >= 2 && (
                <Card>
                  <div className="mb-3 flex items-center gap-4">
                    <span className="text-sm font-medium text-zinc-300">Quick plot</span>
                    <Select label="x" value={xCol} options={['', ...numericCols]} onChange={setXCol} />
                    <Select label="y" value={yCol} options={['', ...numericCols]} onChange={setYCol} />
                  </div>
                  {plotOption ? (
                    <EChart option={plotOption} height={360} />
                  ) : (
                    <div className="py-8 text-center text-sm text-zinc-600">
                      Pick x and y columns (first 500 rows plotted).
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify typecheck + build, then eyeball**

Run: `cd console && npm run typecheck && npm run build`
Expected: success.

Run:

```bash
uv run charybdis-console --port 8899 & SRV=$!
sleep 2
curl -s localhost:8899/api/datasets | head -c 300
kill $SRV
```

Expected: JSON list of real datasets. (Full visual check happens in the final task; the operator can also `npm run dev` and click through `/data`.)

- [ ] **Step 3: Commit**

```bash
git add console/src/pages/DataBrowser.tsx
git commit -m "feat(console): data browser — dataset list, sortable paginated table, quick scatter"
```

---

### Task 10: Chart Lab page

**Files:**
- Modify: `console/src/pages/ChartLab.tsx` (replace stub)

**Interfaces:**
- Consumes: `useApi`, `CandleSource`, `CandlePayload`, `IndicatorMeta`; `CandleChart` (`OverlaySeries`, `Pane`); `ui.tsx` components.
- Produces: the `/chart-lab` route content.

- [ ] **Step 1: Implement the page**

Replace `console/src/pages/ChartLab.tsx` with:

```tsx
import { useMemo, useState } from 'react'
import {
  useApi,
  type CandlePayload,
  type CandleSource,
  type IndicatorMeta,
} from '../api'
import CandleChart, { type OverlaySeries, type Pane } from '../charts/CandleChart'
import { Card, EmptyState, PageHeader, Select, Spinner } from '../ui'

function defaultSpec(m: IndicatorMeta): string {
  const params = Object.values(m.params)
  return params.length ? `${m.name}:${params.join(':')}` : m.name
}

export default function ChartLab() {
  const sources = useApi<CandleSource[]>('/api/candles/sources')
  const registry = useApi<IndicatorMeta[]>('/api/indicators')

  const [sourceId, setSourceId] = useState('')
  const [market, setMarket] = useState('')
  const [specs, setSpecs] = useState<string[]>([])
  const [draft, setDraft] = useState('')

  const source = sources.data?.find((s) => s.id === sourceId) ?? sources.data?.[0]
  const activeMarket = source?.markets.includes(market) ? market : source?.markets[0]

  const candlesPath =
    source && activeMarket
      ? `/api/candles?source=${source.id}&market=${encodeURIComponent(activeMarket)}` +
        (specs.length ? `&ind=${encodeURIComponent(specs.join(','))}` : '')
      : null
  const candles = useApi<CandlePayload>(candlesPath)

  const { overlays, panes } = useMemo(() => {
    const overlays: OverlaySeries[] = []
    const panes: Pane[] = []
    for (const ind of candles.data?.indicators ?? []) {
      const series = Object.entries(ind.series).map(([name, values]) => ({ name, values }))
      if (ind.display === 'overlay') overlays.push(...series)
      else panes.push({ name: ind.id, series })
    }
    return { overlays, panes }
  }, [candles.data])

  const addDraft = () => {
    const s = draft.trim()
    if (s && !specs.includes(s)) setSpecs([...specs, s])
    setDraft('')
  }

  if (sources.loading || registry.loading) return <Spinner />
  if (sources.error) return <EmptyState error={sources.error} />
  if (!sources.data?.length)
    return <EmptyState note="No candle sources present (study3_candles_1h/1d parquet missing)." />

  return (
    <div>
      <PageHeader title="Chart Lab" sub="Candles + indicators over any harvested market." />
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <Select
            label="source"
            value={source!.id}
            options={sources.data.map((s) => s.id)}
            onChange={(v) => setSourceId(v)}
          />
          <Select
            label="market"
            value={activeMarket ?? ''}
            options={source!.markets}
            onChange={setMarket}
          />
          <div className="flex items-center gap-2">
            <Select label="add indicator" value="" options={['', ...(registry.data ?? []).map(defaultSpec)]} onChange={(v) => v && setSpecs((p) => (p.includes(v) ? p : [...p, v]))} />
            <input
              className="w-36 rounded-md border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-cyan-500"
              placeholder="custom: ema:50"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addDraft()}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {specs.map((s) => (
              <span
                key={s}
                className="flex items-center gap-1 rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300"
              >
                {s}
                <button
                  className="text-zinc-500 hover:text-rose-400"
                  onClick={() => setSpecs(specs.filter((x) => x !== s))}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      </Card>
      {candles.loading && <Spinner />}
      {candles.error && <EmptyState error={candles.error} />}
      {candles.data && (
        <Card>
          <div className="mb-2 text-sm text-zinc-400">
            {candles.data.market} · {candles.data.interval} · {candles.data.time.length} bars
          </div>
          <CandleChart
            time={candles.data.time}
            open={candles.data.open}
            high={candles.data.high}
            low={candles.data.low}
            close={candles.data.close}
            overlays={overlays}
            panes={panes}
            height={560}
          />
        </Card>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify typecheck + build**

Run: `cd console && npm run typecheck && npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add console/src/pages/ChartLab.tsx
git commit -m "feat(console): chart lab — candles with registry-driven indicator picker"
```

---

### Task 11: Backtests page

**Files:**
- Modify: `console/src/pages/Backtests.tsx` (replace stub)

**Interfaces:**
- Consumes: `useApi`, `BacktestEntry`, `BacktestDetail`; `TimeSeriesChart`; `EChart` + `monthlyHeatmap`; `ui.tsx`.
- Produces: the `/backtests` route content.

- [ ] **Step 1: Implement the page**

Replace `console/src/pages/Backtests.tsx` with:

```tsx
import { useState } from 'react'
import { useApi, type BacktestDetail, type BacktestEntry } from '../api'
import EChart from '../charts/EChart'
import { monthlyHeatmap } from '../charts/options'
import TimeSeriesChart from '../charts/TimeSeriesChart'
import { Card, EmptyState, PageHeader, Spinner, StatCard } from '../ui'

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`

export default function Backtests() {
  const list = useApi<BacktestEntry[]>('/api/backtests')
  const [selected, setSelected] = useState<string | null>(null)
  const activeId = selected ?? list.data?.[0]?.id ?? null
  const detail = useApi<BacktestDetail>(activeId ? `/api/backtests/${activeId}` : null)

  if (list.loading) return <Spinner />
  if (list.error) return <EmptyState error={list.error} />
  if (!list.data?.length)
    return <EmptyState note="No backtests registered (study3_sc_backtest parquet missing)." />

  const d = detail.data
  const summary = d?.summary as Record<string, number> | null | undefined

  return (
    <div>
      <PageHeader title="Backtests" sub="Generic performance viewer — register a parquet, get the full readout." />
      <div className="mb-4 flex flex-wrap gap-2">
        {list.data.map((b) => (
          <button
            key={b.id}
            onClick={() => setSelected(b.id)}
            className={`rounded-full border px-3 py-1.5 text-sm ${
              b.id === activeId
                ? 'border-cyan-500 bg-cyan-500/10 text-cyan-300'
                : 'border-zinc-800 text-zinc-400 hover:border-zinc-600'
            }`}
          >
            {b.strategy}
          </button>
        ))}
      </div>
      {detail.loading && <Spinner />}
      {detail.error && <EmptyState error={detail.error} />}
      {d && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Total return"
              value={pct(d.stats.total_return)}
              tone={d.stats.total_return >= 0 ? 'up' : 'down'}
              sub={
                summary
                  ? `report CI [${pct(summary.return_ci_low)}, ${pct(summary.return_ci_high)}]`
                  : undefined
              }
            />
            <StatCard
              label="Sharpe"
              value={d.stats.sharpe?.toFixed(2) ?? '—'}
              sub={summary ? `report: ${summary.sharpe?.toFixed(2)}` : undefined}
            />
            <StatCard label="Max drawdown" value={pct(d.stats.max_drawdown)} tone="down" />
            <StatCard
              label="Periods"
              value={String(d.stats.periods)}
              sub={`${new Date(d.stats.start * 1000).toISOString().slice(0, 10)} → ${new Date(d.stats.end * 1000).toISOString().slice(0, 10)}`}
            />
          </div>
          {summary && (
            <div className="grid grid-cols-3 gap-4">
              <StatCard label="Funding PnL" value={pct(summary.funding_pnl)} tone={summary.funding_pnl >= 0 ? 'up' : 'down'} />
              <StatCard label="Price PnL" value={pct(summary.price_pnl)} tone={summary.price_pnl >= 0 ? 'up' : 'down'} />
              <StatCard label="Cost PnL" value={pct(summary.cost_pnl)} tone="down" />
            </div>
          )}
          <Card>
            <div className="mb-2 text-sm font-medium text-zinc-300">Equity (cumulative net return)</div>
            <TimeSeriesChart points={d.equity} percent height={300} />
          </Card>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <div className="mb-2 text-sm font-medium text-zinc-300">Drawdown</div>
              <TimeSeriesChart points={d.drawdown} percent height={240} />
            </Card>
            <Card>
              <div className="mb-2 text-sm font-medium text-zinc-300">Rolling Sharpe (30 periods)</div>
              {d.rolling_sharpe.length ? (
                <TimeSeriesChart points={d.rolling_sharpe} height={240} />
              ) : (
                <div className="py-10 text-center text-sm text-zinc-600">
                  Not enough periods for a 30-period window.
                </div>
              )}
            </Card>
          </div>
          <Card>
            <div className="mb-2 text-sm font-medium text-zinc-300">Monthly returns</div>
            <EChart option={monthlyHeatmap(d.monthly)} height={80 + 40 * new Set(d.monthly.map((m) => m.ym.slice(0, 4))).size} />
          </Card>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify typecheck + build**

Run: `cd console && npm run typecheck && npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add console/src/pages/Backtests.tsx
git commit -m "feat(console): backtest viewer — equity, drawdown, rolling sharpe, monthly heatmap"
```

---

### Task 12: Study pages (Studies 1–2 and Study 3)

**Files:**
- Modify: `console/src/pages/Study12.tsx` (replace stub)
- Modify: `console/src/pages/Study3.tsx` (replace stub)

**Interfaces:**
- Consumes: `useApi`, `RowsPage`, `Study1Markout`; `EChart`, `lineOption`, `dotWhisker`, `scatterOption`, `CIItem`; `ui.tsx`; `C` from theme.
- Produces: the `/studies-1-2` and `/study-3` route content. Shared helper `rowsToObjects(rows: RowsPage): Record<string, Cell>[]` exported from `api.ts` (add it there in Step 1).

- [ ] **Step 1: Add the rows helper to `api.ts`**

Append to `console/src/api.ts`:

```ts
export function rowsToObjects(page: RowsPage): Record<string, Cell>[] {
  return page.rows.map((r) => Object.fromEntries(page.columns.map((c, i) => [c, r[i]])))
}
```

- [ ] **Step 2: Implement Studies 1–2 page**

Replace `console/src/pages/Study12.tsx` with:

```tsx
import { useMemo, useState } from 'react'
import { rowsToObjects, useApi, type RowsPage, type Study1Markout } from '../api'
import EChart from '../charts/EChart'
import { dotWhisker, lineOption, type CIItem } from '../charts/options'
import { C } from '../theme'
import { Card, EmptyState, PageHeader, Select, Spinner } from '../ui'

function Study1Section() {
  const markout = useApi<Study1Markout>('/api/study1/markout')
  const [market, setMarket] = useState('')
  if (markout.loading) return <Spinner />
  if (markout.error) return <EmptyState error={markout.error} />
  const d = markout.data!
  const active = d.markets.includes(market) ? market : d.markets[0]
  const series = d.segments.map((seg) => ({
    name: seg,
    data: d.horizons.map(
      (h) =>
        d.cells.find((c) => c.market === active && c.segment === seg && c.horizon === h)
          ?.mean_bps ?? null,
    ),
  }))
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-300">
          Net maker markout by horizon and session
        </div>
        <Select label="market" value={active} options={d.markets} onChange={setMarket} />
      </div>
      <EChart option={lineOption({ categories: d.horizons, series, yName: 'net markout (bps)' })} height={360} />
      <p className="mt-2 text-xs text-zinc-600">
        Stale quotes excluded. L2 fill simulation is an optimistic upper bound (no cancel/priority
        visibility). Verdict: off-hours is not better than RTH — CIs overlap in 8/8 markets.
      </p>
    </Card>
  )
}

function Study2Section() {
  const rows = useApi<RowsPage>(
    '/api/datasets/forced_flow_vs_baseline_markout_proxy/rows?page_size=500',
  )
  const [horizon, setHorizon] = useState('30s')
  const { horizons, option } = useMemo(() => {
    if (!rows.data) return { horizons: [] as string[], option: null }
    const objs = rowsToObjects(rows.data)
    const horizons = [...new Set(objs.map((o) => String(o.horizon)))]
    const groups = ['forced-flow', 'baseline'].map((wt, i) => ({
      name: wt,
      color: i === 0 ? C.accent : C.muted,
      items: objs
        .filter((o) => o.horizon === horizon && String(o.window_type).includes(wt === 'forced-flow' ? 'forced' : 'baseline'))
        .map(
          (o): CIItem => ({
            label: String(o.market),
            value: Number(o.point_estimate_bps),
            lo: Number(o.ci_low_bps),
            hi: Number(o.ci_high_bps),
          }),
        ),
    }))
    const valid = groups.every((g) => g.items.length > 0)
    return {
      horizons,
      option: valid ? dotWhisker(groups, 'net markout (bps)') : null,
    }
  }, [rows.data, horizon])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-300">
          Forced-flow proxy vs matched baseline (95% CI)
        </div>
        <Select label="horizon" value={horizon} options={horizons} onChange={setHorizon} />
      </div>
      {option ? <EChart option={option} height={300} /> : <EmptyState note="No rows for this horizon." />}
      <p className="mt-2 text-xs text-zinc-600">
        All events are heuristic proxy tags (0 confirmed liquidations in HLSYSTEMEVENTS). Post
        2026-06-18 quote poisoning drops 39.5% of windows; the comparison is confounded and
        conservative.
      </p>
    </Card>
  )
}

export default function Study12() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Studies 1–2 — Markout"
        sub="Off-hours maker markout (Study 1) and forced-flow proxy vs baseline (Study 2)."
      />
      <Study1Section />
      <Study2Section />
    </div>
  )
}
```

- [ ] **Step 3: Implement Study 3 page**

Replace `console/src/pages/Study3.tsx` with:

```tsx
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { rowsToObjects, useApi, type RowsPage } from '../api'
import EChart from '../charts/EChart'
import { dotWhisker, scatterOption, type CIItem } from '../charts/options'
import { C } from '../theme'
import { Card, EmptyState, PageHeader, Spinner } from '../ui'

const pct = (v: unknown) => `${(Number(v) * 100).toFixed(1)}%`

function CensusSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sa_census/rows?page_size=500')
  const { scatter, top } = useMemo(() => {
    if (!rows.data) return { scatter: null, top: null }
    const objs = rowsToObjects(rows.data).filter((o) => o.mean_apr != null)
    const scatter = scatterOption({
      points: objs
        .filter((o) => o.shock_half_life_hours != null)
        .map((o) => ({
          x: Number(o.shock_half_life_hours),
          y: Number(o.mean_apr) * 100,
          name: String(o.market),
        })),
      xName: 'shock half-life (h)',
      yName: 'mean APR (%)',
    })
    const topItems = objs
      .sort((a, b) => Number(b.mean_apr) - Number(a.mean_apr))
      .slice(0, 15)
      .map(
        (o): CIItem => ({
          label: String(o.market),
          value: Number(o.mean_apr) * 100,
          lo: Number(o.mean_apr_ci_low) * 100,
          hi: Number(o.mean_apr_ci_high) * 100,
        }),
      )
    return { scatter, top: dotWhisker([{ name: 'mean APR', color: C.accent, items: topItems }], 'mean APR (%)') }
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <div className="mb-2 text-sm font-medium text-zinc-300">
          Funding census: size vs persistence (183 markets)
        </div>
        {scatter && <EChart option={scatter} height={380} />}
        <p className="mt-2 text-xs text-zinc-600">
          Half-life median 1.3h, max 9.9h — the 24h carry bar is structurally unreachable; 0/183
          markets are carry-relevant.
        </p>
      </Card>
      <Card>
        <div className="mb-2 text-sm font-medium text-zinc-300">Top mean APR with 95% CI</div>
        {top && <EChart option={top} height={380} />}
      </Card>
    </div>
  )
}

function ClockSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sd_brackets/rows?page_size=500')
  const option = useMemo(() => {
    if (!rows.data) return null
    const objs = rowsToObjects(rows.data).filter((o) => o.group_type === 'all')
    if (!objs.length) return null
    const label = (o: Record<string, unknown>) => `${o.coverage_group} · ±${o.bracket_minutes}m`
    return dotWhisker(
      [
        {
          name: 'funding bracket',
          color: C.accent,
          items: objs.map(
            (o): CIItem => ({
              label: label(o),
              value: Number(o.mean_return) * 1e4,
              lo: Number(o.ci_low) * 1e4,
              hi: Number(o.ci_high) * 1e4,
            }),
          ),
        },
        {
          name: 'baseline',
          color: C.muted,
          items: objs.map(
            (o): CIItem => ({
              label: label(o),
              value: Number(o.baseline_mean_return) * 1e4,
              lo: Number(o.baseline_ci_low) * 1e4,
              hi: Number(o.baseline_ci_high) * 1e4,
            }),
          ),
        },
      ],
      'mean return (bps)',
    )
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <div className="mb-2 text-sm font-medium text-zinc-300">
        Funding-clock brackets vs baseline (95% CI) — 12/12 do not separate
      </div>
      {option ? <EChart option={option} height={420} /> : <EmptyState note="No 'all' group rows." />}
      <p className="mt-2 text-xs text-zinc-600">
        SKHX/SMSN use the full L4 window; the other eight markets are a 3.5-day recent-regime null
        only.
      </p>
    </Card>
  )
}

function SpreadsSection() {
  const rows = useApi<RowsPage>(
    '/api/datasets/study3_se_spreads/rows?page_size=100&sort=mean_abs_diff_apr&order=desc',
  )
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  const objs = rowsToObjects(rows.data!).slice(0, 12)
  return (
    <Card>
      <div className="mb-2 text-sm font-medium text-zinc-300">
        Cross-dex twin spreads — top funding differentials (0/57 pairs viable)
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-500">
              {['pair', 'mean |Δ APR|', 'half-life (h)', '% time > maker BE', '% time > taker BE', 'basis p95 vs edge'].map((h) => (
                <th key={h} className="whitespace-nowrap px-2 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objs.map((o) => (
              <tr key={String(o.pair_id)} className="border-b border-zinc-900 text-zinc-300">
                <td className="px-2 py-1.5">{String(o.pair_id)}</td>
                <td className="px-2 py-1.5 tabular-nums">{pct(o.mean_abs_diff_apr)}</td>
                <td className="px-2 py-1.5 tabular-nums">{Number(o.persistence_half_life_hours).toFixed(2)}</td>
                <td className="px-2 py-1.5 tabular-nums">{pct(o.pct_time_gt_maker_breakeven)}</td>
                <td className="px-2 py-1.5 tabular-nums">{pct(o.pct_time_gt_taker_breakeven)}</td>
                <td className="px-2 py-1.5 tabular-nums text-rose-400">
                  {Number(o.basis_p95_abs_excursion) > Number(o.p95_diff_horizon_return) ? 'basis swamps edge' : 'edge survives'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-zinc-600">
        Basis is the scale-invariant log-ratio metric; all 57 pairs fail — basis p95 exceeds the
        persistence-horizon funding edge everywhere.
      </p>
    </Card>
  )
}

function HazardSection() {
  const rows = useApi<RowsPage>('/api/datasets/study3_sf_event_rates/rows?page_size=100')
  const option = useMemo(() => {
    if (!rows.data) return null
    const objs = rowsToObjects(rows.data)
      .filter((o) => o.analysis_cut === 'apr_bucket')
      .sort((a, b) => Number(a.bucket_order) - Number(b.bucket_order))
    if (!objs.length) return null
    return dotWhisker(
      [
        {
          name: 'event rate',
          color: C.accent,
          items: objs.map(
            (o): CIItem => ({
              label: String(o.funding_bucket),
              value: Number(o.event_rate_per_market_hour),
              lo: Number(o.ci_low),
              hi: Number(o.ci_high),
            }),
          ),
        },
      ],
      'proxy events / market-hour',
    )
  }, [rows.data])
  if (rows.loading) return <Spinner />
  if (rows.error) return <EmptyState error={rows.error} />
  return (
    <Card>
      <div className="mb-2 text-sm font-medium text-zinc-300">
        Forced-flow event rate by funding bucket (95% CI)
      </div>
      {option ? <EChart option={option} height={320} /> : <EmptyState note="No apr_bucket rows." />}
      <p className="mt-2 text-xs text-zinc-600">
        Per-market rate-ratio CIs include 1 — funding does not time forced flow within a market.
      </p>
    </Card>
  )
}

export default function Study3() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Study 3 — HIP-3 funding deep dive"
        sub="Funding is large but efficiently priced: no carry, no clock edge, no spread arb."
      />
      <CensusSection />
      <Card>
        <div className="text-sm text-zinc-400">
          Carry backtest results (equity, drawdown, attribution) live in the{' '}
          <Link className="text-cyan-400 hover:underline" to="/backtests">
            Backtests viewer
          </Link>
          .
        </div>
      </Card>
      <ClockSection />
      <SpreadsSection />
      <HazardSection />
    </div>
  )
}
```

- [ ] **Step 4: Verify typecheck + build**

Run: `cd console && npm run typecheck && npm run build`
Expected: success.

- [ ] **Step 5: Commit**

```bash
git add console/src/api.ts console/src/pages/Study12.tsx console/src/pages/Study3.tsx
git commit -m "feat(console): study 1-2 and study 3 detail pages"
```

---

### Task 13: Overview page + end-to-end verification

**Files:**
- Modify: `console/src/pages/Overview.tsx` (replace stub)

**Interfaces:**
- Consumes: `useApi`, `Findings`; `ui.tsx`; react-router `Link`.
- Produces: the `/` landing page.

- [ ] **Step 1: Implement the page**

Replace `console/src/pages/Overview.tsx` with:

```tsx
import { Link } from 'react-router-dom'
import { useApi, type Findings } from '../api'
import { Card, EmptyState, PageHeader, Spinner } from '../ui'

export default function Overview() {
  const findings = useApi<Findings>('/api/findings')
  if (findings.loading) return <Spinner />
  if (findings.error) return <EmptyState error={findings.error} />
  return (
    <div>
      <PageHeader
        title="The story so far"
        sub="Headline conclusions per study — curated, with links to the interactive detail views."
      />
      <div className="grid gap-6 xl:grid-cols-3">
        {findings.data!.studies.map((s) => (
          <Card key={s.id} className="flex flex-col">
            <div className="mb-1 text-xs uppercase tracking-wider text-zinc-500">{s.date}</div>
            <h2 className="text-base font-semibold text-zinc-100">{s.title}</h2>
            <div className="mt-2 inline-block w-fit rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-300">
              {s.verdict}
            </div>
            <p className="mt-3 text-sm leading-relaxed text-zinc-400">{s.summary}</p>
            <dl className="mt-4 space-y-2">
              {s.numbers.map((n) => (
                <div key={n.label} className="flex items-baseline justify-between gap-3 border-b border-zinc-900 pb-1.5">
                  <dt className="text-xs text-zinc-500">{n.label}</dt>
                  <dd className="text-right text-xs font-medium tabular-nums text-zinc-200">
                    {n.value}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="mt-auto flex items-center justify-between pt-4">
              <Link to={s.page} className="text-sm font-medium text-cyan-400 hover:underline">
                Explore →
              </Link>
              <span className="text-[10px] text-zinc-600">{s.report}</span>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Full build + end-to-end smoke test**

Run: `cd console && npm run typecheck && npm run build && cd ..`
Expected: success.

Run:

```bash
uv run charybdis-console --port 8899 & SRV=$!
sleep 2
for p in /api/health /api/findings /api/datasets /api/candles/sources /api/indicators /api/backtests /api/study1/markout; do
  echo "== $p"; curl -sf "localhost:8899$p" | head -c 120; echo
done
curl -sf localhost:8899/ | grep -o '<title>[^<]*</title>'
curl -sf localhost:8899/study-3 | grep -o '<title>[^<]*</title>'   # SPA fallback
kill $SRV
```

Expected: every endpoint returns JSON (no 500s), and both `/` and `/study-3` return the app HTML title.

Run the full backend suite one more time: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add console/src/pages/Overview.tsx
git commit -m "feat(console): overview landing page with curated study findings"
```

- [ ] **Step 4: Ask the operator to eyeball it**

Tell the operator: `uv run charybdis-console` then open http://localhost:8787 — click through all six pages. This is the human visual gate for "looks really good"; collect feedback before closing out.

---

### Task 14: Notebooks + notebook-intelligence (Claude mode)

**Files:**
- Modify: `pyproject.toml` (dev dependency group)
- Create: `notebooks/README.md`
- Create: `notebooks/00_explore.ipynb`
- Modify: `.gitignore` (checkpoint dirs)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: a working `uv run jupyter lab` environment with the NBI extension installed.

- [ ] **Step 1: Add the dev dependency group**

In `pyproject.toml` add (top level, after `[project.scripts]`):

```toml
[dependency-groups]
dev = [
    "ipykernel",
    "jupyterlab",
    "notebook-intelligence",
]
```

Run: `uv sync`
Expected: installs jupyterlab + notebook-intelligence (dev group is synced by default).

Run: `uv run jupyter labextension list 2>&1 | grep -i notebook`
Expected: `@notebook-intelligence/notebook-intelligence` listed as enabled.

- [ ] **Step 2: Append to `.gitignore`**

```
# notebooks
.ipynb_checkpoints/
```

- [ ] **Step 3: Write the starter notebook**

Create `notebooks/00_explore.ipynb` with exactly this JSON:

```json
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Charybdis data exploration\n",
    "\n",
    "Report tables live in `../data/reports/*.parquet`. Load them with polars.\n",
    "Tip: open the Notebook Intelligence chat (sparkle icon, left sidebar) and ask\n",
    "Claude to write cells for you — see `notebooks/README.md` for setup."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "from pathlib import Path\n",
    "\n",
    "import polars as pl\n",
    "\n",
    "DATA = Path(\"../data/reports\")\n",
    "sorted(p.stem for p in DATA.glob(\"*.parquet\"))[:20]"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "census = pl.read_parquet(DATA / \"study3_sa_census.parquet\")\n",
    "census.select(\"market\", \"mean_apr\", \"shock_half_life_hours\", \"carry_relevant\").sort(\n",
    "    \"mean_apr\", descending=True\n",
    ").head(10)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "candles = pl.read_parquet(DATA / \"study3_candles_1h.parquet\")\n",
    "candles.filter(pl.col(\"market\") == \"xyz:SP500\").tail(5)"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "name": "python",
   "version": "3.11"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
```

- [ ] **Step 4: Write the setup README**

Create `notebooks/README.md`:

```markdown
# Notebooks

## Start

```bash
uv run jupyter lab
```

Open `notebooks/00_explore.ipynb`. The kernel is the project venv, so
`charybdis.*` modules and polars are importable directly.

## Claude Code inside JupyterLab (Notebook Intelligence)

[notebook-intelligence](https://github.com/plmbr/notebook-intelligence) (NBI)
is installed as a dev dependency. One-time setup:

1. In JupyterLab, open the NBI chat panel (sparkle icon in the left sidebar).
2. Click the gear (settings) icon in the chat panel.
3. Set the provider to **Claude** → enables *Claude mode*, which launches your
   local Claude Code CLI for chat. You get Claude Code's full toolset, skills,
   MCP servers, and this project's context inside JupyterLab. Requires the
   `claude` CLI to be installed and logged in (it is, if you're reading this).
4. Optional: inline tab-completions use the Anthropic API directly — set
   `ANTHROPIC_API_KEY` in your environment before launching if you want them.

Settings persist in `~/.jupyter/nbi/config.json`.

Usage: type what you want in the chat ("load the funding census and plot APR
vs half-life") — NBI's agent can create and edit notebook cells directly.

## Conventions

- Notebooks are exploratory scratch space; anything worth keeping graduates
  into `charybdis/` modules with tests.
- `.ipynb_checkpoints/` is gitignored; commit notebooks only when the outputs
  are worth preserving.
```

- [ ] **Step 5: Verify JupyterLab boots**

Run: `timeout 20 uv run jupyter lab --no-browser --port 9797 2>&1 | grep -m1 "http://localhost:9797"`
Expected: prints a lab URL (then the timeout kills it). If NBI prints a startup line about server extension loading, even better.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock notebooks .gitignore
git commit -m "feat(notebooks): jupyterlab + notebook-intelligence (Claude mode) with starter notebook"
```

---

## Self-review checklist (run after writing, fixed inline)

- **Spec coverage:** overview ✔ (T6 yaml + T13), study 1–2 pages ✔ (T12), study 3 pages ✔ (T12 + backtests link), chart lab ✔ (T4 + T10), backtest viewer ✔ (T5 + T11), data browser ✔ (T2 + T9), indicator registry ✔ (T3), one-command start ✔ (T1/T7), missing-data resilience ✔ (`_check_present` + `EmptyState`, tested in T2/T5/T6), notebooks + NBI ✔ (T14).
- **Type consistency:** `CIItem`, `TimePoint`, `RowsPage`, `rowsToObjects`, `OverlaySeries`/`Pane` names match across tasks; backend route shapes match the TS interfaces in T7.
- **Known judgment calls for implementers:** exact npm package versions may drift — if `npm install` fails on a version pin, relax the pin to the nearest available major. If a lightweight-charts v5 API name differs (e.g. pane options), consult the installed package's `.d.ts` rather than guessing.

