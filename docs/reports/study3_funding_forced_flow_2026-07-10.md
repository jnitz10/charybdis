# Study 3 S-F: funding → forced-flow linkage

Run date: 2026-07-10.

> **COVERAGE CAVEAT — This is only a two-market SKHX/SMSN linkage study over the proxy window 2026-05-27 to 2026-07-08. All 2,573 events are proxy-tagged repeated-taker burst events from the Study-2 fallback, not observations from a real liquidation feed. The results are not venue-wide and do not measure confirmed liquidations (Study-2 gap G2).**

The measured exposure interval is `2026-05-27 17:32:24.035000` through `2026-07-08 08:31:00.058000` (the first through last proxy-event timestamps, with the final timestamp included). Funding APR is the settled hourly rate multiplied by 24 × 365. A funding state starts only when its settlement is known and is held until the next settlement. Exposure is split at market × UTC-six-hour boundaries.

## Event rate by funding bucket

The denominator is explicit: `event rate = proxy-event count / market-hours of funding-bucket exposure`, pooled across SKHX and SMSN. Confidence intervals are percentile cluster-bootstrap intervals with 2,000 resamples of whole market × UTC-six-hour blocks, using `markout.py`'s shared bootstrap machinery.

| funding bucket | definition | proxy events | exposure market-hours | events / market-hour | 95% cluster-bootstrap CI | clusters |
| --- | --- | --- | --- | --- | --- | --- |
| negative | APR < 0% | 818 | 594.920 | 1.374975 | [1.234289, 1.521479] | 268 |
| 0_to_25pct | 0% <= APR < 25% | 497 | 385.000 | 1.290909 | [1.087387, 1.489692] | 216 |
| 25_to_100pct | 25% <= APR < 100% | 508 | 370.000 | 1.372973 | [1.182987, 1.572572] | 239 |
| ge_100pct | APR >= 100% | 750 | 648.033 | 1.157348 | [1.034886, 1.278416] | 252 |

## High-versus-low rate ratios

`high` is APR >= 100%; `low` is APR < 0%. Each ratio is `(high events / high exposure hours) / (low events / low exposure hours)`.

| scope | high/low rate ratio | 95% cluster-bootstrap CI | CI excludes 1 | clusters |
| --- | --- | --- | --- | --- |
| ALL | 0.8417 | [0.7267, 0.9805] | true | 322 |
| SKHX | 0.8405 | [0.6895, 1.0182] | false | 159 |
| SMSN | 0.8364 | [0.6659, 1.0510] | false | 163 |

Serial-correlation diagnostic (whole market as the cluster):

| scope | high/low rate ratio | market-clustered CI/status | market clusters |
| --- | --- | --- | --- |
| ALL | 0.8417 | insufficient evidence (low_cluster) | 2 |

## F-F status

| scope | high/low rate ratio | 95% CI | CI excludes 1 | clusters |
| --- | --- | --- | --- | --- |
| ALL | 0.8417 | [0.7267, 0.9805] | true | 322 |
| SKHX | 0.8405 | [0.6895, 1.0182] | false | 159 |
| SMSN | 0.8364 | [0.6659, 1.0510] | false | 163 |

The per-market CIs both include 1: there is no timing effect; funding's role is market-selection only. The pooled point estimate is below 1, opposite the ‘high funding → more events’ hypothesis.

## Leading-indicator hazard table

Conditioning observations are hourly funding settlements with a complete forward outcome window. The bucket at time `t` uses only the latest same-market settlement at or before `t`; the binary outcome checks forward for a same-market proxy event in `(t, t+horizon]`. No later funding value is used for conditioning.

The 24-hour hazard is coverage-limited and uninformative for these two near-continuous markets: its bucket probabilities are saturated near a base rate of 1. The 2-hour horizon is reported as the discriminating view.

| scope | horizon hours | funding bucket at t | conditioning observations | event within horizon | P(event within horizon) | coverage diagnostic |
| --- | --- | --- | --- | --- | --- | --- |
| ALL | 24 | negative | 580 | 541 | 0.9328 | saturated / uninformative |
| ALL | 24 | 0_to_25pct | 383 | 360 | 0.9399 | saturated / uninformative |
| ALL | 24 | 25_to_100pct | 364 | 334 | 0.9176 | saturated / uninformative |
| ALL | 24 | ge_100pct | 623 | 609 | 0.9775 | saturated / uninformative |
| ALL | 2 | negative | 594 | 447 | 0.7525 | informative |
| ALL | 2 | 0_to_25pct | 385 | 265 | 0.6883 | informative |
| ALL | 2 | 25_to_100pct | 369 | 272 | 0.7371 | informative |
| ALL | 2 | ge_100pct | 646 | 477 | 0.7384 | informative |
| SKHX | 24 | negative | 261 | 246 | 0.9425 | saturated / uninformative |
| SKHX | 24 | 0_to_25pct | 207 | 196 | 0.9469 | saturated / uninformative |
| SKHX | 24 | 25_to_100pct | 172 | 160 | 0.9302 | saturated / uninformative |
| SKHX | 24 | ge_100pct | 335 | 328 | 0.9791 | saturated / uninformative |
| SKHX | 2 | negative | 267 | 205 | 0.7678 | informative |
| SKHX | 2 | 0_to_25pct | 208 | 164 | 0.7885 | informative |
| SKHX | 2 | 25_to_100pct | 174 | 141 | 0.8103 | informative |
| SKHX | 2 | ge_100pct | 348 | 253 | 0.7270 | informative |
| SMSN | 24 | negative | 319 | 295 | 0.9248 | saturated / uninformative |
| SMSN | 24 | 0_to_25pct | 176 | 164 | 0.9318 | saturated / uninformative |
| SMSN | 24 | 25_to_100pct | 192 | 174 | 0.9062 | saturated / uninformative |
| SMSN | 24 | ge_100pct | 288 | 281 | 0.9757 | saturated / uninformative |
| SMSN | 2 | negative | 327 | 242 | 0.7401 | informative |
| SMSN | 2 | 0_to_25pct | 177 | 101 | 0.5706 | informative |
| SMSN | 2 | 25_to_100pct | 195 | 131 | 0.6718 | informative |
| SMSN | 2 | ge_100pct | 298 | 224 | 0.7517 | informative |

## 1.6 Wallet bridge

Minimum forward window: **24 hours**. Right-censored high-APR BUY wallets: **88**.

| cohort/control | eligible wallets | later reappearance fraction | high-APR BUY minus control |
| --- | --- | --- | --- |
| high-APR BUY cohort | 1300 | 0.6854 | 0.0000 |
| low-APR BUY control (<0% or 0-25%) | 1388 | 0.7010 | -0.0156 |
| >=100% APR SELL control | 1333 | 0.6707 | 0.0147 |
| full proxy-wallet population | 3423 | 0.5235 | 0.1619 |

The wallet bridge shows NO funding-specific linkage.

## Secondary sign × size-decile cut

Absolute-APR size deciles are weighted by market-hours; the sign is retained separately. These are secondary descriptive rates, not the F-F ratio definition.

| sign × absolute-APR decile | definition | proxy events | exposure market-hours | events / market-hour | 95% cluster-bootstrap CI | clusters |
| --- | --- | --- | --- | --- | --- | --- |
| negative_D01 | exposure-weighted absolute-APR decile, sign retained | 22 | 18.000 | 1.222225 | [0.625002, 1.823524] | 18 |
| negative_D02 | exposure-weighted absolute-APR decile, sign retained | 81 | 52.000 | 1.557693 | [1.115328, 2.044460] | 56 |
| negative_D03 | exposure-weighted absolute-APR decile, sign retained | 96 | 85.000 | 1.129411 | [0.821053, 1.463930] | 79 |
| negative_D04 | exposure-weighted absolute-APR decile, sign retained | 118 | 74.000 | 1.594596 | [1.150002, 2.055553] | 72 |
| negative_D05 | exposure-weighted absolute-APR decile, sign retained | 99 | 75.460 | 1.311951 | [0.880874, 1.745686] | 81 |
| negative_D06 | exposure-weighted absolute-APR decile, sign retained | 114 | 66.000 | 1.727274 | [1.285662, 2.181859] | 65 |
| negative_D07 | exposure-weighted absolute-APR decile, sign retained | 75 | 57.000 | 1.315790 | [0.874949, 1.770495] | 54 |
| negative_D08 | exposure-weighted absolute-APR decile, sign retained | 60 | 55.460 | 1.081861 | [0.711869, 1.508797] | 55 |
| negative_D09 | exposure-weighted absolute-APR decile, sign retained | 100 | 57.000 | 1.754388 | [1.358457, 2.138063] | 57 |
| negative_D10 | exposure-weighted absolute-APR decile, sign retained | 53 | 55.000 | 0.963637 | [0.557693, 1.423744] | 45 |
| nonnegative_D01 | exposure-weighted absolute-APR decile, sign retained | 211 | 182.000 | 1.159340 | [0.880001, 1.473084] | 111 |
| nonnegative_D02 | exposure-weighted absolute-APR decile, sign retained | 210 | 148.000 | 1.418919 | [1.141892, 1.729045] | 112 |
| nonnegative_D03 | exposure-weighted absolute-APR decile, sign retained | 149 | 114.000 | 1.307016 | [1.000000, 1.666794] | 107 |
| nonnegative_D04 | exposure-weighted absolute-APR decile, sign retained | 170 | 126.000 | 1.349206 | [1.076228, 1.629678] | 125 |
| nonnegative_D05 | exposure-weighted absolute-APR decile, sign retained | 183 | 125.000 | 1.464000 | [1.129255, 1.830713] | 118 |
| nonnegative_D06 | exposure-weighted absolute-APR decile, sign retained | 166 | 133.000 | 1.248121 | [0.985187, 1.535797] | 126 |
| nonnegative_D07 | exposure-weighted absolute-APR decile, sign retained | 155 | 143.000 | 1.083917 | [0.847182, 1.335621] | 132 |
| nonnegative_D08 | exposure-weighted absolute-APR decile, sign retained | 179 | 144.000 | 1.243055 | [0.970442, 1.546225] | 130 |
| nonnegative_D09 | exposure-weighted absolute-APR decile, sign retained | 190 | 143.033 | 1.328362 | [1.081375, 1.602717] | 103 |
| nonnegative_D10 | exposure-weighted absolute-APR decile, sign retained | 142 | 145.000 | 0.979310 | [0.788452, 1.191502] | 97 |

## Reproducibility and scope

Inputs were projected with PyArrow to only the columns used from `study3_funding_all.parquet`, `study3_universe.parquet`, and `forced_flow_events_proxy.parquet`. This run made no network calls and touched no order, wallet, or key paths. Spend remained $116.92; task spend was $0.
