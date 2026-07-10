# Study 3 S-B mechanics reconciliation — 2026-07-10

## Scope and coverage

Markets: `xyz:SKHX`, `xyz:SMSN`. Oracle inventory: SKHX 498 files and SMSN 498 files; both span `2026061716` through `2026070809` with `0` partition gaps.
The complete-hour regression window is `2026-06-17T17:00:00Z` through `2026-07-08T09:00:00Z` (986 market-hours). Completeness requires observations in minute 0 and minute 59 and no run of more than 5 consecutive missing minute buckets; excluded hours are removed uniformly from the hourly regression and every minute-curve point. Oracle data starts 2026-06-17, so S-B is only an approximately three-week study (20.75 days of feed partitions); funding history before that date is outside this reconciliation.

The feed uses bare coin identifiers. SKHX and SMSN are single-dex xyz coins and are unambiguous. SP500 was not included: its bare identifier collides across dexes, the files contain no dex column, and no contemporaneous per-dex REST oracle-price history exists in the scoped cache for historical price-cluster labeling.

G-F1 listing of every hourly extension prefix after 2026-07-08 09:00 returned zero objects. Dry-run: 0 files, 0 bytes, `$0.00`, projected cumulative meter `$116.92`; no GET/download was run and Study-3 new spend remained `$0.00`.

## Mechanical prediction and regression setup

For settlement `h`, samples satisfy `floor(time_exchange, 1h) = h-1`, hence every included sample is in `[h-1,h)` and strictly precedes `h`. No future sample is backfilled. The raw hourly premium is the arithmetic mean of `(mark_px-oracle_px)/oracle_px`; ticks with `oracle_px == 0` are skipped. The roughly three-second feed cadence makes this the discrete sampled-hour average. Partial-minute `m` predictions use only samples whose timestamp minute is `<=m`, over the same complete-hour set.

Fixed prediction: `pred = clip(0.5 * (P + clip(0.0001 - P, -0.0005, 0.0005)) / 8, -0.04, 0.04)`, where `P` is the sampled hourly average. OLS is `realized = intercept + slope * pred + residual`; R-squared includes an intercept. The prediction itself has no fitted slope or intercept.

With clamp width, multiplier, divisor, and cap fixed, an empirical grid over interest `[-0.001,0.001]` in 0.0000005 steps minimizes raw prediction RMSE at interest `0.0001380` (RMSE `0.321993` bps/hr); the fixed prediction above uses the pre-specified core-interest candidate `0.0001000`. This is the empirical clamp/interest identity measurement; it does not label the HIP-3 interest term as independently verified.

| scope | n | intercept (funding/hr) | slope | R-squared |
|---|---:|---:|---:|---:|
| ALL | 986 | 0.0000006744 | 1.13387994 | 0.99291893 |
| xyz:SKHX | 493 | 0.0000012121 | 1.12279478 | 0.99381665 |
| xyz:SMSN | 493 | 0.0000001545 | 1.14869448 | 0.99203796 |

## 1.5 Endpoint feed reconciliation

Mechanical formula R-squared: `0.99291893`. Raw oracle-premium-alone R-squared: `0.99570558`. OLS slope: `1.13387994`. OLS intercept: `0.0000006744` funding/hr. Mean raw residual: `0.089056` bps/hr.

Label: `feed-reconciliation / formula-consistency check`. CoinAPI oracle premium reproduces Hyperliquid realized funding to R-squared approximately 0.99, up to an approximately 13% affine scale. The mechanics add no correlation over raw premium; the clamp nonlinearity lowers R-squared by `0.00278664` relative to raw premium alone.

The on-disk `data/rest_cache/9b3fcc2b416006efa8e49efc06cb47716bfe74778a6864b58de856a8a1a02d15.json` `perpDexs` snapshot reports `assetToFundingMultiplier=0.5` for both `xyz:SKHX` and `xyz:SMSN`. T0 (`docs/reports/study3_fees_and_formula.md`) records that HIP-3 multiplier and interest are deployer-configurable. With configured multiplier 0.5 confirmed, slope `1.13387994` implies an affine-equivalent multiplier `0.566940`; the approximately 13% multiplicative identity gap is structural miscalibration, not residual noise. `predicted_funding` is reconciled only up to this affine scale and must not be consumed as an absolute funding level.

## Sample counts per settlement hour

| scope | hours | min samples | median samples | max samples |
|---|---:|---:|---:|---:|
| ALL | 986 | 1149 | 1198.0 | 1200 |
| xyz:SKHX | 493 | 1149 | 1198.0 | 1200 |
| xyz:SMSN | 493 | 1149 | 1198.0 | 1200 |

## Residual distribution (bps/hr)

| min | p01 | p05 | p25 | p50 | p75 | p95 | p99 | max | mean | RMSE |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| -1.263941 | -0.748291 | -0.401968 | -0.150048 | 0.167335 | 0.309390 | 0.457470 | 0.670507 | 2.080865 | 0.089056 | 0.322063 |

## Residual split by oracle update class (bps/hr)

An hour is labeled Fallback when any included sample is Fallback; otherwise it is Deployer.

| update_class | hours | mean residual | median residual | RMSE |
|---|---:|---:|---:|---:|
| Deployer | 980 | 0.090048 | 0.169729 | 0.322894 |
| Fallback | 6 | -0.072922 | 0.000000 | 0.127195 |

Fallback minus Deployer mean-residual difference: `-0.162969` bps/hr.

Hourly ±4% cap-hit count: `0`.

## Clamp regime split

Clamp-INACTIVE means the inner clamp does not bind and the mechanical prediction is constant; clamp-ACTIVE means the premium lies outside that constant-output band. The blended endpoint R-squared is shown above; the subsets are:

| regime | market-hours | within-subset R-squared |
|---|---:|---:|
| clamp-INACTIVE | 190 | 0.00000000 |
| clamp-ACTIVE | 796 | 0.99310338 |

The constant-output inactive predictor explains no within-subset variation; the active subset carries the blended feed-reconciliation correlation.

## IID partial-observation floor

The primary F-B comparison is an order-agnostic iid partial-observation floor. For each minute and each of 100 seeds (base seed 0), the Monte Carlo uses every hour's actual observed and full sample counts and draws exchangeable iid observed-subset and unobserved-complement sums. This is equivalent to uniformly drawing the minute's observed sample count without regard to order from an iid full hour. The partial-versus-full iid R-squared is attenuated by the empirical full-hour realized-funding endpoint R-squared so the null uses the same realized target as the observed statistic. Iid excess is observed R-squared minus that floor.

Seed stability: across the 60 minute points, the maximum seed-to-seed iid-floor variance is `0.0007053995`, the mean variance is `0.0003408918`, and the maximum standard error of the 100-seed mean is `0.0026559358`.

## Intra-hour sample-timing/drift diagnostic (secondary)

Label: `intra-hour sample-timing/drift diagnostic`. For each of 100 shuffles (seed 0), premium samples are randomly reassigned to the hour's observed minute labels within each market-hour. This preserves each hour's near-constant premium level and is therefore NOT the F-B routing input. When observed R-squared is below shuffle R-squared, a contiguous-early window is a worse estimator than a random spread subsample of the same size, implying within-hour premium drift.

| minute | observed_r2 | iid_floor | iid_excess | shuffle_r2 | market-hours | cumulative samples |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.31613548 | 0.01773390 | 0.29840159 | 0.96665129 | 986 | 19596 |
| 1 | 0.33734445 | 0.03349443 | 0.30385003 | 0.97960493 | 986 | 39268 |
| 2 | 0.36409270 | 0.05075130 | 0.31334140 | 0.98408880 | 986 | 58944 |
| 3 | 0.39051506 | 0.06726297 | 0.32325208 | 0.98632291 | 986 | 78596 |
| 4 | 0.41612311 | 0.08535095 | 0.33077217 | 0.98772294 | 986 | 98232 |
| 5 | 0.44498995 | 0.09848926 | 0.34650069 | 0.98865280 | 986 | 117900 |
| 6 | 0.47519335 | 0.11772917 | 0.35746417 | 0.98938354 | 986 | 137572 |
| 7 | 0.50403091 | 0.13322174 | 0.37080917 | 0.98986598 | 986 | 157258 |
| 8 | 0.53087047 | 0.14823622 | 0.38263425 | 0.99022415 | 986 | 176946 |
| 9 | 0.55623266 | 0.16767970 | 0.38855296 | 0.99054038 | 986 | 196620 |
| 10 | 0.58029150 | 0.18231963 | 0.39797187 | 0.99081650 | 986 | 216304 |
| 11 | 0.60223677 | 0.20034839 | 0.40188838 | 0.99104673 | 986 | 235974 |
| 12 | 0.62056969 | 0.21536362 | 0.40520607 | 0.99120428 | 986 | 255660 |
| 13 | 0.63574863 | 0.23502619 | 0.40072244 | 0.99139934 | 986 | 275340 |
| 14 | 0.65019207 | 0.24818723 | 0.40200484 | 0.99152635 | 986 | 295022 |
| 15 | 0.66323184 | 0.26533579 | 0.39789605 | 0.99163207 | 986 | 314694 |
| 16 | 0.67473419 | 0.28138346 | 0.39335073 | 0.99173319 | 986 | 334380 |
| 17 | 0.68572029 | 0.29919496 | 0.38652533 | 0.99181816 | 986 | 354016 |
| 18 | 0.69586045 | 0.31315635 | 0.38270410 | 0.99187019 | 986 | 373668 |
| 19 | 0.70569957 | 0.33140264 | 0.37429693 | 0.99193156 | 986 | 393318 |
| 20 | 0.71639142 | 0.34408530 | 0.37230611 | 0.99199957 | 986 | 413004 |
| 21 | 0.72651088 | 0.36644151 | 0.36006937 | 0.99203927 | 986 | 432688 |
| 22 | 0.73614486 | 0.38152475 | 0.35462011 | 0.99211025 | 986 | 452372 |
| 23 | 0.74545245 | 0.39531088 | 0.35014157 | 0.99217177 | 986 | 472074 |
| 24 | 0.75531210 | 0.41118801 | 0.34412410 | 0.99222444 | 986 | 491756 |
| 25 | 0.76499090 | 0.43277933 | 0.33221157 | 0.99226073 | 986 | 511428 |
| 26 | 0.77465797 | 0.44837128 | 0.32628669 | 0.99231283 | 986 | 531104 |
| 27 | 0.78410965 | 0.46504416 | 0.31906548 | 0.99234876 | 986 | 550786 |
| 28 | 0.79350998 | 0.47839166 | 0.31511832 | 0.99238173 | 986 | 570474 |
| 29 | 0.80265620 | 0.49541040 | 0.30724580 | 0.99242364 | 986 | 590156 |
| 30 | 0.81179392 | 0.51516281 | 0.29663111 | 0.99245151 | 986 | 609850 |
| 31 | 0.82096474 | 0.52946323 | 0.29150151 | 0.99248362 | 986 | 629532 |
| 32 | 0.83055114 | 0.54731549 | 0.28323565 | 0.99250979 | 986 | 649210 |
| 33 | 0.83933302 | 0.56137744 | 0.27795558 | 0.99253854 | 986 | 668860 |
| 34 | 0.84780761 | 0.57733394 | 0.27047367 | 0.99257291 | 986 | 688512 |
| 35 | 0.85695605 | 0.59035227 | 0.26660378 | 0.99259968 | 986 | 708152 |
| 36 | 0.86566820 | 0.61248437 | 0.25318383 | 0.99261169 | 986 | 727822 |
| 37 | 0.87360507 | 0.62898872 | 0.24461635 | 0.99263451 | 986 | 747508 |
| 38 | 0.88133980 | 0.64241711 | 0.23892269 | 0.99265594 | 986 | 767196 |
| 39 | 0.88883596 | 0.66067184 | 0.22816413 | 0.99267847 | 986 | 786874 |
| 40 | 0.89644832 | 0.67825243 | 0.21819589 | 0.99269982 | 986 | 806562 |
| 41 | 0.90405835 | 0.69290770 | 0.21115064 | 0.99271799 | 986 | 826250 |
| 42 | 0.91153562 | 0.71209082 | 0.19944480 | 0.99273814 | 986 | 845934 |
| 43 | 0.91901507 | 0.72986822 | 0.18914686 | 0.99275378 | 986 | 865612 |
| 44 | 0.92639894 | 0.74521571 | 0.18118323 | 0.99276530 | 986 | 885302 |
| 45 | 0.93345272 | 0.76035627 | 0.17309645 | 0.99278048 | 986 | 904986 |
| 46 | 0.93998220 | 0.77675023 | 0.16323197 | 0.99279669 | 986 | 924672 |
| 47 | 0.94614402 | 0.79421223 | 0.15193179 | 0.99280934 | 986 | 944368 |
| 48 | 0.95189458 | 0.80884512 | 0.14304946 | 0.99282204 | 986 | 964054 |
| 49 | 0.95716976 | 0.82776402 | 0.12940574 | 0.99282790 | 986 | 983714 |
| 50 | 0.96215113 | 0.84477691 | 0.11737422 | 0.99283539 | 986 | 1003390 |
| 51 | 0.96686342 | 0.86060961 | 0.10625381 | 0.99284811 | 986 | 1023074 |
| 52 | 0.97140187 | 0.87756277 | 0.09383910 | 0.99286145 | 986 | 1042758 |
| 53 | 0.97571115 | 0.89384939 | 0.08186176 | 0.99286818 | 986 | 1062444 |
| 54 | 0.97998529 | 0.90971847 | 0.07026682 | 0.99287688 | 986 | 1082130 |
| 55 | 0.98373628 | 0.92651981 | 0.05721647 | 0.99288945 | 986 | 1101810 |
| 56 | 0.98694469 | 0.94350222 | 0.04344248 | 0.99289889 | 986 | 1121480 |
| 57 | 0.98951449 | 0.95990288 | 0.02961162 | 0.99290838 | 986 | 1141160 |
| 58 | 0.99151884 | 0.97638084 | 0.01513800 | 0.99291394 | 986 | 1160838 |
| 59 | 0.99291893 | 0.99291893 | 0.00000000 | 0.99291893 | 986 | 1180520 |

## §1.6 F-B/G-F2 Routing Input — numbers only, no verdict

Pre-registered F-B metric: minute 50 observed R-squared `0.96215113`; minute 10 observed R-squared `0.58029150` (50-minute lead). Minute 0 observed R-squared `0.31613548`, iid floor `0.01773390`, iid excess `0.29840159`. The minute-50 figure is largely a partial-observation artifact because 50/60 of the averaging window has already been seen; at the 50-minute lead, minute 10 observed R-squared is `0.58029150`. Versus the iid floor, minute-0 observed R-squared `0.31613548` exceeds minute-0 iid floor `0.01773390` by iid excess `0.29840159`.

| minute | observed_r2 | iid_floor | iid_excess | shuffle_r2 |
|---:|---:|---:|---:|---:|
| 0 | 0.31613548 | 0.01773390 | 0.29840159 | 0.96665129 |
| 10 | 0.58029150 | 0.18231963 | 0.39797187 | 0.99081650 |
| 30 | 0.81179392 | 0.51516281 | 0.29663111 | 0.99245151 |
| 50 | 0.96215113 | 0.84477691 | 0.11737422 | 0.99283539 |
| 59 | 0.99291893 | 0.99291893 | 0.00000000 | 0.99291893 |
