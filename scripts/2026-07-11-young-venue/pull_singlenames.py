"""Pull single-name L4 trades + oracle prices, budget-capped at $60.

Discovery: list T-TRADES and T-HLORACLEPRICES hourly dirs 2026-06-01..2026-07-08,
filter to target symbols. Pricing via tier_cost_usd per SKU on cumulative new
bytes (today is a fresh billing day). If projected > $57, drop names from the
tail of PRIORITY until it fits. Then execute_manifest with 8 workers.
"""

from __future__ import annotations

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, UTC

import os
for line in Path("/home/jnitz/Documents/trading/charybdis/.env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from charybdis.ffs3 import (
    FlatFilesS3Client, Manifest, ManifestFile, SpendMeter, execute_manifest, tier_cost_usd,
)

BUDGET_USD = 57.0  # margin under the operator's $60 (GB-vs-GiB rate unverified)
PRIORITY = ["INTC", "HIMS", "MSTR", "CRCL", "HOOD", "COIN", "MU", "MRVL",
            "TSLA", "NVDA", "PLTR", "RKLB", "NBIS", "AMD", "ARM", "BE", "RIVN"]
ORACLE_EXTRA = ["EWY", "KR200", "SMH", "SP500", "XYZ100", "US500", "USA500",
                "USA100", "USTECH", "SMALL2000"]
START = datetime(2026, 6, 1, 0)
END = datetime(2026, 7, 8, 9)

client = FlatFilesS3Client()
hours = []
t = START
while t <= END:
    hours.append(t.strftime("%Y%m%d%H"))
    t += timedelta(hours=1)
print(f"{len(hours)} hourly partitions to list x2 tables", flush=True)

def list_prefix(prefix):
    try:
        return client.list_with_sizes(prefix)
    except Exception as e:
        return e

trade_objs, oracle_objs = [], []
prefixes = [(f"T-TRADES/D-{h}/E-HYPERLIQUIDL4/", "T") for h in hours] + \
           [(f"T-HLORACLEPRICES/D-{h}/E-HYPERLIQUIDL4/", "O") for h in hours]
errors = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(list_prefix, p): (p, kind) for p, kind in prefixes}
    done = 0
    for fut in as_completed(futs):
        (p, kind) = futs[fut]
        res = fut.result()
        done += 1
        if done % 400 == 0:
            print(f"  listed {done}/{len(prefixes)} (T:{len(trade_objs)} O:{len(oracle_objs)})", flush=True)
        if isinstance(res, Exception):
            errors += 1
            continue
        (trade_objs if kind == "T" else oracle_objs).extend(res)
print(f"listing done: {len(trade_objs)} trade objs, {len(oracle_objs)} oracle objs, errors={errors}", flush=True)

def trade_name(key):
    if "_DPERP_XYZ_" not in key:
        return None
    return key.split("_DPERP_XYZ_")[1].split("_USDC")[0]

def oracle_sym(key):
    return key.rsplit("+S-", 1)[1].replace(".csv.gz", "") if "+S-" in key else None

by_name_trades = {}
for o in trade_objs:
    n = trade_name(o.key)
    if n in PRIORITY:
        by_name_trades.setdefault(n, []).append(o)
oracle_syms = set(PRIORITY) | set(ORACLE_EXTRA)
oracle_sel = [o for o in oracle_objs if oracle_sym(o.key) in oracle_syms]

print("\nper-name trade bytes (MB):", flush=True)
for n in PRIORITY:
    objs = by_name_trades.get(n, [])
    print(f"  {n:6s} {sum(o.size for o in objs)/1e6:8.1f} MB  ({len(objs)} files)", flush=True)
print(f"oracle selected: {sum(o.size for o in oracle_sel)/1e6:.1f} MB ({len(oracle_sel)} files) for {len(oracle_syms)} syms", flush=True)

def projected(names):
    tb = sum(o.size for n in names for o in by_name_trades.get(n, []))
    ob = sum(o.size for o in oracle_sel)
    return float(tier_cost_usd("Trades", tb)) + float(tier_cost_usd("HL Oracle Prices", ob))

names = list(PRIORITY)
while names and projected(names) > BUDGET_USD:
    dropped = names.pop()
    print(f"BUDGET TRIM: dropping {dropped} (projected was over ${BUDGET_USD})", flush=True)
cost = projected(names)
print(f"\nfinal scope: {len(names)} names, projected ${cost:.2f} (budget ${BUDGET_USD})", flush=True)
if not names:
    raise SystemExit("nothing fits budget; aborting")

files = []
tcum = ocum = 0
for n in names:
    for o in sorted(by_name_trades.get(n, []), key=lambda x: x.key):
        prev = float(tier_cost_usd("Trades", tcum)); tcum += o.size
        files.append(ManifestFile(o.key, o.size, "Trades", float(tier_cost_usd("Trades", tcum)) - prev))
for o in sorted(oracle_sel, key=lambda x: x.key):
    prev = float(tier_cost_usd("HL Oracle Prices", ocum)); ocum += o.size
    files.append(ManifestFile(o.key, o.size, "HL Oracle Prices", float(tier_cost_usd("HL Oracle Prices", ocum)) - prev))

meter = SpendMeter()
manifest = Manifest(
    files=tuple(files),
    billing_day=date.today().isoformat(),
    current_spend_usd=meter.running_cost_usd,
    estimated_cost_usd=sum(f.estimated_cost_usd for f in files),
)
Path("data/pull_singlenames_manifest.json").write_text(json.dumps(
    {"names": names, "oracle_syms": sorted(oracle_syms), "files": len(files),
     "estimated_cost_usd": manifest.estimated_cost_usd,
     "projected_total_usd": manifest.projected_spend_usd}, indent=1))
print(f"manifest: {len(files)} files, est ${manifest.estimated_cost_usd:.2f}, "
      f"projected total ${manifest.projected_spend_usd:.2f}", flush=True)

import io
sink = io.StringIO()  # suppress per-file plan lines (thousands); keep summary
result = execute_manifest(client, manifest, meter, data_root="data", dry_run=False, workers=8, output=sink)
plan_head = "\n".join(sink.getvalue().splitlines()[:1])
print(plan_head, flush=True)
print(f"result: downloaded={result.downloaded} skipped={result.skipped} paused={result.paused}", flush=True)
print(f"spend now: ${meter.running_cost_usd:.2f}", flush=True)
