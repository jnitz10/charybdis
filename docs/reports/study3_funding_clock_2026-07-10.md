# Study 3 S-D — Funding-clock effects

**Analysis date:** 2026-07-10. **Mode:** research only; no orders, wallets, keys, or paid calls. Total study spend remains $116.92.

## Settlement brackets and F-D interval geometry

Returns are log first-open to last-close returns across 1m bars whose last-trade or candle-close timestamps lie strictly inside each open bracket. This makes the ±1m brackets measurable without borrowing an outside bar. Negative brackets end at settlement and never use a post-settlement trade; positive brackets begin at settlement. The baseline is a plain same-market `t+30m` within-hour placebo with the same directional width. It shares hour-level shocks with the event and is verified not to overlap the ±10m windows around the current or adjacent hourly settlements. No Study-2 calendar-day matching machinery is run.

F-D is reported separately for the two full-window L4-derived markets and the eight markets limited to the cached 3.5-day candles.

### SKHX/SMSN full-window L4

| bracket | return (95% CI) | +30m baseline (95% CI) | F-D separation | n | clusters |
|---:|---:|---:|---|---:|---:|
| -10m | -0.0108% [-0.0282%, 0.0066%] | 0.0210% [0.0019%, 0.0398%] | DOES NOT SEPARATE | 2466 | 446 |
| -5m | -0.0118% [-0.0253%, 0.0011%] | 0.0093% [-0.0047%, 0.0229%] | DOES NOT SEPARATE | 2355 | 442 |
| -1m | -0.0038% [-0.0120%, 0.0044%] | 0.0083% [0.0005%, 0.0155%] | DOES NOT SEPARATE | 2011 | 420 |
| +1m | 0.0009% [-0.0152%, 0.0154%] | 0.0102% [0.0003%, 0.0196%] | DOES NOT SEPARATE | 2062 | 420 |
| +5m | 0.0108% [-0.0097%, 0.0308%] | 0.0017% [-0.0159%, 0.0192%] | DOES NOT SEPARATE | 2388 | 441 |
| +10m | 0.0147% [-0.0099%, 0.0403%] | 0.0101% [-0.0130%, 0.0326%] | DOES NOT SEPARATE | 2498 | 445 |

### 8-market 3.5-day candles

| bracket | return (95% CI) | +30m baseline (95% CI) | F-D separation | n | clusters |
|---:|---:|---:|---|---:|---:|
| -10m | 0.0148% [-0.0430%, 0.0779%] | -0.0020% [-0.0628%, 0.0603%] | DOES NOT SEPARATE | 651 | 116 |
| -5m | 0.0198% [-0.0231%, 0.0660%] | 0.0071% [-0.0375%, 0.0541%] | DOES NOT SEPARATE | 651 | 116 |
| -1m | 0.0037% [-0.0153%, 0.0247%] | 0.0102% [-0.0085%, 0.0303%] | DOES NOT SEPARATE | 651 | 116 |
| +1m | -0.0283% [-0.0495%, -0.0083%] | -0.0253% [-0.0650%, 0.0084%] | DOES NOT SEPARATE | 651 | 116 |
| +5m | -0.0043% [-0.0455%, 0.0379%] | -0.0060% [-0.0638%, 0.0501%] | DOES NOT SEPARATE | 651 | 116 |
| +10m | 0.0167% [-0.0391%, 0.0766%] | -0.0013% [-0.0736%, 0.0707%] | DOES NOT SEPARATE | 651 | 116 |

### Per-market bracket coverage

| market | source/window | first settlement | last settlement | -10m | -5m | -1m | +1m | +5m | +10m |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| xyz:KIOXIA | 8-market 3.5-day candles | 2026-07-07 12:00 | 2026-07-10 19:00 | 80 | 80 | 80 | 80 | 80 | 80 |
| xyz:BIRD | 8-market 3.5-day candles | 2026-07-07 09:00 | 2026-07-10 19:00 | 83 | 83 | 83 | 83 | 83 | 83 |
| xyz:BOT | 8-market 3.5-day candles | 2026-07-07 10:00 | 2026-07-10 19:00 | 82 | 82 | 82 | 82 | 82 | 82 |
| xyz:SKHX | SKHX/SMSN full-window L4 | 2026-05-08 00:00 | 2026-07-08 08:00 | 1278 | 1250 | 1137 | 1147 | 1250 | 1288 |
| xyz:SOFTBANK | 8-market 3.5-day candles | 2026-07-07 12:00 | 2026-07-10 19:00 | 80 | 80 | 80 | 80 | 80 | 80 |
| xyz:HYUNDAI | 8-market 3.5-day candles | 2026-07-07 12:00 | 2026-07-10 19:00 | 80 | 80 | 80 | 80 | 80 | 80 |
| xyz:SMSN | SKHX/SMSN full-window L4 | 2026-05-08 00:00 | 2026-07-08 08:00 | 1188 | 1105 | 874 | 915 | 1138 | 1210 |
| xyz:KR200 | 8-market 3.5-day candles | 2026-07-07 12:00 | 2026-07-10 19:00 | 80 | 80 | 80 | 80 | 80 | 80 |
| xyz:PURRDAT | 8-market 3.5-day candles | 2026-07-07 09:00 | 2026-07-10 19:00 | 83 | 83 | 83 | 83 | 83 | 83 |
| xyz:MINIMAX | 8-market 3.5-day candles | 2026-07-07 09:00 | 2026-07-10 19:00 | 83 | 83 | 83 | 83 | 83 | 83 |

Funding-sign and funding-size-decile splits, each with the same event/baseline CIs and separation status, are in `data/reports/study3_sd_brackets.parquet`.

## Premium decay into settlement

- SKHX: mean mark/oracle premium moved from 0.1163% at minute -10 to 0.0957% at minute -1 (n=98802 observations across these minute buckets).
- SMSN: mean mark/oracle premium moved from 0.0780% at minute -10 to 0.0631% at minute -1 (n=98802 observations across these minute buckets).

Coverage: 996 on-disk oracle files; 197604 observations in minutes -10..-1.

## Repeat-wallet signed taker flow

Negative signed notional is sell-taker flow (short-opening proxy); positive is buy-taker flow (short-closing proxy). A repeat wallet has at least two trades across its ±10m settlement window. This is a flow proxy, not a reconstructed position.

| market | metric | estimate (95% CI) | n settlements | clusters |
|---|---|---:|---:|---:|
| all | pre_signed_notional | $-19,823 [$-39,250, $-131] | 1844 | 315 |
| all | post_signed_notional | $-6,380 [$-25,453, $12,252] | 1844 | 315 |
| all | short_open_close_share | 6.0122% [5.6765%, 6.3388%] | 1844 | 315 |
| all | baseline_short_open_close_share | 5.9616% [5.6211%, 6.3036%] | 1825 | 314 |
| all | short_open_close_share_difference | 0.0896% [-0.3161%, 0.4919%] | 1825 | 314 |
| xyz:SKHX | pre_signed_notional | $-36,900 [$-78,666, $2,109] | 935 | 158 |
| xyz:SKHX | post_signed_notional | $-10,431 [$-48,164, $25,795] | 935 | 158 |
| xyz:SKHX | short_open_close_share | 5.4703% [5.0733%, 5.8704%] | 935 | 158 |
| xyz:SKHX | baseline_short_open_close_share | 5.3396% [4.9619%, 5.7419%] | 930 | 158 |
| xyz:SKHX | short_open_close_share_difference | 0.1522% [-0.2959%, 0.5956%] | 930 | 158 |
| xyz:SMSN | pre_signed_notional | $-2,258 [$-8,546, $3,850] | 909 | 157 |
| xyz:SMSN | post_signed_notional | $-2,213 [$-8,726, $4,284] | 909 | 157 |
| xyz:SMSN | short_open_close_share | 6.5696% [6.0141%, 7.1216%] | 909 | 157 |
| xyz:SMSN | baseline_short_open_close_share | 6.6079% [6.0645%, 7.1637%] | 895 | 156 |
| xyz:SMSN | short_open_close_share_difference | 0.0246% [-0.6719%, 0.7292%] | 895 | 156 |

`baseline_short_open_close_share` applies the identical repeat-wallet rule around `t+30m`; `short_open_close_share_difference` is the paired settlement share minus that baseline. A difference interval spanning zero indicates no measured settlement-specific wallet pattern.

Coverage: 2650 SKHX/SMSN L4 files found; 776 skipped for absent `user_taker` or corruption; 87411 settlement-window and 81036 baseline-window repeat-wallet rows; 1825 paired market-settlements.

## Coverage and prediction framing

The scoped set is `xyz:KIOXIA, xyz:BIRD, xyz:BOT, xyz:SKHX, xyz:SOFTBANK, xyz:HYUNDAI, xyz:SMSN, xyz:KR200, xyz:PURRDAT, xyz:MINIMAX`. It is the top ten by share of funding hours at ≥100% APR among markets with at least 168 funding observations; SKHX and SMSN are included. The common REST span is 2026-02-19T00:00:00 through 2026-07-10T20:00:00 UTC. Estimated REST page calls before harvest: 410; actual network calls: 0. A cache-only rerun made zero network calls.

SKHX/SMSN bracket inference uses full on-disk L4 coverage aggregated to 1m bars. The other eight markets remain explicitly limited to the most recent roughly 5,000 cached REST candles per market (about 3.5 days). That short window is not funding-poor: the original ten-market cached window contains 584 settlements at ≥100% compounded APR. The limitation is temporal breadth, not absence of the target regime. No paid source was used to fill older minutes.

G-F2 keeps the prediction framing: T4 observed R² at minute 50 of 0.962 (≥0.95) with real iid-excess, consistent with premium-mechanical settlement funding. Long-lead predictability remains moderate, so these clock-conditioned measurements should not be read as uniformly knowable far ahead of settlement.

All numeric CIs use the existing Study-1 nonparametric cluster bootstrap (2,000 resamples, seed 0, min G=5), clustered by market × UTC 6-hour bucket. `INSUFFICIENT CLUSTERS` replaces numeric interval claims below the minimum. F-D separation status is reported per bracket and coverage cohort; no pooled overall verdict is rendered.

## KEY_DECISIONS

- High-funding scope: top ten by ≥100% APR time share with at least one week of hourly observations, including SKHX/SMSN.
- SKHX/SMSN: aggregate every usable on-disk L4 file by exchange-time minute; open is the first trade price, close is the last, and the bar timestamp is the last trade's `time_exchange`. The eight other markets retain their deterministic widest/latest cached 1m candle file.
- Brackets: open intervals `(t−h,t)` for negative h and `(t,t+h)` for positive h; include only bars whose last-trade/candle-close timestamp is strictly inside and measure first open to last close. Controls mirror these around `t+:30`.
- Settlement timestamps in funding history are normalized to their UTC hour because source rows carry small millisecond transport offsets.
