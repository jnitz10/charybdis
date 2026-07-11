# Study 3 spend accounting

Accounting date: 2026-07-10. Study-3 new flat-file spend is **$0.00**. All S-A and S-C–S-F work used free public Hyperliquid REST data or existing on-disk inputs. S-B/G-F1 found its required oracle inventory already on disk; its extension listing returned no objects and its dry-run was **0 files, 0 bytes, $0.00**, with no GET/download (`docs/reports/study3_mechanics_2026-07-10.md`, G-F1 artifact statement).

## Meter and caps

The authoritative cumulative meter is **$116.924738780**, displayed as **$116.92** (`data/spend.json: running_cost_usd`). It is unchanged from the Studies 1–2 close-out (`docs/reports/spend_accounting_2026-07-09.md`).

| Reconciliation | USD |
|---|---:|
| Studies 1–2 cumulative | $116.92 |
| Study 3 new flat-file spend | $0.00 |
| **Cumulative** | **$116.92** |

Explicit arithmetic: **$116.92 + $0.00 = $116.92**. Study-3 spend is **$60.00** below the **$60.00** Study-3 ceiling. Cumulative spend is **$63.08** below the **$180.00** overall cap. Sources: `data/spend.json: running_cost_usd=116.92473877999909`; Study-3 ceiling and overall cap from `docs/superpowers/plans/2026-07-10-funding-deep-dive.md`; prior-study total from `docs/reports/spend_accounting_2026-07-09.md`.

## Free REST volume

- T1 made **1,937 actual public REST calls**, with 19 cache hits and no paid endpoint (`data/study3_harvest.log`, final `calls=1937`; `data/reports/study3_harvest_manifest.json`; `docs/reports/study3_harvest_2026-07-10.md`).
- T5 estimated **410 REST page calls** for the ten-market 1m scope; the run was cache-only and made **0 network calls** (`docs/reports/study3_funding_clock_2026-07-10.md`, coverage framing; cached artifacts under `data/study3_sd_1m/`).

No Study-3 task used orders, wallets, keys, or a paid download.
