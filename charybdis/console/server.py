"""FastAPI app for the charybdis research console."""
from __future__ import annotations

import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from charybdis.console import backtests, candles, datasets, findings, indicators, study1, tables


def _check_present(name: str) -> None:
    try:
        present = datasets.dataset_exists(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not present:
        raise HTTPException(status_code=404, detail=f"dataset not present: {name}")


def create_app() -> FastAPI:
    app = FastAPI(title="charybdis console", docs_url="/api/docs", openapi_url="/api/openapi.json")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/datasets")
    def list_datasets() -> list[dict]:
        return datasets.list_datasets()

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
        except candles.MarketNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"unknown source: {source}")
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=f"dataset not present: {e}")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except (OverflowError, ZeroDivisionError) as e:
            raise HTTPException(status_code=400, detail=f"bad indicator params: {e}")

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

    @app.get("/api/findings")
    def get_findings() -> dict:
        return findings.load_findings()

    @app.get("/api/study1/markout")
    def study1_markout() -> dict:
        _check_present("study1_fills_l2")
        return study1.markout_summary()

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    dist = Path(__file__).resolve().parents[2] / "console" / "dist"
    if not dist.is_dir():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="unknown API route")
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
