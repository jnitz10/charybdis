# Study 3 S-E: cross-dex funding spreads and twin-basis risk

Analysis date: 2026-07-10. This is research-only; no orders, wallets, keys, network calls, or new paid data were used. Total cumulative spend remains **$116.92**.

Hourly funding settlement rates are aligned at their UTC settlement hour without backfilling and annualized by 8,760. Twins use an audited exact underlier map: SP500 = {SP500, US500, USA500}, USA100 = {USTECH, USA100, XYZ100}; every other group uses exact coin identity only. All pair combinations across distinct dex prefixes are reported, including the additional `mkts` index twins surfaced by the frozen S-A universe.

Round-trip maker breakeven is `2 × (effective maker fee A + effective maker fee B)`: resting maker execution does not cross the spread. Taker breakeven is `2 × [(effective taker fee A + half-spread A) + (effective taker fee B + half-spread B)]`. Each is annualized over the observed absolute-differential AR(1) half-life, and fees are read only from `study3_fee_table.parquet`. Basis is the median-demeaned `ln(closeA/closeB)`; volatility is its sample standard deviation and excursion is the 95th percentile of its absolute value.

All bracketed intervals are 95% percentile intervals from 2,000 nonparametric pair-market × UTC-six-hour cluster resamples (seed 0, minimum G=5), reusing `charybdis.markout.cluster_bootstrap_statistic`. Half-life uses genuine adjacent-hour lag pairs precomputed before resampling and assigns each pair to its destination UTC-six-hour block, so sampled blocks cannot create false time adjacency.

## F-E finding and kill attribution

All 57 pairs remain F-E dead.

The robust universal finding is that basis/twin-basis risk swamps the funding differential: corrected basis p95 exceeds the persistence-horizon funding edge for 57/57 pairs. Separately, 40/57 pairs never reach taker breakeven and 14/57 never reach maker breakeven. Among pairs that reach maker breakeven, the primary maker kill leg below is duration unless the duration gate survives, in which case basis is the kill leg.

Primary maker kill-leg counts: never-reaches-breakeven=14; duration=40; basis=3; survives=0.

| underlier | pair | primary maker kill leg | basis also fails |
|---|---|---|---:|
| XMR | flx:XMR|hyna:XMR | duration | yes |
| MU | km:MU|xyz:MU | duration | yes |
| PALLADIUM | flx:PALLADIUM|xyz:PALLADIUM | duration | yes |
| AVGO | para:AVGO|xyz:AVGO | duration | yes |
| CRCL | flx:CRCL|xyz:CRCL | duration | yes |
| SILVER | flx:SILVER|km:SILVER | duration | yes |
| SILVER | km:SILVER|xyz:SILVER | duration | yes |
| PLTR | km:PLTR|xyz:PLTR | duration | yes |
| BABA | km:BABA|xyz:BABA | duration | yes |
| COPPER | flx:COPPER|xyz:COPPER | duration | yes |
| SILVER | cash:SILVER|km:SILVER | duration | yes |
| TSLA | flx:TSLA|km:TSLA | basis | yes |
| EWY | cash:EWY|xyz:EWY | duration | yes |
| USA100 | flx:USA100|km:USTECH | duration | yes |
| USA100 | flx:USA100|xyz:XYZ100 | duration | yes |
| TSLA | km:TSLA|xyz:TSLA | basis | yes |
| PLATINUM | flx:PLATINUM|xyz:PLATINUM | duration | yes |
| NVDA | flx:NVDA|km:NVDA | duration | yes |
| COIN | flx:COIN|xyz:COIN | duration | yes |
| NVDA | cash:NVDA|km:NVDA | duration | yes |
| NVDA | km:NVDA|xyz:NVDA | duration | yes |
| HOOD | cash:HOOD|xyz:HOOD | basis | yes |
| GOLD | flx:GOLD|km:GOLD | duration | yes |
| INTC | cash:INTC|xyz:INTC | duration | yes |
| GOOGL | km:GOOGL|xyz:GOOGL | duration | yes |
| TSLA | cash:TSLA|km:TSLA | duration | yes |
| NVDA | flx:NVDA|xyz:NVDA | duration | yes |
| GOOGL | cash:GOOGL|km:GOOGL | duration | yes |
| GOLD | km:GOLD|xyz:GOLD | duration | yes |
| GOLD | cash:GOLD|km:GOLD | duration | yes |
| SP500 | flx:USA500|km:US500 | duration | yes |
| SP500 | flx:USA500|xyz:SP500 | duration | yes |
| AAPL | km:AAPL|xyz:AAPL | duration | yes |
| NVDA | cash:NVDA|xyz:NVDA | duration | yes |
| META | cash:META|xyz:META | never-reaches-breakeven | yes |
| SILVER | flx:SILVER|xyz:SILVER | duration | yes |
| USA100 | mkts:USTECH|xyz:XYZ100 | never-reaches-breakeven | yes |
| EUR | km:EUR|xyz:EUR | duration | yes |
| SP500 | cash:USA500|flx:USA500 | duration | yes |
| GOLD | flx:GOLD|xyz:GOLD | duration | yes |
| TSLA | flx:TSLA|xyz:TSLA | duration | yes |
| SP500 | cash:USA500|km:US500 | never-reaches-breakeven | yes |
| AMZN | cash:AMZN|xyz:AMZN | never-reaches-breakeven | yes |
| SP500 | mkts:US500|xyz:SP500 | never-reaches-breakeven | yes |
| MSFT | cash:MSFT|xyz:MSFT | duration | yes |
| SILVER | cash:SILVER|xyz:SILVER | never-reaches-breakeven | yes |
| GOOGL | cash:GOOGL|xyz:GOOGL | never-reaches-breakeven | yes |
| USA100 | km:USTECH|xyz:XYZ100 | never-reaches-breakeven | yes |
| TSLA | cash:TSLA|xyz:TSLA | never-reaches-breakeven | yes |
| SP500 | cash:USA500|xyz:SP500 | never-reaches-breakeven | yes |
| SP500 | km:US500|xyz:SP500 | never-reaches-breakeven | yes |
| GOLD | cash:GOLD|xyz:GOLD | never-reaches-breakeven | yes |
| NVDA | cash:NVDA|flx:NVDA | duration | yes |
| SP500 | cash:USA500|mkts:US500 | never-reaches-breakeven | yes |
| GOLD | cash:GOLD|flx:GOLD | duration | yes |
| TSLA | cash:TSLA|flx:TSLA | duration | yes |
| SILVER | cash:SILVER|flx:SILVER | never-reaches-breakeven | yes |

### Sub-1h top-differential artifacts

`flx:XMR|hyna:XMR`, despite ranking first by mean absolute funding differential, is a venue-quality/erratic-funding artifact, not an opportunity: its 0.67h half-life and only 4.44% maker and 1.39% taker time above breakeven are consistent with whipsawing funding on the near-dead `hyna` venue already flagged in Studies 1–2.

Other pairs in the top-ten mean-differential cohort with sub-1h persistence are likewise treated as erratic-funding/venue-quality artifacts rather than capturable spreads:

| pair | mean |diff| APR | half-life h |
|---|---:|---:|
| flx:XMR|hyna:XMR | 1.4485 | 0.67 |
| para:AVGO|xyz:AVGO | 0.4190 | 0.98 |

## Pairwise results

| underlier | pair | mean |diff| APR [95% CI] | half-life h [95% CI] | > BE maker / taker [95% CI] | basis vol [95% CI] | basis p95 excursion [95% CI] |
|---|---|---:|---:|---:|---:|---:|
| XMR | flx:XMR|hyna:XMR | 1.4485 [1.2107, 1.7322] | 0.67 [0.40, 1.31] | 4.44% [3.37%, 5.57%] / 1.39% [0.88%, 1.95%] | 0.0180 [0.0153, 0.0207] | 0.0309 [0.0263, 0.0337] |
| MU | km:MU|xyz:MU | 0.5184 [0.4616, 0.5789] | 1.09 [0.78, 1.87] | 0.40% [0.18%, 0.67%] / 0.03% [0.00%, 0.09%] | 0.0041 [0.0035, 0.0048] | 0.0080 [0.0073, 0.0085] |
| PALLADIUM | flx:PALLADIUM|xyz:PALLADIUM | 0.4343 [0.3963, 0.4760] | 1.46 [1.12, 1.93] | 0.59% [0.20%, 1.07%] / 0.00% [0.00%, 0.00%] | 0.0067 [0.0059, 0.0076] | 0.0137 [0.0117, 0.0159] |
| AVGO | para:AVGO|xyz:AVGO | 0.4190 [0.3497, 0.4943] | 0.98 [0.64, 1.92] | 0.22% [0.00%, 0.56%] / 0.00% [0.00%, 0.00%] | 0.0068 [0.0059, 0.0076] | 0.0151 [0.0128, 0.0173] |
| CRCL | flx:CRCL|xyz:CRCL | 0.3727 [0.3423, 0.4074] | 1.30 [1.02, 1.70] | 0.35% [0.17%, 0.57%] / 0.02% [0.00%, 0.07%] | 0.0076 [0.0064, 0.0089] | 0.0147 [0.0130, 0.0170] |
| SILVER | flx:SILVER|km:SILVER | 0.3478 [0.2924, 0.4119] | 1.01 [0.80, 1.17] | 0.99% [0.61%, 1.45%] / 0.08% [0.00%, 0.20%] | 0.0019 [0.0017, 0.0021] | 0.0036 [0.0032, 0.0041] |
| SILVER | km:SILVER|xyz:SILVER | 0.3454 [0.2918, 0.4075] | 1.05 [0.77, 1.25] | 0.87% [0.51%, 1.27%] / 0.08% [0.00%, 0.20%] | 0.0016 [0.0014, 0.0018] | 0.0029 [0.0026, 0.0033] |
| PLTR | km:PLTR|xyz:PLTR | 0.3432 [0.2988, 0.3877] | 2.42 [1.95, 3.04] | 3.21% [2.26%, 4.19%] / 0.00% [0.00%, 0.00%] | 0.0031 [0.0028, 0.0034] | 0.0064 [0.0058, 0.0073] |
| BABA | km:BABA|xyz:BABA | 0.3381 [0.3076, 0.3696] | 1.86 [1.46, 2.37] | 0.59% [0.31%, 0.94%] / 0.00% [0.00%, 0.00%] | 0.0027 [0.0024, 0.0031] | 0.0053 [0.0047, 0.0056] |
| COPPER | flx:COPPER|xyz:COPPER | 0.3282 [0.2991, 0.3580] | 1.59 [1.21, 2.08] | 0.41% [0.19%, 0.68%] / 0.00% [0.00%, 0.00%] | 0.0060 [0.0057, 0.0063] | 0.0120 [0.0114, 0.0126] |
| SILVER | cash:SILVER|km:SILVER | 0.2995 [0.2576, 0.3502] | 1.04 [0.84, 1.24] | 0.78% [0.43%, 1.19%] / 0.00% [0.00%, 0.00%] | 0.0014 [0.0013, 0.0016] | 0.0027 [0.0024, 0.0031] |
| TSLA | flx:TSLA|km:TSLA | 0.2958 [0.2338, 0.3759] | 0.31 [0.22, 1.25] | 0.12% [0.02%, 0.26%] / 0.02% [0.00%, 0.07%] | 0.0028 [0.0023, 0.0034] | 0.0049 [0.0045, 0.0055] |
| EWY | cash:EWY|xyz:EWY | 0.2939 [0.2520, 0.3429] | 1.16 [0.72, 2.43] | 0.26% [0.03%, 0.61%] / 0.03% [0.00%, 0.10%] | 0.0014 [0.0013, 0.0016] | 0.0028 [0.0026, 0.0031] |
| USA100 | flx:USA100|km:USTECH | 0.2865 [0.2185, 0.3668] | 2.32 [1.11, 3.85] | 2.41% [1.47%, 3.50%] / 0.16% [0.00%, 0.37%] | 0.0104 [0.0094, 0.0114] | 0.0213 [0.0197, 0.0232] |
| USA100 | flx:USA100|xyz:XYZ100 | 0.2821 [0.2162, 0.3595] | 2.63 [1.22, 4.68] | 2.20% [1.26%, 3.30%] / 0.20% [0.00%, 0.49%] | 0.0103 [0.0094, 0.0111] | 0.0215 [0.0192, 0.0231] |
| TSLA | km:TSLA|xyz:TSLA | 0.2719 [0.2145, 0.3497] | 0.28 [0.19, 1.07] | 0.10% [0.00%, 0.24%] / 0.02% [0.00%, 0.07%] | 0.0016 [0.0014, 0.0018] | 0.0030 [0.0027, 0.0034] |
| PLATINUM | flx:PLATINUM|xyz:PLATINUM | 0.2601 [0.2383, 0.2861] | 1.60 [1.00, 2.38] | 0.25% [0.03%, 0.61%] / 0.00% [0.00%, 0.00%] | 0.0081 [0.0056, 0.0104] | 0.0081 [0.0072, 0.0099] |
| NVDA | flx:NVDA|km:NVDA | 0.2598 [0.2216, 0.2989] | 1.83 [1.49, 2.28] | 1.23% [0.78%, 1.79%] / 0.00% [0.00%, 0.00%] | 0.0030 [0.0028, 0.0033] | 0.0064 [0.0056, 0.0071] |
| COIN | flx:COIN|xyz:COIN | 0.2594 [0.2321, 0.2889] | 1.26 [1.04, 1.53] | 0.26% [0.11%, 0.46%] / 0.00% [0.00%, 0.00%] | 0.0068 [0.0060, 0.0075] | 0.0160 [0.0132, 0.0185] |
| NVDA | cash:NVDA|km:NVDA | 0.2486 [0.2148, 0.2841] | 1.48 [1.03, 2.06] | 0.39% [0.17%, 0.67%] / 0.00% [0.00%, 0.00%] | 0.0019 [0.0018, 0.0020] | 0.0040 [0.0037, 0.0043] |
| NVDA | km:NVDA|xyz:NVDA | 0.2400 [0.2182, 0.2634] | 1.46 [1.28, 1.71] | 0.08% [0.00%, 0.22%] / 0.00% [0.00%, 0.00%] | 0.0019 [0.0018, 0.0021] | 0.0040 [0.0036, 0.0044] |
| HOOD | cash:HOOD|xyz:HOOD | 0.2365 [0.1997, 0.2949] | 1.04 [0.26, 4.34] | 0.13% [0.00%, 0.31%] / 0.05% [0.00%, 0.15%] | 0.0015 [0.0013, 0.0017] | 0.0028 [0.0024, 0.0031] |
| GOLD | flx:GOLD|km:GOLD | 0.2343 [0.1986, 0.2734] | 1.50 [0.97, 2.39] | 0.54% [0.28%, 0.87%] / 0.00% [0.00%, 0.00%] | 0.0021 [0.0019, 0.0025] | 0.0041 [0.0038, 0.0046] |
| INTC | cash:INTC|xyz:INTC | 0.2285 [0.1935, 0.2810] | 1.04 [0.25, 58.59] | 0.18% [0.03%, 0.41%] / 0.05% [0.00%, 0.15%] | 0.0015 [0.0013, 0.0017] | 0.0032 [0.0026, 0.0037] |
| GOOGL | km:GOOGL|xyz:GOOGL | 0.2213 [0.2015, 0.2424] | 1.72 [1.29, 2.31] | 0.08% [0.00%, 0.21%] / 0.00% [0.00%, 0.00%] | 0.0019 [0.0017, 0.0021] | 0.0036 [0.0032, 0.0040] |
| TSLA | cash:TSLA|km:TSLA | 0.2207 [0.1914, 0.2530] | 1.73 [1.49, 2.06] | 0.66% [0.39%, 0.96%] / 0.00% [0.00%, 0.00%] | 0.0018 [0.0016, 0.0019] | 0.0035 [0.0031, 0.0039] |
| NVDA | flx:NVDA|xyz:NVDA | 0.2124 [0.1909, 0.2361] | 2.29 [1.48, 3.37] | 0.78% [0.32%, 1.37%] / 0.00% [0.00%, 0.00%] | 0.0047 [0.0039, 0.0054] | 0.0085 [0.0070, 0.0104] |
| GOOGL | cash:GOOGL|km:GOOGL | 0.2056 [0.1800, 0.2320] | 2.01 [1.56, 2.62] | 0.44% [0.23%, 0.67%] / 0.00% [0.00%, 0.00%] | 0.0020 [0.0018, 0.0022] | 0.0041 [0.0036, 0.0047] |
| GOLD | km:GOLD|xyz:GOLD | 0.2031 [0.1811, 0.2258] | 1.01 [0.78, 1.46] | 0.15% [0.05%, 0.28%] / 0.00% [0.00%, 0.00%] | 0.0014 [0.0013, 0.0014] | 0.0027 [0.0025, 0.0030] |
| GOLD | cash:GOLD|km:GOLD | 0.1917 [0.1675, 0.2195] | 1.04 [0.70, 1.72] | 0.21% [0.05%, 0.43%] / 0.00% [0.00%, 0.00%] | 0.0014 [0.0013, 0.0014] | 0.0027 [0.0025, 0.0029] |
| SP500 | flx:USA500|km:US500 | 0.1905 [0.1432, 0.2460] | 1.77 [0.85, 2.88] | 1.02% [0.41%, 1.71%] / 0.07% [0.00%, 0.21%] | 0.0032 [0.0027, 0.0036] | 0.0067 [0.0053, 0.0094] |
| SP500 | flx:USA500|xyz:SP500 | 0.1877 [0.1410, 0.2429] | 2.68 [1.60, 3.41] | 1.20% [0.47%, 2.04%] / 0.29% [0.04%, 0.66%] | 0.0035 [0.0029, 0.0041] | 0.0065 [0.0050, 0.0101] |
| AAPL | km:AAPL|xyz:AAPL | 0.1860 [0.1667, 0.2054] | 2.01 [1.61, 2.60] | 0.08% [0.00%, 0.15%] / 0.00% [0.00%, 0.00%] | 0.0020 [0.0015, 0.0025] | 0.0033 [0.0031, 0.0035] |
| NVDA | cash:NVDA|xyz:NVDA | 0.1724 [0.1552, 0.1909] | 1.31 [0.67, 2.97] | 0.05% [0.00%, 0.15%] / 0.00% [0.00%, 0.00%] | 0.0012 [0.0010, 0.0013] | 0.0021 [0.0019, 0.0024] |
| META | cash:META|xyz:META | 0.1722 [0.1610, 0.1839] | 1.67 [1.39, 2.04] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0011 [0.0010, 0.0013] | 0.0022 [0.0021, 0.0024] |
| SILVER | flx:SILVER|xyz:SILVER | 0.1684 [0.1499, 0.1872] | 0.66 [0.52, 0.86] | 0.04% [0.00%, 0.11%] / 0.00% [0.00%, 0.00%] | 0.0024 [0.0018, 0.0030] | 0.0037 [0.0033, 0.0041] |
| USA100 | mkts:USTECH|xyz:XYZ100 | 0.1628 [0.1090, 0.2196] | 0.56 [0.28, 1.03] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0007, 0.0013] | 0.0019 [0.0014, 0.0022] |
| EUR | km:EUR|xyz:EUR | 0.1615 [0.1271, 0.1993] | 0.98 [0.75, 2.75] | 0.18% [0.00%, 0.41%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0009, 0.0012] | 0.0021 [0.0019, 0.0024] |
| SP500 | cash:USA500|flx:USA500 | 0.1579 [0.1104, 0.2138] | 1.96 [0.91, 3.22] | 0.99% [0.34%, 1.74%] / 0.10% [0.00%, 0.27%] | 0.0037 [0.0032, 0.0043] | 0.0080 [0.0055, 0.0116] |
| GOLD | flx:GOLD|xyz:GOLD | 0.1469 [0.1260, 0.1710] | 1.69 [0.79, 5.79] | 0.26% [0.09%, 0.52%] / 0.02% [0.00%, 0.07%] | 0.0022 [0.0019, 0.0025] | 0.0040 [0.0037, 0.0044] |
| TSLA | flx:TSLA|xyz:TSLA | 0.1358 [0.1238, 0.1496] | 1.33 [1.04, 1.71] | 0.02% [0.00%, 0.07%] / 0.00% [0.00%, 0.00%] | 0.0029 [0.0024, 0.0034] | 0.0051 [0.0046, 0.0058] |
| SP500 | cash:USA500|km:US500 | 0.1334 [0.1214, 0.1457] | 1.11 [0.92, 1.32] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0019 [0.0018, 0.0021] | 0.0049 [0.0041, 0.0055] |
| AMZN | cash:AMZN|xyz:AMZN | 0.1316 [0.1221, 0.1417] | 1.22 [1.03, 1.46] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0012 [0.0011, 0.0014] | 0.0024 [0.0021, 0.0027] |
| SP500 | mkts:US500|xyz:SP500 | 0.1217 [0.0985, 0.1463] | 0.45 [0.25, 0.68] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0008 [0.0006, 0.0010] | 0.0017 [0.0012, 0.0023] |
| MSFT | cash:MSFT|xyz:MSFT | 0.1196 [0.1053, 0.1345] | 0.90 [0.47, 3.54] | 0.03% [0.00%, 0.08%] / 0.00% [0.00%, 0.00%] | 0.0011 [0.0010, 0.0012] | 0.0019 [0.0018, 0.0021] |
| SILVER | cash:SILVER|xyz:SILVER | 0.1193 [0.1047, 0.1363] | 0.55 [0.37, 0.78] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0009, 0.0011] | 0.0019 [0.0017, 0.0022] |
| GOOGL | cash:GOOGL|xyz:GOOGL | 0.1159 [0.1070, 0.1257] | 1.43 [1.10, 1.96] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0011 [0.0009, 0.0012] | 0.0019 [0.0017, 0.0022] |
| USA100 | km:USTECH|xyz:XYZ100 | 0.1158 [0.1049, 0.1277] | 0.79 [0.62, 1.00] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0012 [0.0010, 0.0013] | 0.0023 [0.0019, 0.0027] |
| TSLA | cash:TSLA|xyz:TSLA | 0.1108 [0.0995, 0.1235] | 1.30 [0.93, 1.78] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0009, 0.0011] | 0.0018 [0.0016, 0.0020] |
| SP500 | cash:USA500|xyz:SP500 | 0.1081 [0.0976, 0.1201] | 1.48 [1.09, 1.95] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0013 [0.0012, 0.0014] | 0.0032 [0.0028, 0.0035] |
| SP500 | km:US500|xyz:SP500 | 0.1042 [0.0951, 0.1146] | 1.09 [0.78, 1.65] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0009, 0.0011] | 0.0019 [0.0017, 0.0020] |
| GOLD | cash:GOLD|xyz:GOLD | 0.0949 [0.0855, 0.1055] | 0.78 [0.49, 1.31] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0010 [0.0009, 0.0010] | 0.0018 [0.0016, 0.0020] |
| NVDA | cash:NVDA|flx:NVDA | 0.0900 [0.0722, 0.1105] | 1.71 [0.71, 6.89] | 0.15% [0.02%, 0.32%] / 0.00% [0.00%, 0.00%] | 0.0045 [0.0038, 0.0053] | 0.0083 [0.0068, 0.0101] |
| SP500 | cash:USA500|mkts:US500 | 0.0847 [0.0679, 0.1057] | 0.35 [0.14, 0.53] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0008 [0.0005, 0.0009] | 0.0014 [0.0013, 0.0019] |
| GOLD | cash:GOLD|flx:GOLD | 0.0804 [0.0577, 0.1075] | 1.83 [0.67, 13.22] | 0.73% [0.19%, 1.42%] / 0.03% [0.00%, 0.08%] | 0.0023 [0.0020, 0.0028] | 0.0042 [0.0039, 0.0048] |
| TSLA | cash:TSLA|flx:TSLA | 0.0504 [0.0409, 0.0619] | 1.59 [1.22, 2.08] | 0.10% [0.00%, 0.22%] / 0.00% [0.00%, 0.00%] | 0.0030 [0.0024, 0.0036] | 0.0051 [0.0047, 0.0058] |
| SILVER | cash:SILVER|flx:SILVER | 0.0440 [0.0382, 0.0505] | 0.51 [0.35, 0.98] | 0.00% [0.00%, 0.00%] / 0.00% [0.00%, 0.00%] | 0.0024 [0.0017, 0.0032] | 0.0036 [0.0030, 0.0040] |

## F-E numeric quantities (no verdicts)

The episode comparison reports median contiguous hours above each breakeven against `2 ×` the same cost-amortization horizon. The basis comparison reports absolute-basis p95 against absolute-funding-differential p95 both as APR and as the return implied over the persistence horizon; the latter is the dimensionally comparable quantity.

| underlier | pair | maker median episode h / 2× horizon h | taker median episode h / 2× horizon h | basis p95 | funding |diff| p95 APR | p95 diff return over horizon | basis / horizon-diff ratio |
|---|---|---:|---:|---:|---:|---:|---:|
| XMR | flx:XMR|hyna:XMR | 1.00 / 1.34 | 1.00 / 1.34 | 0.030873 | 3.9455 | 0.00030267 | 102.00 |
| MU | km:MU|xyz:MU | 1.00 / 2.19 | 1.00 / 2.19 | 0.008025 | 2.3227 | 0.00028971 | 27.70 |
| PALLADIUM | flx:PALLADIUM|xyz:PALLADIUM | 1.00 / 2.91 | never (n=0) / 2.91 | 0.013668 | 1.4307 | 0.00023770 | 57.50 |
| AVGO | para:AVGO|xyz:AVGO | 1.00 / 1.97 | never (n=0) / 1.97 | 0.015075 | 1.6399 | 0.00018397 | 81.94 |
| CRCL | flx:CRCL|xyz:CRCL | 1.00 / 2.60 | 1.00 / 2.60 | 0.014699 | 1.4796 | 0.00021991 | 66.84 |
| SILVER | flx:SILVER|km:SILVER | 1.00 / 2.02 | 1.50 / 2.02 | 0.003629 | 1.2046 | 0.00013880 | 26.15 |
| SILVER | km:SILVER|xyz:SILVER | 1.00 / 2.10 | 1.50 / 2.10 | 0.002939 | 1.0543 | 0.00012627 | 23.27 |
| PLTR | km:PLTR|xyz:PLTR | 2.00 / 4.85 | never (n=0) / 4.85 | 0.006419 | 1.7802 | 0.00049236 | 13.04 |
| BABA | km:BABA|xyz:BABA | 1.00 / 3.71 | never (n=0) / 3.71 | 0.005260 | 1.4513 | 0.00030759 | 17.10 |
| COPPER | flx:COPPER|xyz:COPPER | 1.00 / 3.18 | never (n=0) / 3.18 | 0.011987 | 1.3941 | 0.00025271 | 47.43 |
| SILVER | cash:SILVER|km:SILVER | 1.00 / 2.07 | never (n=0) / 2.07 | 0.002710 | 1.0875 | 0.00012878 | 21.04 |
| TSLA | flx:TSLA|km:TSLA | 1.00 / 0.63 | 1.00 / 0.63 | 0.004865 | 1.4641 | 0.00005230 | 93.02 |
| EWY | cash:EWY|xyz:EWY | 1.50 / 2.31 | 1.00 / 2.31 | 0.002780 | 1.1084 | 0.00014625 | 19.01 |
| USA100 | flx:USA100|km:USTECH | 1.00 / 4.63 | 1.00 / 4.63 | 0.021267 | 1.2468 | 0.00032969 | 64.51 |
| USA100 | flx:USA100|xyz:XYZ100 | 1.00 / 5.27 | 1.00 / 5.27 | 0.021531 | 1.0253 | 0.00030817 | 69.87 |
| TSLA | km:TSLA|xyz:TSLA | 1.00 / 0.55 | 1.00 / 0.55 | 0.003006 | 1.1123 | 0.00003516 | 85.49 |
| PLATINUM | flx:PLATINUM|xyz:PLATINUM | 1.00 / 3.19 | never (n=0) / 3.19 | 0.008135 | 0.8549 | 0.00015585 | 52.20 |
| NVDA | flx:NVDA|km:NVDA | 1.00 / 3.66 | never (n=0) / 3.66 | 0.006350 | 1.5461 | 0.00032286 | 19.67 |
| COIN | flx:COIN|xyz:COIN | 1.00 / 2.53 | never (n=0) / 2.53 | 0.016000 | 1.1824 | 0.00017059 | 93.79 |
| NVDA | cash:NVDA|km:NVDA | 1.00 / 2.96 | never (n=0) / 2.96 | 0.003980 | 1.3127 | 0.00022197 | 17.93 |
| NVDA | km:NVDA|xyz:NVDA | 1.50 / 2.92 | never (n=0) / 2.92 | 0.003986 | 0.9593 | 0.00015970 | 24.96 |
| HOOD | cash:HOOD|xyz:HOOD | 2.50 / 2.07 | 2.00 / 2.07 | 0.002770 | 0.7180 | 0.00008490 | 32.63 |
| GOLD | flx:GOLD|km:GOLD | 1.00 / 3.00 | never (n=0) / 3.00 | 0.004088 | 0.9700 | 0.00016590 | 24.64 |
| INTC | cash:INTC|xyz:INTC | 1.50 / 2.08 | 2.00 / 2.08 | 0.003227 | 0.7863 | 0.00009326 | 34.60 |
| GOOGL | km:GOOGL|xyz:GOOGL | 1.50 / 3.45 | never (n=0) / 3.45 | 0.003576 | 0.9323 | 0.00018350 | 19.49 |
| TSLA | cash:TSLA|km:TSLA | 1.00 / 3.45 | never (n=0) / 3.45 | 0.003493 | 1.3660 | 0.00026928 | 12.97 |
| NVDA | flx:NVDA|xyz:NVDA | 1.50 / 4.59 | never (n=0) / 4.59 | 0.008541 | 0.6969 | 0.00018239 | 46.83 |
| GOOGL | cash:GOOGL|km:GOOGL | 1.00 / 4.02 | never (n=0) / 4.02 | 0.004135 | 1.0612 | 0.00024375 | 16.96 |
| GOLD | km:GOLD|xyz:GOLD | 1.00 / 2.01 | never (n=0) / 2.01 | 0.002729 | 0.7071 | 0.00008124 | 33.60 |
| GOLD | cash:GOLD|km:GOLD | 1.00 / 2.09 | never (n=0) / 2.09 | 0.002678 | 0.7158 | 0.00008537 | 31.37 |
| SP500 | flx:USA500|km:US500 | 1.00 / 3.55 | 2.00 / 3.55 | 0.006725 | 0.6496 | 0.00013160 | 51.10 |
| SP500 | flx:USA500|xyz:SP500 | 3.00 / 5.37 | 1.50 / 5.37 | 0.006458 | 0.5064 | 0.00015509 | 41.64 |
| AAPL | km:AAPL|xyz:AAPL | 1.00 / 4.02 | never (n=0) / 4.02 | 0.003319 | 0.8525 | 0.00019573 | 16.96 |
| NVDA | cash:NVDA|xyz:NVDA | 2.00 / 2.63 | never (n=0) / 2.63 | 0.002112 | 0.6329 | 0.00009497 | 22.24 |
| META | cash:META|xyz:META | never (n=0) / 3.34 | never (n=0) / 3.34 | 0.002195 | 0.4743 | 0.00009042 | 24.27 |
| SILVER | flx:SILVER|xyz:SILVER | 1.00 / 1.32 | never (n=0) / 1.32 | 0.003711 | 0.6291 | 0.00004754 | 78.05 |
| USA100 | mkts:USTECH|xyz:XYZ100 | never (n=0) / 1.12 | never (n=0) / 1.12 | 0.001937 | 0.7432 | 0.00004737 | 40.89 |
| EUR | km:EUR|xyz:EUR | 1.50 / 1.96 | never (n=0) / 1.96 | 0.002074 | 0.7524 | 0.00008400 | 24.69 |
| SP500 | cash:USA500|flx:USA500 | 3.00 / 3.92 | 1.50 / 3.92 | 0.007987 | 0.3737 | 0.00008365 | 95.49 |
| GOLD | flx:GOLD|xyz:GOLD | 1.00 / 3.38 | 1.00 / 3.38 | 0.004021 | 0.4907 | 0.00009467 | 42.48 |
| TSLA | flx:TSLA|xyz:TSLA | 1.00 / 2.67 | never (n=0) / 2.67 | 0.005145 | 0.5202 | 0.00007918 | 64.98 |
| SP500 | cash:USA500|km:US500 | never (n=0) / 2.21 | never (n=0) / 2.21 | 0.004873 | 0.4721 | 0.00005967 | 81.67 |
| AMZN | cash:AMZN|xyz:AMZN | never (n=0) / 2.44 | never (n=0) / 2.44 | 0.002380 | 0.4228 | 0.00005892 | 40.40 |
| SP500 | mkts:US500|xyz:SP500 | never (n=0) / 0.90 | never (n=0) / 0.90 | 0.001671 | 0.3253 | 0.00001676 | 99.75 |
| MSFT | cash:MSFT|xyz:MSFT | 1.00 / 1.80 | never (n=0) / 1.80 | 0.001940 | 0.4236 | 0.00004361 | 44.48 |
| SILVER | cash:SILVER|xyz:SILVER | never (n=0) / 1.09 | never (n=0) / 1.09 | 0.001907 | 0.3567 | 0.00002225 | 85.71 |
| GOOGL | cash:GOOGL|xyz:GOOGL | never (n=0) / 2.86 | never (n=0) / 2.86 | 0.001924 | 0.3809 | 0.00006210 | 30.99 |
| USA100 | km:USTECH|xyz:XYZ100 | never (n=0) / 1.57 | never (n=0) / 1.57 | 0.002279 | 0.4066 | 0.00003654 | 62.38 |
| TSLA | cash:TSLA|xyz:TSLA | never (n=0) / 2.61 | never (n=0) / 2.61 | 0.001793 | 0.4358 | 0.00006488 | 27.64 |
| SP500 | cash:USA500|xyz:SP500 | never (n=0) / 2.96 | never (n=0) / 2.96 | 0.003249 | 0.3537 | 0.00005979 | 54.35 |
| SP500 | km:US500|xyz:SP500 | never (n=0) / 2.18 | never (n=0) / 2.18 | 0.001867 | 0.3886 | 0.00004828 | 38.66 |
| GOLD | cash:GOLD|xyz:GOLD | never (n=0) / 1.56 | never (n=0) / 1.56 | 0.001814 | 0.2836 | 0.00002533 | 71.63 |
| NVDA | cash:NVDA|flx:NVDA | 1.00 / 3.42 | never (n=0) / 3.42 | 0.008318 | 0.2692 | 0.00005258 | 158.21 |
| SP500 | cash:USA500|mkts:US500 | never (n=0) / 0.70 | never (n=0) / 0.70 | 0.001422 | 0.2766 | 0.00001105 | 128.66 |
| GOLD | cash:GOLD|flx:GOLD | 1.00 / 3.66 | 1.00 / 3.66 | 0.004243 | 0.2264 | 0.00004735 | 89.62 |
| TSLA | cash:TSLA|flx:TSLA | 1.00 / 3.18 | never (n=0) / 3.18 | 0.005133 | 0.1181 | 0.00002147 | 239.10 |
| SILVER | cash:SILVER|flx:SILVER | never (n=0) / 1.03 | never (n=0) / 1.03 | 0.003597 | 0.1959 | 0.00001147 | 313.62 |

## Cost and coverage caveats

| pair | maker / taker round trip bps | maker / taker BE APR | market A half-spread | market B half-spread |
|---|---:|---:|---:|---:|
| flx:XMR|hyna:XMR | 3.3333 / 12.0313 | 4.3453 / 15.6840 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:MU|xyz:MU | 6.0000 / 20.0314 | 4.8104 / 16.0598 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:PALLADIUM|xyz:PALLADIUM | 6.0000 / 20.0314 | 3.6113 / 12.0566 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| para:AVGO|xyz:AVGO | 6.0000 / 20.0314 | 5.3481 / 17.8550 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:CRCL|xyz:CRCL | 6.0000 / 20.0314 | 4.0369 / 13.4775 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:SILVER|km:SILVER | 6.0000 / 20.0314 | 5.2073 / 17.3850 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:SILVER|xyz:SILVER | 6.0000 / 20.0314 | 5.0098 / 16.7255 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:PLTR|xyz:PLTR | 6.0000 / 20.0314 | 2.1694 / 7.2426 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:BABA|xyz:BABA | 6.0000 / 20.0314 | 2.8310 / 9.4516 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:COPPER|xyz:COPPER | 6.0000 / 20.0314 | 3.3098 / 11.0502 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:SILVER|km:SILVER | 6.0000 / 20.0314 | 5.0666 / 16.9151 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:TSLA|km:TSLA | 6.0000 / 20.0314 | 16.7955 / 56.0730 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:EWY|xyz:EWY | 6.0000 / 20.0314 | 4.5471 / 15.1810 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:USA100|km:USTECH | 6.0000 / 29.9483 | 2.2690 / 11.3257 | 5.6362 (measured_pre_2026-06-18_l4_quotes) | 0.3380 (measured_pre_2026-06-18_l4_quotes) |
| flx:USA100|xyz:XYZ100 | 6.0000 / 29.6121 | 1.9962 / 9.8521 | 5.6362 (measured_pre_2026-06-18_l4_quotes) | 0.1699 (measured_pre_2026-06-18_l4_quotes) |
| km:TSLA|xyz:TSLA | 6.0000 / 20.0314 | 18.9805 / 63.3680 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:PLATINUM|xyz:PLATINUM | 6.0000 / 20.0314 | 3.2912 / 10.9880 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:NVDA|km:NVDA | 6.0000 / 20.0314 | 2.8732 / 9.5925 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:COIN|xyz:COIN | 6.0000 / 20.0314 | 4.1587 / 13.8841 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:NVDA|km:NVDA | 6.0000 / 20.0314 | 3.5485 / 11.8468 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:NVDA|xyz:NVDA | 6.0000 / 20.0314 | 3.6041 / 12.0325 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:HOOD|xyz:HOOD | 6.0000 / 20.0314 | 5.0743 / 16.9410 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:GOLD|km:GOLD | 6.0000 / 20.0314 | 3.5082 / 11.7122 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:INTC|xyz:INTC | 6.0000 / 20.0314 | 5.0588 / 16.8892 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:GOOGL|xyz:GOOGL | 6.0000 / 20.0314 | 3.0486 / 10.1778 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:TSLA|km:TSLA | 6.0000 / 20.0314 | 3.0437 / 10.1617 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:NVDA|xyz:NVDA | 6.0000 / 20.0314 | 2.2926 / 7.6539 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:GOOGL|km:GOOGL | 6.0000 / 20.0314 | 2.6122 / 8.7211 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:GOLD|xyz:GOLD | 6.0000 / 20.0314 | 5.2219 / 17.4335 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:GOLD|km:GOLD | 6.0000 / 20.0314 | 5.0308 / 16.7956 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:USA500|km:US500 | 6.0000 / 23.6498 | 2.9615 / 11.6732 | 2.7574 (measured_pre_2026-06-18_l4_quotes) | 0.0675 (measured_pre_2026-06-18_l4_quotes) |
| flx:USA500|xyz:SP500 | 6.0000 / 23.6500 | 1.9591 / 7.7222 | 2.7574 (measured_pre_2026-06-18_l4_quotes) | 0.0676 (measured_pre_2026-06-18_l4_quotes) |
| km:AAPL|xyz:AAPL | 6.0000 / 20.0314 | 2.6132 / 8.7243 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:NVDA|xyz:NVDA | 6.0000 / 20.0314 | 3.9985 / 13.3494 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:META|xyz:META | 6.0000 / 20.0314 | 3.1475 / 10.5080 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:SILVER|xyz:SILVER | 6.0000 / 20.0314 | 7.9394 / 26.5064 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| mkts:USTECH|xyz:XYZ100 | 6.0000 / 19.3555 | 9.4138 / 30.3681 | 0.5079 (assumed_2x_study1_market_median) | 0.1699 (measured_pre_2026-06-18_l4_quotes) |
| km:EUR|xyz:EUR | 6.0000 / 20.0314 | 5.3744 / 17.9428 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:USA500|flx:USA500 | 6.0000 / 23.6498 | 2.6808 / 10.5668 | 0.0675 (measured_pre_2026-06-18_l4_quotes) | 2.7574 (measured_pre_2026-06-18_l4_quotes) |
| flx:GOLD|xyz:GOLD | 6.0000 / 20.0314 | 3.1100 / 10.3831 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| flx:TSLA|xyz:TSLA | 6.0000 / 20.0314 | 3.9416 / 13.1592 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:USA500|km:US500 | 6.0000 / 18.2700 | 4.7469 / 14.4544 | 0.0675 (measured_pre_2026-06-18_l4_quotes) | 0.0675 (measured_pre_2026-06-18_l4_quotes) |
| cash:AMZN|xyz:AMZN | 6.0000 / 20.0314 | 4.3049 / 14.3722 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| mkts:US500|xyz:SP500 | 6.0000 / 19.1508 | 11.6486 / 37.1800 | 0.5079 (assumed_2x_study1_market_median) | 0.0676 (measured_pre_2026-06-18_l4_quotes) |
| cash:MSFT|xyz:MSFT | 6.0000 / 20.0314 | 5.8289 / 19.4602 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:SILVER|xyz:SILVER | 6.0000 / 20.0314 | 9.6162 / 32.1043 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:GOOGL|xyz:GOOGL | 6.0000 / 20.0314 | 3.6807 / 12.2883 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| km:USTECH|xyz:XYZ100 | 6.0000 / 19.0157 | 6.6756 / 21.1570 | 0.3380 (measured_pre_2026-06-18_l4_quotes) | 0.1699 (measured_pre_2026-06-18_l4_quotes) |
| cash:TSLA|xyz:TSLA | 6.0000 / 20.0314 | 4.0304 / 13.4557 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:USA500|xyz:SP500 | 6.0000 / 18.2701 | 3.5497 / 10.8089 | 0.0675 (measured_pre_2026-06-18_l4_quotes) | 0.0676 (measured_pre_2026-06-18_l4_quotes) |
| km:US500|xyz:SP500 | 6.0000 / 18.2701 | 4.8292 / 14.7049 | 0.0675 (measured_pre_2026-06-18_l4_quotes) | 0.0676 (measured_pre_2026-06-18_l4_quotes) |
| cash:GOLD|xyz:GOLD | 6.0000 / 20.0314 | 6.7184 / 22.4300 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:NVDA|flx:NVDA | 6.0000 / 20.0314 | 3.0725 / 10.2579 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:USA500|mkts:US500 | 6.0000 / 19.1507 | 15.0138 / 47.9207 | 0.0675 (measured_pre_2026-06-18_l4_quotes) | 0.5079 (assumed_2x_study1_market_median) |
| cash:GOLD|flx:GOLD | 6.0000 / 20.0314 | 2.8694 / 9.5797 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:TSLA|flx:TSLA | 6.0000 / 20.0314 | 3.3018 / 11.0232 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |
| cash:SILVER|flx:SILVER | 6.0000 / 20.0314 | 10.2474 / 34.2116 | 0.5079 (assumed_2x_study1_market_median) | 0.5079 (assumed_2x_study1_market_median) |

Measured half-spreads are medians of hourly segment medians from valid, uncrossed pre-2026-06-18 L4 quotes for the eight Study-1 index markets. Post-2026-06-18 quotes are excluded as poisoned. Markets without that exact book coverage use the explicitly labeled assumption `2 × median(the eight measured Study-1 market half-spreads)`.

The index aliases are underlier hypotheses pre-registered by the study. Basis is measured as the median-demeaned log price ratio, so constant quote-unit differences are removed while transient relative-price dislocations remain. Candle closes are hourly REST observations, so intra-hour basis tails are not measured.

Sources: projected columns from `study3_universe.parquet`, `study3_funding_all.parquet`, `study3_candles_1h.parquet`, and `study3_fee_table.parquet`; pre-cutoff local quote files only. Machine-readable output: `data/reports/study3_se_spreads.parquet`.
