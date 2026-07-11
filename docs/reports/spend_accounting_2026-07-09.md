# Final spend accounting: Studies 1 and 2

Accounting date in the meter: 2026-07-10. CoinAPI spend did not increase during this reporting task.

## Receipts by SKU and day

The authoritative meter total is $116.924738780, which rounds to $116.92. Bytes and costs below are direct fields under `data/spend.json` → `days` → `2026-07-10`; decimal GB is `bytes / 1,000,000,000`.

| Day | SKU | Bytes | Decimal GB | Metered USD |
|---|---|---:|---:|---:|
| 2026-07-10 | Order Book | 15,515,733,460 | 15.515733460 | $55.031466920 |
| 2026-07-10 | Quotes | 3,758,234,950 | 3.758234950 | $17.032939800 |
| 2026-07-10 | Trades | 2,907,196,967 | 2.907196967 | $40.886363604 |
| 2026-07-10 | HL Oracle Prices | 108,000,846 | 0.108000846 | $2.592020304 |
| 2026-07-10 | HL System Events | 57,581,173 | 0.057581173 | $1.381948152 |
| **Total** |  | **22,346,747,396** | **22.346747396** | **$116.924738780** |

Source: `data/spend.json` fields `days.2026-07-10.<SKU>.bytes`, `days.2026-07-10.<SKU>.cost_usd`, and `running_cost_usd`.

## Task reconciliation

The task deltas reconcile exactly, before display rounding:

| Pull | Metered USD | Receipt composition |
|---|---:|---|
| Study 1 / T1 | $70.661194624 | Order Book $24.586523416 + Quotes $14.611018140 + Trades $31.463653068 |
| Study 2 cheap data / T5 | $15.818600652 | Trades $9.422710536 + Quotes $2.421921660 + HL Oracle Prices $2.592020304 + HL System Events $1.381948152 |
| Study 2 event books / T7 | $30.444943504 | Order Book $30.444943504 |
| **Reconciled total** | **$116.924738780** | **$70.661194624 + $15.818600652 + $30.444943504** |

The SKU cross-check also closes exactly:

- Order Book: $24.586523416 (T1) + $30.444943504 (T7) = $55.031466920, matching the `spend.json` Order Book cell.
- Quotes: $14.611018140 (T1) + $2.421921660 (T5) = $17.032939800, matching the `spend.json` Quotes cell.
- Trades: $31.463653068 (T1) + $9.422710536 (T5) = $40.886363604, matching the `spend.json` Trades cell.
- The T5 HL Oracle Prices and HL System Events amounts match their `spend.json` cells directly.

Task-delta sources: `data/study1_manifest.json` cost summary as reproduced in `docs/reports/pull_study1_2026-07-09.md`; `data/study2_manifest.json` cost summary as reproduced in `docs/reports/pull_study2_2026-07-09.md`; `data/study2_t7_plan.json` fields `final_pulled_usd`, `spend_before_pull_usd`, and `spend_running_total_usd`. Final receipt cells and total are independently read from `data/spend.json`.

At report precision, the requested shorthand is therefore $70.66 + $15.82 + $30.44 = $116.92. The exact total is $116.924738780, which is $63.075261220 below the $180.00 policy cap and therefore within it.

## Pricing note

The meter prices decimal GB, not GiB. Hyperliquid-specific feed SKUs were conservatively assigned the published Trades-tier schedule in the meter; whether those SKU rates match the CoinAPI billing console remains an external reconciliation follow-up.
