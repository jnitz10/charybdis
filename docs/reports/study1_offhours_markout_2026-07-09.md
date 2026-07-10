# Study 1: off-hours markout measurements

Run date: 2026-07-10. Data window: 2026-03-11 through 2026-06-08. Results below are measurements and interval-comparison statuses only.

## Method and run census

The L2 run processed n=694 market-days and wrote n=2204391 simulated fills. Each market-day was processed independently with projected columns. The requested user-scoped systemd manager was unreachable in the execution container; the run used a hard 6 GiB virtual-address-space limit (`prlimit --as=6442450944`).

Feed sanitation census: n=222 non-monotonic market-day books were stable-sorted; n=2069658 pre-first-snapshot events and n=7284 rotated snapshot rows were excluded; n=625 orphan deep-level SUB events were dropped; n=1 oversize SUB events were clamped to level removal; n=2620 crossed reconstructed L1 rows were invalidated to missing state. These are observed row counts, not sampled estimates.

Census definitions: spread is `(ask-bid)/mid` in bps; depth is combined displayed bid-plus-ask touch size in base units; uptime is the two-sided-valid fraction of reconstructed L1 update rows. These are L1-update-row-weighted observations. Staleness is the fraction of simulated fills whose 30s markout was excluded by the 60s quote-age rule. Intervals resample whole market × UTC six-hour clusters with 2,000 draws; `G<5` has an undefined interval and is labeled insufficient evidence.

| Market | Segment | Spread bps | Touch depth units | Two-sided uptime | 30s staleness |
|---|---|---:|---:|---:|---:|
| xyz:SP500 | RTH | 0.360 (n=2321269, G=112; 95% CI [0.300, 0.440]) | 21.245 (n=2321269, G=112; 95% CI [18.623, 23.861]) | 100.000% (n=2321269, G=112; 95% CI [100.000, 100.000]%) | 0.006% (n=245285, G=112; 95% CI [0.003, 0.009]%) |
| xyz:SP500 | off-hours-weekday | 0.263 (n=6007238, G=244; 95% CI [0.242, 0.287]) | 18.950 (n=6007238, G=244; 95% CI [16.972, 20.921]) | 100.000% (n=6007238, G=244; 95% CI [100.000, 100.000]%) | 0.006% (n=270882, G=243; 95% CI [0.003, 0.011]%) |
| xyz:SP500 | weekend | 0.474 (n=2736774, G=108; 95% CI [0.428, 0.527]) | 8.500 (n=2736774, G=108; 95% CI [6.263, 11.491]) | 100.000% (n=2736775, G=108; 95% CI [100.000, 100.000]%) | 0.011% (n=100701, G=108; 95% CI [0.004, 0.021]%) |
| km:US500 | RTH | 0.359 (n=2420231, G=122; 95% CI [0.321, 0.397]) | 114.144 (n=2420231, G=122; 95% CI [103.433, 126.932]) | 100.000% (n=2420231, G=122; 95% CI [100.000, 100.000]%) | 0.016% (n=99938, G=122; 95% CI [0.008, 0.025]%) |
| km:US500 | off-hours-weekday | 0.284 (n=5500650, G=264; 95% CI [0.259, 0.311]) | 85.293 (n=5500650, G=264; 95% CI [79.080, 92.070]) | 100.000% (n=5500651, G=264; 95% CI [100.000, 100.000]%) | 0.027% (n=80864, G=264; 95% CI [0.014, 0.043]%) |
| km:US500 | weekend | 0.585 (n=2278068, G=117; 95% CI [0.502, 0.691]) | 41.433 (n=2278068, G=117; 95% CI [36.206, 47.393]) | 100.000% (n=2278071, G=117; 95% CI [100.000, 100.000]%) | 0.036% (n=25113, G=116; 95% CI [0.007, 0.078]%) |
| flx:USA500 | RTH | 4.293 (n=1273740, G=122; 95% CI [3.807, 4.864]) | 14.786 (n=1273740, G=122; 95% CI [13.092, 16.529]) | 100.000% (n=1273740, G=122; 95% CI [100.000, 100.000]%) | 0.064% (n=1574, G=91; 95% CI [0.000, 0.215]%) |
| flx:USA500 | off-hours-weekday | 5.204 (n=2546023, G=265; 95% CI [4.546, 5.934]) | 11.997 (n=2546023, G=265; 95% CI [10.748, 13.227]) | 99.999% (n=2546055, G=265; 95% CI [99.998, 99.999]%) | 0.351% (n=1708, G=186; 95% CI [0.066, 0.723]%) |
| flx:USA500 | weekend | 35.396 (n=527169, G=117; 95% CI [27.825, 44.714]) | 7.345 (n=527169, G=117; 95% CI [5.236, 9.408]) | 99.976% (n=527295, G=117; 95% CI [99.942, 99.996]%) | 1.032% (n=775, G=75; 95% CI [0.221, 2.315]%) |
| cash:USA500 | RTH | 0.253 (n=2343777, G=122; 95% CI [0.237, 0.271]) | 10.910 (n=2343777, G=122; 95% CI [9.054, 12.794]) | 100.000% (n=2343777, G=122; 95% CI [100.000, 100.000]%) | 0.008% (n=239536, G=122; 95% CI [0.004, 0.012]%) |
| cash:USA500 | off-hours-weekday | 0.200 (n=5056641, G=264; 95% CI [0.188, 0.216]) | 12.943 (n=5056641, G=264; 95% CI [11.272, 14.527]) | 100.000% (n=5056645, G=264; 95% CI [100.000, 100.000]%) | 0.009% (n=232118, G=264; 95% CI [0.004, 0.014]%) |
| cash:USA500 | weekend | 0.450 (n=1629155, G=117; 95% CI [0.344, 0.573]) | 6.390 (n=1629155, G=117; 95% CI [4.771, 8.181]) | 99.997% (n=1629199, G=117; 95% CI [99.995, 99.999]%) | 0.045% (n=42395, G=117; 95% CI [0.018, 0.080]%) |
| km:USTECH | RTH | 1.087 (n=2405481, G=122; 95% CI [0.986, 1.201]) | 119.735 (n=2405481, G=122; 95% CI [108.589, 133.010]) | 100.000% (n=2405481, G=122; 95% CI [100.000, 100.000]%) | 0.045% (n=39825, G=122; 95% CI [0.019, 0.078]%) |
| km:USTECH | off-hours-weekday | 1.005 (n=5101780, G=265; 95% CI [0.927, 1.090]) | 117.185 (n=5101780, G=265; 95% CI [106.608, 128.574]) | 100.000% (n=5101803, G=265; 95% CI [99.999, 100.000]%) | 0.074% (n=27093, G=263; 95% CI [0.034, 0.127]%) |
| km:USTECH | weekend | 2.121 (n=1273504, G=117; 95% CI [1.744, 2.520]) | 63.111 (n=1273504, G=117; 95% CI [49.661, 78.852]) | 99.998% (n=1273535, G=117; 95% CI [99.995, 99.999]%) | 0.260% (n=4992, G=114; 95% CI [0.063, 0.560]%) |
| xyz:XYZ100 | RTH | 0.478 (n=2572818, G=122; 95% CI [0.458, 0.497]) | 7.383 (n=2572818, G=122; 95% CI [6.749, 8.013]) | 100.000% (n=2572818, G=122; 95% CI [100.000, 100.000]%) | 0.005% (n=336231, G=122; 95% CI [0.003, 0.007]%) |
| xyz:XYZ100 | off-hours-weekday | 0.411 (n=7010381, G=264; 95% CI [0.403, 0.418]) | 5.668 (n=7010381, G=264; 95% CI [5.204, 6.147]) | 100.000% (n=7010381, G=264; 95% CI [100.000, 100.000]%) | 0.008% (n=326797, G=264; 95% CI [0.005, 0.012]%) |
| xyz:XYZ100 | weekend | 0.450 (n=3502507, G=117; 95% CI [0.431, 0.472]) | 3.016 (n=3502507, G=117; 95% CI [2.449, 3.679]) | 100.000% (n=3502507, G=117; 95% CI [100.000, 100.000]%) | 0.005% (n=105843, G=117; 95% CI [0.001, 0.010]%) |
| flx:USA100 | RTH | 6.087 (n=1284180, G=96; 95% CI [4.826, 7.717]) | 16.875 (n=1284180, G=96; 95% CI [16.201, 17.456]) | 99.999% (n=1284198, G=96; 95% CI [99.996, 100.000]%) | 0.000% (n=345, G=35; 95% CI [0.000, 0.000]%) |
| flx:USA100 | off-hours-weekday | 12.107 (n=2242757, G=210; 95% CI [9.738, 14.972]) | 15.859 (n=2242757, G=210; 95% CI [15.250, 16.406]) | 99.999% (n=2242770, G=210; 95% CI [99.999, 100.000]%) | 1.961% (n=357, G=66; 95% CI [0.679, 3.943]%) |
| flx:USA100 | weekend | 134.117 (n=304217, G=89; 95% CI [100.008, 177.472]) | 8.237 (n=304217, G=89; 95% CI [5.461, 10.514]) | 99.274% (n=306443, G=89; 95% CI [97.620, 100.000]%) | 17.500% (n=120, G=37; 95% CI [7.936, 27.200]%) |
| km:SMALL2000 | RTH | 3.908 (n=1977095, G=122; 95% CI [3.545, 4.307]) | 923.355 (n=1977095, G=122; 95% CI [848.676, 1005.557]) | 100.000% (n=1977095, G=122; 95% CI [100.000, 100.000]%) | 0.102% (n=10826, G=122; 95% CI [0.025, 0.204]%) |
| km:SMALL2000 | off-hours-weekday | 4.203 (n=2937379, G=265; 95% CI [3.815, 4.650]) | 662.686 (n=2937379, G=265; 95% CI [612.463, 713.977]) | 99.997% (n=2937479, G=265; 95% CI [99.994, 99.999]%) | 0.187% (n=9646, G=253; 95% CI [0.095, 0.310]%) |
| km:SMALL2000 | weekend | 7.939 (n=531588, G=117; 95% CI [6.110, 10.083]) | 317.199 (n=531588, G=117; 95% CI [262.461, 381.623]) | 99.996% (n=531607, G=117; 95% CI [99.992, 100.000]%) | 1.682% (n=1427, G=100; 95% CI [0.931, 2.719]%) |

## Net markouts by horizon

Every cell is pooled net bps with n, cluster count G, and a cluster-bootstrap 95% CI. Null markouts, including stale observations, are excluded.

| Market | Segment | 1s | 5s | 30s | 2m | 10m |
|---|---|---:|---:|---:|---:|---:|
| xyz:SP500 | RTH | -1.770 (n=245272, G=112; 95% CI [-1.790, -1.751]) | -1.953 (n=245272, G=112; 95% CI [-1.975, -1.931]) | -2.004 (n=245271, G=112; 95% CI [-2.033, -1.974]) | -2.041 (n=245004, G=112; 95% CI [-2.087, -1.997]) | -2.019 (n=243969, G=112; 95% CI [-2.102, -1.943]) |
| xyz:SP500 | off-hours-weekday | -1.729 (n=270867, G=243; 95% CI [-1.744, -1.714]) | -1.903 (n=270868, G=243; 95% CI [-1.925, -1.880]) | -1.987 (n=270866, G=243; 95% CI [-2.021, -1.957]) | -2.039 (n=270386, G=243; 95% CI [-2.094, -1.990]) | -2.039 (n=267952, G=242; 95% CI [-2.113, -1.968]) |
| xyz:SP500 | weekend | -1.571 (n=100690, G=108; 95% CI [-1.606, -1.533]) | -1.705 (n=100690, G=108; 95% CI [-1.746, -1.659]) | -1.858 (n=100690, G=108; 95% CI [-1.913, -1.797]) | -2.002 (n=100468, G=108; 95% CI [-2.093, -1.915]) | -2.152 (n=99278, G=108; 95% CI [-2.387, -1.934]) |
| km:US500 | RTH | -1.939 (n=99922, G=122; 95% CI [-1.971, -1.908]) | -2.282 (n=99922, G=122; 95% CI [-2.315, -2.247]) | -2.442 (n=99922, G=122; 95% CI [-2.490, -2.391]) | -2.509 (n=99779, G=122; 95% CI [-2.583, -2.435]) | -2.566 (n=99252, G=122; 95% CI [-2.687, -2.458]) |
| km:US500 | off-hours-weekday | -1.868 (n=80845, G=264; 95% CI [-1.889, -1.848]) | -2.216 (n=80845, G=264; 95% CI [-2.270, -2.166]) | -2.432 (n=80842, G=264; 95% CI [-2.516, -2.363]) | -2.626 (n=80676, G=264; 95% CI [-2.751, -2.515]) | -2.823 (n=79875, G=263; 95% CI [-3.094, -2.623]) |
| km:US500 | weekend | -1.593 (n=25104, G=116; 95% CI [-1.675, -1.504]) | -1.772 (n=25104, G=116; 95% CI [-1.885, -1.656]) | -2.098 (n=25104, G=116; 95% CI [-2.294, -1.905]) | -2.530 (n=25046, G=116; 95% CI [-2.832, -2.243]) | -3.163 (n=24701, G=116; 95% CI [-3.706, -2.693]) |
| flx:USA500 | RTH | -1.400 (n=1573, G=91; 95% CI [-1.985, -0.760]) | -2.334 (n=1573, G=91; 95% CI [-3.013, -1.701]) | -2.626 (n=1573, G=91; 95% CI [-3.584, -1.632]) | -3.108 (n=1572, G=90; 95% CI [-4.581, -1.469]) | -4.154 (n=1570, G=90; 95% CI [-5.810, -2.690]) |
| flx:USA500 | off-hours-weekday | -0.324 (n=1702, G=186; 95% CI [-0.988, 0.387]) | -1.182 (n=1702, G=186; 95% CI [-1.933, -0.461]) | -0.805 (n=1702, G=186; 95% CI [-1.659, 0.021]) | -0.896 (n=1696, G=186; 95% CI [-1.887, -0.056]) | -1.815 (n=1684, G=185; 95% CI [-3.130, -0.776]) |
| flx:USA500 | weekend | 8.552 (n=767, G=75; 95% CI [4.307, 15.146]) | 5.991 (n=767, G=75; 95% CI [2.202, 11.607]) | 2.665 (n=767, G=75; 95% CI [-2.428, 8.479]) | -0.629 (n=739, G=73; 95% CI [-7.120, 6.195]) | -3.235 (n=718, G=70; 95% CI [-8.760, 2.567]) |
| cash:USA500 | RTH | -1.864 (n=239519, G=122; 95% CI [-1.888, -1.840]) | -2.176 (n=239519, G=122; 95% CI [-2.201, -2.149]) | -2.245 (n=239518, G=122; 95% CI [-2.284, -2.207]) | -2.253 (n=239178, G=122; 95% CI [-2.316, -2.195]) | -2.222 (n=237786, G=122; 95% CI [-2.311, -2.145]) |
| cash:USA500 | off-hours-weekday | -1.818 (n=232099, G=264; 95% CI [-1.832, -1.804]) | -2.080 (n=232098, G=264; 95% CI [-2.114, -2.048]) | -2.180 (n=232098, G=264; 95% CI [-2.222, -2.145]) | -2.241 (n=231600, G=264; 95% CI [-2.311, -2.182]) | -2.220 (n=229395, G=262; 95% CI [-2.325, -2.140]) |
| cash:USA500 | weekend | -1.700 (n=42376, G=117; 95% CI [-1.737, -1.653]) | -2.024 (n=42376, G=117; 95% CI [-2.085, -1.953]) | -2.240 (n=42376, G=117; 95% CI [-2.363, -2.124]) | -2.464 (n=42129, G=117; 95% CI [-2.699, -2.272]) | -2.919 (n=41029, G=117; 95% CI [-3.353, -2.551]) |
| km:USTECH | RTH | -2.140 (n=39810, G=122; 95% CI [-2.197, -2.084]) | -2.484 (n=39810, G=122; 95% CI [-2.559, -2.410]) | -2.630 (n=39807, G=122; 95% CI [-2.714, -2.546]) | -2.745 (n=39740, G=122; 95% CI [-2.870, -2.625]) | -2.751 (n=39615, G=122; 95% CI [-3.046, -2.473]) |
| km:USTECH | off-hours-weekday | -1.988 (n=27080, G=263; 95% CI [-2.042, -1.929]) | -2.394 (n=27080, G=263; 95% CI [-2.462, -2.328]) | -2.615 (n=27073, G=263; 95% CI [-2.747, -2.495]) | -2.826 (n=27017, G=263; 95% CI [-3.043, -2.647]) | -2.937 (n=26803, G=261; 95% CI [-3.364, -2.600]) |
| km:USTECH | weekend | -1.448 (n=4981, G=114; 95% CI [-1.859, -0.844]) | -2.207 (n=4981, G=114; 95% CI [-2.458, -1.928]) | -3.033 (n=4979, G=114; 95% CI [-3.490, -2.471]) | -3.722 (n=4956, G=114; 95% CI [-4.092, -3.378]) | -4.145 (n=4857, G=114; 95% CI [-4.728, -3.623]) |
| xyz:XYZ100 | RTH | -1.919 (n=336215, G=122; 95% CI [-1.940, -1.896]) | -2.162 (n=336215, G=122; 95% CI [-2.184, -2.139]) | -2.178 (n=336215, G=122; 95% CI [-2.208, -2.147]) | -2.202 (n=335758, G=122; 95% CI [-2.249, -2.150]) | -2.239 (n=333988, G=122; 95% CI [-2.311, -2.167]) |
| xyz:XYZ100 | off-hours-weekday | -1.843 (n=326769, G=264; 95% CI [-1.856, -1.830]) | -2.050 (n=326769, G=264; 95% CI [-2.073, -2.028]) | -2.117 (n=326770, G=264; 95% CI [-2.164, -2.080]) | -2.183 (n=326081, G=264; 95% CI [-2.266, -2.117]) | -2.192 (n=322862, G=263; 95% CI [-2.287, -2.108]) |
| xyz:XYZ100 | weekend | -1.726 (n=105838, G=117; 95% CI [-1.768, -1.679]) | -1.938 (n=105838, G=117; 95% CI [-2.014, -1.862]) | -2.154 (n=105838, G=117; 95% CI [-2.280, -2.041]) | -2.311 (n=105544, G=117; 95% CI [-2.486, -2.161]) | -2.443 (n=104186, G=117; 95% CI [-2.657, -2.261]) |
| flx:USA100 | RTH | -1.081 (n=345, G=35; 95% CI [-3.871, 1.521]) | -3.356 (n=345, G=35; 95% CI [-7.256, -0.417]) | -3.921 (n=345, G=35; 95% CI [-8.899, -0.898]) | -4.751 (n=344, G=35; 95% CI [-9.611, -1.137]) | -3.091 (n=338, G=35; 95% CI [-8.234, 2.476]) |
| flx:USA100 | off-hours-weekday | 7.451 (n=350, G=64; 95% CI [-1.007, 16.954]) | -0.573 (n=350, G=64; 95% CI [-9.562, 7.981]) | -3.357 (n=350, G=64; 95% CI [-15.750, 8.337]) | -10.876 (n=339, G=62; 95% CI [-26.155, 3.713]) | -9.039 (n=331, G=61; 95% CI [-22.310, 2.331]) |
| flx:USA100 | weekend | 16.656 (n=99, G=33; 95% CI [3.696, 34.443]) | -7.374 (n=99, G=33; 95% CI [-27.488, 13.551]) | -12.071 (n=99, G=33; 95% CI [-41.441, 16.635]) | -9.333 (n=64, G=22; 95% CI [-38.638, 15.485]) | -6.512 (n=63, G=24; 95% CI [-43.985, 27.785]) |
| km:SMALL2000 | RTH | -1.961 (n=10815, G=122; 95% CI [-2.142, -1.768]) | -3.357 (n=10814, G=122; 95% CI [-3.593, -3.149]) | -2.972 (n=10815, G=122; 95% CI [-3.146, -2.785]) | -3.106 (n=10790, G=122; 95% CI [-3.420, -2.840]) | -3.212 (n=10737, G=122; 95% CI [-3.651, -2.805]) |
| km:SMALL2000 | off-hours-weekday | -1.724 (n=9634, G=252; 95% CI [-2.591, -0.667]) | -2.992 (n=9631, G=252; 95% CI [-4.259, -1.609]) | -3.236 (n=9628, G=252; 95% CI [-4.588, -1.929]) | -3.182 (n=9598, G=252; 95% CI [-5.034, -1.190]) | -1.378 (n=9454, G=249; 95% CI [-4.734, 2.926]) |
| km:SMALL2000 | weekend | -0.260 (n=1404, G=98; 95% CI [-4.513, 4.705]) | -1.130 (n=1404, G=98; 95% CI [-4.639, 3.339]) | -1.303 (n=1403, G=98; 95% CI [-4.479, 2.814]) | -2.091 (n=1383, G=95; 95% CI [-5.386, 2.144]) | -2.901 (n=1336, G=95; 95% CI [-6.541, 2.278]) |

## Primary 30s CI-separation status

The numeric comparison is `off-hours lower CI > RTH upper CI`. Undefined intervals are insufficient evidence and are never counted as separation.

| Market | Comparison | RTH net bps | Other-segment net bps | CI-separation status |
|---|---|---:|---:|---|
| xyz:SP500 | off-hours-weekday vs RTH | -2.004 (n=245271, G=112; 95% CI [-2.033, -1.974]) | -1.987 (n=270866, G=243; 95% CI [-2.021, -1.957]) | no |
| xyz:SP500 | weekend vs RTH | -2.004 (n=245271, G=112; 95% CI [-2.033, -1.974]) | -1.858 (n=100690, G=108; 95% CI [-1.913, -1.797]) | yes |
| km:US500 | off-hours-weekday vs RTH | -2.442 (n=99922, G=122; 95% CI [-2.490, -2.391]) | -2.432 (n=80842, G=264; 95% CI [-2.516, -2.363]) | no |
| km:US500 | weekend vs RTH | -2.442 (n=99922, G=122; 95% CI [-2.490, -2.391]) | -2.098 (n=25104, G=116; 95% CI [-2.294, -1.905]) | yes |
| flx:USA500 | off-hours-weekday vs RTH | -2.626 (n=1573, G=91; 95% CI [-3.584, -1.632]) | -0.805 (n=1702, G=186; 95% CI [-1.659, 0.021]) | no |
| flx:USA500 | weekend vs RTH | -2.626 (n=1573, G=91; 95% CI [-3.584, -1.632]) | 2.665 (n=767, G=75; 95% CI [-2.428, 8.479]) | no |
| cash:USA500 | off-hours-weekday vs RTH | -2.245 (n=239518, G=122; 95% CI [-2.284, -2.207]) | -2.180 (n=232098, G=264; 95% CI [-2.222, -2.145]) | no |
| cash:USA500 | weekend vs RTH | -2.245 (n=239518, G=122; 95% CI [-2.284, -2.207]) | -2.240 (n=42376, G=117; 95% CI [-2.363, -2.124]) | no |
| km:USTECH | off-hours-weekday vs RTH | -2.630 (n=39807, G=122; 95% CI [-2.714, -2.546]) | -2.615 (n=27073, G=263; 95% CI [-2.747, -2.495]) | no |
| km:USTECH | weekend vs RTH | -2.630 (n=39807, G=122; 95% CI [-2.714, -2.546]) | -3.033 (n=4979, G=114; 95% CI [-3.490, -2.471]) | no |
| xyz:XYZ100 | off-hours-weekday vs RTH | -2.178 (n=336215, G=122; 95% CI [-2.208, -2.147]) | -2.117 (n=326770, G=264; 95% CI [-2.164, -2.080]) | no |
| xyz:XYZ100 | weekend vs RTH | -2.178 (n=336215, G=122; 95% CI [-2.208, -2.147]) | -2.154 (n=105838, G=117; 95% CI [-2.280, -2.041]) | no |
| flx:USA100 | off-hours-weekday vs RTH | -3.921 (n=345, G=35; 95% CI [-8.899, -0.898]) | -3.357 (n=350, G=64; 95% CI [-15.750, 8.337]) | no |
| flx:USA100 | weekend vs RTH | -3.921 (n=345, G=35; 95% CI [-8.899, -0.898]) | -12.071 (n=99, G=33; 95% CI [-41.441, 16.635]) | no |
| km:SMALL2000 | off-hours-weekday vs RTH | -2.972 (n=10815, G=122; 95% CI [-3.146, -2.785]) | -3.236 (n=9628, G=252; 95% CI [-4.588, -1.929]) | no |
| km:SMALL2000 | weekend vs RTH | -2.972 (n=10815, G=122; 95% CI [-3.146, -2.785]) | -1.303 (n=1403, G=98; 95% CI [-4.479, 2.814]) | no |

## Secondary: side

| market | segment | side | 30s net bps |
|---|---|---|---|
| cash:USA500 | RTH | buy | -2.256 (n=120848, G=122; 95% CI [-2.306, -2.205]) |
| cash:USA500 | RTH | sell | -2.235 (n=118670, G=122; 95% CI [-2.292, -2.180]) |
| cash:USA500 | off-hours-weekday | buy | -2.170 (n=116409, G=264; 95% CI [-2.215, -2.126]) |
| cash:USA500 | off-hours-weekday | sell | -2.189 (n=115689, G=264; 95% CI [-2.285, -2.118]) |
| cash:USA500 | weekend | buy | -2.193 (n=21188, G=117; 95% CI [-2.317, -2.073]) |
| cash:USA500 | weekend | sell | -2.287 (n=21188, G=117; 95% CI [-2.452, -2.122]) |
| flx:USA100 | RTH | buy | -4.313 (n=179, G=24; 95% CI [-12.807, 2.006]) |
| flx:USA100 | RTH | sell | -3.497 (n=166, G=26; 95% CI [-6.398, -2.105]) |
| flx:USA100 | off-hours-weekday | buy | -4.069 (n=219, G=53; 95% CI [-20.131, 8.678]) |
| flx:USA100 | off-hours-weekday | sell | -2.168 (n=131, G=41; 95% CI [-16.152, 11.717]) |
| flx:USA100 | weekend | buy | -4.473 (n=51, G=23; 95% CI [-41.193, 35.697]) |
| flx:USA100 | weekend | sell | -20.144 (n=48, G=22; 95% CI [-53.740, 12.242]) |
| flx:USA500 | RTH | buy | -2.022 (n=877, G=78; 95% CI [-2.942, -0.967]) |
| flx:USA500 | RTH | sell | -3.388 (n=696, G=79; 95% CI [-5.019, -2.237]) |
| flx:USA500 | off-hours-weekday | buy | -0.155 (n=988, G=139; 95% CI [-1.382, 1.273]) |
| flx:USA500 | off-hours-weekday | sell | -1.704 (n=714, G=152; 95% CI [-2.843, -0.902]) |
| flx:USA500 | weekend | buy | 1.563 (n=398, G=61; 95% CI [-6.732, 9.310]) |
| flx:USA500 | weekend | sell | 3.854 (n=369, G=56; 95% CI [-2.078, 12.540]) |
| km:SMALL2000 | RTH | buy | -2.910 (n=5417, G=120; 95% CI [-3.156, -2.671]) |
| km:SMALL2000 | RTH | sell | -3.034 (n=5398, G=120; 95% CI [-3.301, -2.756]) |
| km:SMALL2000 | off-hours-weekday | buy | -3.469 (n=4709, G=244; 95% CI [-4.731, -2.202]) |
| km:SMALL2000 | off-hours-weekday | sell | -3.013 (n=4919, G=238; 95% CI [-4.757, -0.979]) |
| km:SMALL2000 | weekend | buy | -2.838 (n=779, G=83; 95% CI [-7.431, 1.059]) |
| km:SMALL2000 | weekend | sell | 0.613 (n=624, G=83; 95% CI [-7.558, 13.686]) |
| km:US500 | RTH | buy | -2.446 (n=49468, G=122; 95% CI [-2.503, -2.391]) |
| km:US500 | RTH | sell | -2.438 (n=50454, G=122; 95% CI [-2.506, -2.367]) |
| km:US500 | off-hours-weekday | buy | -2.364 (n=40239, G=264; 95% CI [-2.425, -2.304]) |
| km:US500 | off-hours-weekday | sell | -2.499 (n=40603, G=263; 95% CI [-2.681, -2.380]) |
| km:US500 | weekend | buy | -2.003 (n=12618, G=115; 95% CI [-2.195, -1.830]) |
| km:US500 | weekend | sell | -2.193 (n=12486, G=112; 95% CI [-2.464, -1.954]) |
| km:USTECH | RTH | buy | -2.676 (n=19394, G=122; 95% CI [-2.781, -2.567]) |
| km:USTECH | RTH | sell | -2.586 (n=20413, G=122; 95% CI [-2.694, -2.480]) |
| km:USTECH | off-hours-weekday | buy | -2.539 (n=13485, G=262; 95% CI [-2.659, -2.421]) |
| km:USTECH | off-hours-weekday | sell | -2.691 (n=13588, G=262; 95% CI [-2.923, -2.509]) |
| km:USTECH | weekend | buy | -3.051 (n=2379, G=111; 95% CI [-3.547, -2.496]) |
| km:USTECH | weekend | sell | -3.017 (n=2600, G=108; 95% CI [-3.548, -2.452]) |
| xyz:SP500 | RTH | buy | -1.975 (n=125051, G=112; 95% CI [-2.023, -1.926]) |
| xyz:SP500 | RTH | sell | -2.033 (n=120220, G=112; 95% CI [-2.082, -1.987]) |
| xyz:SP500 | off-hours-weekday | buy | -1.947 (n=136968, G=243; 95% CI [-1.994, -1.899]) |
| xyz:SP500 | off-hours-weekday | sell | -2.027 (n=133898, G=243; 95% CI [-2.112, -1.959]) |
| xyz:SP500 | weekend | buy | -1.811 (n=51405, G=108; 95% CI [-1.903, -1.707]) |
| xyz:SP500 | weekend | sell | -1.907 (n=49285, G=108; 95% CI [-2.013, -1.811]) |
| xyz:XYZ100 | RTH | buy | -2.173 (n=169777, G=122; 95% CI [-2.232, -2.112]) |
| xyz:XYZ100 | RTH | sell | -2.183 (n=166438, G=122; 95% CI [-2.244, -2.126]) |
| xyz:XYZ100 | off-hours-weekday | buy | -2.086 (n=163804, G=264; 95% CI [-2.140, -2.029]) |
| xyz:XYZ100 | off-hours-weekday | sell | -2.149 (n=162966, G=264; 95% CI [-2.254, -2.068]) |
| xyz:XYZ100 | weekend | buy | -2.127 (n=52974, G=117; 95% CI [-2.266, -2.017]) |
| xyz:XYZ100 | weekend | sell | -2.181 (n=52864, G=117; 95% CI [-2.352, -2.029]) |

## Secondary: UTC hour of day

| market | segment | hour_of_day | 30s net bps |
|---|---|---|---|
| cash:USA500 | RTH | 13 | -2.292 (n=30334, G=60; 95% CI [-2.360, -2.230]) |
| cash:USA500 | RTH | 14 | -2.310 (n=51301, G=61; 95% CI [-2.406, -2.228]) |
| cash:USA500 | RTH | 15 | -2.232 (n=40440, G=61; 95% CI [-2.289, -2.179]) |
| cash:USA500 | RTH | 16 | -2.267 (n=30734, G=59; 95% CI [-2.347, -2.196]) |
| cash:USA500 | RTH | 17 | -2.233 (n=29545, G=61; 95% CI [-2.316, -2.152]) |
| cash:USA500 | RTH | 18 | -2.115 (n=27511, G=60; 95% CI [-2.170, -2.062]) |
| cash:USA500 | RTH | 19 | -2.214 (n=29653, G=61; 95% CI [-2.291, -2.144]) |
| cash:USA500 | off-hours-weekday | 0 | -2.290 (n=10240, G=49; 95% CI [-2.459, -2.164]) |
| cash:USA500 | off-hours-weekday | 1 | -2.181 (n=11525, G=61; 95% CI [-2.260, -2.097]) |
| cash:USA500 | off-hours-weekday | 2 | -2.127 (n=8968, G=63; 95% CI [-2.216, -2.047]) |
| cash:USA500 | off-hours-weekday | 3 | -2.033 (n=6436, G=63; 95% CI [-2.088, -1.977]) |
| cash:USA500 | off-hours-weekday | 4 | -2.053 (n=7233, G=63; 95% CI [-2.114, -1.996]) |
| cash:USA500 | off-hours-weekday | 5 | -2.136 (n=10437, G=63; 95% CI [-2.201, -2.072]) |
| cash:USA500 | off-hours-weekday | 6 | -2.092 (n=13003, G=63; 95% CI [-2.160, -2.027]) |
| cash:USA500 | off-hours-weekday | 7 | -2.135 (n=17101, G=63; 95% CI [-2.179, -2.089]) |
| cash:USA500 | off-hours-weekday | 8 | -2.183 (n=20293, G=62; 95% CI [-2.234, -2.131]) |
| cash:USA500 | off-hours-weekday | 9 | -2.124 (n=17864, G=63; 95% CI [-2.169, -2.078]) |
| cash:USA500 | off-hours-weekday | 10 | -2.180 (n=17586, G=63; 95% CI [-2.292, -2.083]) |
| cash:USA500 | off-hours-weekday | 11 | -2.312 (n=18914, G=62; 95% CI [-2.623, -2.142]) |
| cash:USA500 | off-hours-weekday | 12 | -2.209 (n=25139, G=62; 95% CI [-2.265, -2.155]) |
| cash:USA500 | off-hours-weekday | 13 | -2.118 (n=12534, G=61; 95% CI [-2.199, -2.045]) |
| cash:USA500 | off-hours-weekday | 14 | -1.890 (n=51, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 15 | -2.010 (n=51, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 16 | -1.616 (n=22, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 17 | -1.266 (n=25, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 18 | -1.988 (n=24, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 19 | -2.713 (n=56, G=2; 95% CI undefined—insufficient evidence) |
| cash:USA500 | off-hours-weekday | 20 | -2.344 (n=14561, G=63; 95% CI [-2.511, -2.159]) |
| cash:USA500 | off-hours-weekday | 21 | -2.002 (n=3148, G=62; 95% CI [-2.112, -1.908]) |
| cash:USA500 | off-hours-weekday | 22 | -2.225 (n=9682, G=63; 95% CI [-2.326, -2.118]) |
| cash:USA500 | off-hours-weekday | 23 | -2.141 (n=7205, G=63; 95% CI [-2.280, -1.968]) |
| cash:USA500 | weekend | 0 | -2.365 (n=4062, G=19; 95% CI [-2.607, -2.135]) |
| cash:USA500 | weekend | 1 | -2.376 (n=3147, G=25; 95% CI [-2.649, -2.107]) |
| cash:USA500 | weekend | 2 | -1.999 (n=3310, G=26; 95% CI [-2.110, -1.837]) |
| cash:USA500 | weekend | 3 | -1.974 (n=2504, G=26; 95% CI [-2.121, -1.852]) |
| cash:USA500 | weekend | 4 | -1.840 (n=638, G=26; 95% CI [-2.138, -1.505]) |
| cash:USA500 | weekend | 5 | -1.931 (n=600, G=25; 95% CI [-2.143, -1.792]) |
| cash:USA500 | weekend | 6 | -2.095 (n=810, G=25; 95% CI [-2.306, -1.906]) |
| cash:USA500 | weekend | 7 | -2.271 (n=1140, G=25; 95% CI [-4.046, -1.676]) |
| cash:USA500 | weekend | 8 | -2.016 (n=620, G=26; 95% CI [-2.373, -1.749]) |
| cash:USA500 | weekend | 9 | -1.801 (n=1004, G=26; 95% CI [-2.260, -1.415]) |
| cash:USA500 | weekend | 10 | -1.939 (n=798, G=26; 95% CI [-2.229, -1.714]) |
| cash:USA500 | weekend | 11 | -1.957 (n=660, G=26; 95% CI [-2.143, -1.747]) |
| cash:USA500 | weekend | 12 | -2.033 (n=1010, G=24; 95% CI [-2.507, -1.755]) |
| cash:USA500 | weekend | 13 | -1.961 (n=909, G=26; 95% CI [-2.182, -1.650]) |
| cash:USA500 | weekend | 14 | -2.023 (n=900, G=26; 95% CI [-2.397, -1.748]) |
| cash:USA500 | weekend | 15 | -2.377 (n=986, G=26; 95% CI [-2.621, -2.133]) |
| cash:USA500 | weekend | 16 | -2.042 (n=1392, G=26; 95% CI [-2.400, -1.828]) |
| cash:USA500 | weekend | 17 | -2.353 (n=1254, G=26; 95% CI [-2.616, -1.999]) |
| cash:USA500 | weekend | 18 | -3.321 (n=1124, G=25; 95% CI [-4.631, -2.072]) |
| cash:USA500 | weekend | 19 | -1.956 (n=1682, G=26; 95% CI [-2.457, -1.778]) |
| cash:USA500 | weekend | 20 | -2.294 (n=1856, G=24; 95% CI [-3.022, -1.868]) |
| cash:USA500 | weekend | 21 | -2.447 (n=1416, G=25; 95% CI [-2.803, -2.084]) |
| cash:USA500 | weekend | 22 | -2.466 (n=6556, G=25; 95% CI [-2.606, -2.292]) |
| cash:USA500 | weekend | 23 | -2.262 (n=3998, G=25; 95% CI [-2.455, -2.083]) |
| flx:USA100 | RTH | 13 | -4.049 (n=40, G=11; 95% CI [-9.321, -1.279]) |
| flx:USA100 | RTH | 14 | -7.898 (n=104, G=14; 95% CI [-35.409, 1.262]) |
| flx:USA100 | RTH | 15 | -1.584 (n=71, G=11; 95% CI [-4.860, 0.280]) |
| flx:USA100 | RTH | 16 | -2.546 (n=63, G=9; 95% CI [-6.404, 0.573]) |
| flx:USA100 | RTH | 17 | 0.934 (n=11, G=7; 95% CI [-10.170, 19.925]) |
| flx:USA100 | RTH | 18 | -0.600 (n=28, G=7; 95% CI [-5.124, 1.723]) |
| flx:USA100 | RTH | 19 | -3.207 (n=28, G=9; 95% CI [-9.094, 1.402]) |
| flx:USA100 | off-hours-weekday | 0 | -1.533 (n=14, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 1 | 8.289 (n=25, G=7; 95% CI [-7.866, 15.564]) |
| flx:USA100 | off-hours-weekday | 2 | -21.757 (n=14, G=8; 95% CI [-47.405, -6.554]) |
| flx:USA100 | off-hours-weekday | 3 | 14.434 (n=10, G=6; 95% CI [-6.519, 49.337]) |
| flx:USA100 | off-hours-weekday | 4 | -1.397 (n=8, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 5 | -3.994 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 6 | -0.578 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 7 | 4.353 (n=8, G=5; 95% CI [-8.021, 16.790]) |
| flx:USA100 | off-hours-weekday | 8 | -15.792 (n=10, G=7; 95% CI [-55.511, 17.692]) |
| flx:USA100 | off-hours-weekday | 9 | -2.834 (n=10, G=6; 95% CI [-7.516, -0.711]) |
| flx:USA100 | off-hours-weekday | 10 | -20.919 (n=23, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 11 | -11.188 (n=30, G=11; 95% CI [-24.810, -2.698]) |
| flx:USA100 | off-hours-weekday | 12 | -1.642 (n=36, G=10; 95% CI [-9.335, 14.305]) |
| flx:USA100 | off-hours-weekday | 13 | -2.174 (n=11, G=7; 95% CI [-4.955, 0.197]) |
| flx:USA100 | off-hours-weekday | 16 | 182.210 (n=2, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | off-hours-weekday | 20 | -11.919 (n=24, G=6; 95% CI [-51.003, 2.397]) |
| flx:USA100 | off-hours-weekday | 21 | -32.005 (n=30, G=9; 95% CI [-68.839, 81.516]) |
| flx:USA100 | off-hours-weekday | 22 | 9.828 (n=70, G=10; 95% CI [-45.233, 63.891]) |
| flx:USA100 | off-hours-weekday | 23 | 3.086 (n=21, G=7; 95% CI [-9.642, 10.592]) |
| flx:USA100 | weekend | 0 | 1.493 (n=2, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 1 | -0.633 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 3 | -0.244 (n=2, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 4 | 81.877 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 5 | 89.094 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 6 | 77.882 (n=2, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 8 | insufficient evidence (n=0, G=0; 95% CI undefined) |
| flx:USA100 | weekend | 9 | 64.673 (n=9, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 10 | 136.372 (n=1, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 11 | -18.276 (n=6, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 12 | -0.426 (n=1, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 13 | -128.670 (n=7, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 14 | 0.792 (n=6, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 15 | -46.296 (n=6, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 16 | -56.695 (n=4, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 17 | -72.649 (n=5, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 18 | 172.736 (n=2, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 19 | -100.986 (n=5, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 20 | -91.464 (n=3, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 21 | -8.049 (n=6, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA100 | weekend | 22 | -1.964 (n=25, G=8; 95% CI [-5.586, 1.136]) |
| flx:USA100 | weekend | 23 | -7.357 (n=1, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA500 | RTH | 13 | -3.336 (n=141, G=26; 95% CI [-5.499, -1.294]) |
| flx:USA500 | RTH | 14 | -2.711 (n=297, G=28; 95% CI [-4.222, -1.325]) |
| flx:USA500 | RTH | 15 | -1.742 (n=318, G=40; 95% CI [-3.785, 0.465]) |
| flx:USA500 | RTH | 16 | -2.629 (n=203, G=35; 95% CI [-5.002, -1.364]) |
| flx:USA500 | RTH | 17 | -2.997 (n=204, G=34; 95% CI [-4.222, -2.128]) |
| flx:USA500 | RTH | 18 | -1.921 (n=237, G=29; 95% CI [-2.895, -1.226]) |
| flx:USA500 | RTH | 19 | -4.055 (n=173, G=31; 95% CI [-5.694, -2.507]) |
| flx:USA500 | off-hours-weekday | 0 | -3.644 (n=25, G=10; 95% CI [-6.694, -0.755]) |
| flx:USA500 | off-hours-weekday | 1 | 0.843 (n=80, G=20; 95% CI [-1.626, 3.673]) |
| flx:USA500 | off-hours-weekday | 2 | -1.202 (n=131, G=22; 95% CI [-5.843, 1.329]) |
| flx:USA500 | off-hours-weekday | 3 | 3.965 (n=99, G=18; 95% CI [-0.360, 17.060]) |
| flx:USA500 | off-hours-weekday | 4 | -0.551 (n=93, G=21; 95% CI [-2.179, 0.126]) |
| flx:USA500 | off-hours-weekday | 5 | -1.616 (n=75, G=23; 95% CI [-2.589, -0.744]) |
| flx:USA500 | off-hours-weekday | 6 | -2.161 (n=86, G=23; 95% CI [-4.126, -0.675]) |
| flx:USA500 | off-hours-weekday | 7 | -0.885 (n=84, G=25; 95% CI [-1.748, -0.230]) |
| flx:USA500 | off-hours-weekday | 8 | -1.966 (n=63, G=20; 95% CI [-3.502, -0.678]) |
| flx:USA500 | off-hours-weekday | 9 | -1.163 (n=124, G=26; 95% CI [-2.903, -0.273]) |
| flx:USA500 | off-hours-weekday | 10 | -2.418 (n=151, G=23; 95% CI [-4.059, -1.434]) |
| flx:USA500 | off-hours-weekday | 11 | 0.410 (n=116, G=26; 95% CI [-3.235, 5.971]) |
| flx:USA500 | off-hours-weekday | 12 | -2.226 (n=158, G=32; 95% CI [-4.257, -0.314]) |
| flx:USA500 | off-hours-weekday | 13 | -2.329 (n=54, G=18; 95% CI [-4.651, -1.004]) |
| flx:USA500 | off-hours-weekday | 14 | -0.624 (n=5, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA500 | off-hours-weekday | 15 | 1.460 (n=3, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA500 | off-hours-weekday | 16 | -4.031 (n=2, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA500 | off-hours-weekday | 17 | 9.662 (n=1, G=1; 95% CI undefined—insufficient evidence) |
| flx:USA500 | off-hours-weekday | 20 | -2.399 (n=85, G=29; 95% CI [-3.739, -1.271]) |
| flx:USA500 | off-hours-weekday | 21 | 2.248 (n=58, G=18; 95% CI [-13.036, 13.411]) |
| flx:USA500 | off-hours-weekday | 22 | 0.279 (n=140, G=23; 95% CI [-2.974, 4.424]) |
| flx:USA500 | off-hours-weekday | 23 | -0.776 (n=69, G=31; 95% CI [-2.555, 1.512]) |
| flx:USA500 | weekend | 0 | 1.854 (n=62, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 1 | 0.002 (n=37, G=8; 95% CI [-2.908, 3.925]) |
| flx:USA500 | weekend | 2 | 2.894 (n=25, G=8; 95% CI [-3.807, 8.929]) |
| flx:USA500 | weekend | 3 | -3.572 (n=36, G=4; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 4 | 52.725 (n=18, G=5; 95% CI [10.439, 127.948]) |
| flx:USA500 | weekend | 5 | 26.434 (n=10, G=6; 95% CI [-4.689, 85.331]) |
| flx:USA500 | weekend | 6 | 14.637 (n=24, G=3; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 7 | 12.828 (n=25, G=6; 95% CI [-9.499, 38.782]) |
| flx:USA500 | weekend | 8 | 21.384 (n=27, G=5; 95% CI [-0.625, 72.477]) |
| flx:USA500 | weekend | 9 | 7.023 (n=4, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 10 | 21.488 (n=3, G=2; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 11 | 29.119 (n=15, G=6; 95% CI [2.034, 53.439]) |
| flx:USA500 | weekend | 12 | 6.442 (n=14, G=7; 95% CI [-1.072, 13.554]) |
| flx:USA500 | weekend | 13 | -20.118 (n=43, G=6; 95% CI [-30.418, -9.324]) |
| flx:USA500 | weekend | 14 | 5.431 (n=29, G=8; 95% CI [-2.224, 9.721]) |
| flx:USA500 | weekend | 15 | -28.472 (n=30, G=5; 95% CI [-57.245, 20.287]) |
| flx:USA500 | weekend | 16 | 6.919 (n=9, G=7; 95% CI [-2.106, 12.707]) |
| flx:USA500 | weekend | 17 | 1.247 (n=10, G=6; 95% CI [-2.188, 4.947]) |
| flx:USA500 | weekend | 18 | 13.110 (n=26, G=12; 95% CI [0.819, 31.165]) |
| flx:USA500 | weekend | 19 | 1.160 (n=11, G=5; 95% CI [-10.953, 8.218]) |
| flx:USA500 | weekend | 20 | -0.442 (n=22, G=6; 95% CI [-3.545, 5.209]) |
| flx:USA500 | weekend | 21 | -6.207 (n=26, G=4; 95% CI undefined—insufficient evidence) |
| flx:USA500 | weekend | 22 | -0.230 (n=224, G=13; 95% CI [-2.666, 3.414]) |
| flx:USA500 | weekend | 23 | 7.003 (n=37, G=11; 95% CI [-3.684, 32.089]) |
| km:SMALL2000 | RTH | 13 | -3.615 (n=1520, G=60; 95% CI [-4.243, -3.038]) |
| km:SMALL2000 | RTH | 14 | -3.464 (n=2224, G=61; 95% CI [-3.938, -2.994]) |
| km:SMALL2000 | RTH | 15 | -2.731 (n=1859, G=61; 95% CI [-3.095, -2.355]) |
| km:SMALL2000 | RTH | 16 | -2.725 (n=1351, G=58; 95% CI [-3.290, -2.246]) |
| km:SMALL2000 | RTH | 17 | -2.673 (n=1178, G=61; 95% CI [-3.057, -2.279]) |
| km:SMALL2000 | RTH | 18 | -2.566 (n=1158, G=59; 95% CI [-2.882, -2.257]) |
| km:SMALL2000 | RTH | 19 | -2.664 (n=1525, G=59; 95% CI [-3.086, -2.273]) |
| km:SMALL2000 | off-hours-weekday | 0 | -4.145 (n=326, G=37; 95% CI [-5.675, -2.736]) |
| km:SMALL2000 | off-hours-weekday | 1 | -8.625 (n=518, G=46; 95% CI [-20.814, -2.059]) |
| km:SMALL2000 | off-hours-weekday | 2 | -3.118 (n=356, G=49; 95% CI [-3.989, -2.351]) |
| km:SMALL2000 | off-hours-weekday | 3 | 2.270 (n=302, G=46; 95% CI [-3.156, 7.790]) |
| km:SMALL2000 | off-hours-weekday | 4 | -2.889 (n=222, G=44; 95% CI [-3.641, -2.106]) |
| km:SMALL2000 | off-hours-weekday | 5 | -2.537 (n=282, G=44; 95% CI [-3.710, -1.197]) |
| km:SMALL2000 | off-hours-weekday | 6 | -3.061 (n=421, G=48; 95% CI [-3.763, -2.322]) |
| km:SMALL2000 | off-hours-weekday | 7 | -2.621 (n=583, G=58; 95% CI [-3.220, -2.076]) |
| km:SMALL2000 | off-hours-weekday | 8 | -3.190 (n=689, G=58; 95% CI [-3.710, -2.729]) |
| km:SMALL2000 | off-hours-weekday | 9 | -3.112 (n=659, G=53; 95% CI [-3.533, -2.612]) |
| km:SMALL2000 | off-hours-weekday | 10 | -3.004 (n=644, G=57; 95% CI [-3.509, -2.428]) |
| km:SMALL2000 | off-hours-weekday | 11 | -6.414 (n=674, G=54; 95% CI [-12.309, -2.747]) |
| km:SMALL2000 | off-hours-weekday | 12 | -3.514 (n=1021, G=59; 95% CI [-4.077, -2.787]) |
| km:SMALL2000 | off-hours-weekday | 13 | -2.690 (n=509, G=52; 95% CI [-3.333, -2.045]) |
| km:SMALL2000 | off-hours-weekday | 15 | -19.108 (n=1, G=1; 95% CI undefined—insufficient evidence) |
| km:SMALL2000 | off-hours-weekday | 20 | -2.384 (n=771, G=56; 95% CI [-3.828, -0.516]) |
| km:SMALL2000 | off-hours-weekday | 21 | 2.897 (n=652, G=42; 95% CI [-6.545, 7.134]) |
| km:SMALL2000 | off-hours-weekday | 22 | -6.348 (n=647, G=49; 95% CI [-10.588, -2.024]) |
| km:SMALL2000 | off-hours-weekday | 23 | -3.423 (n=351, G=41; 95% CI [-4.311, -2.079]) |
| km:SMALL2000 | weekend | 0 | -6.622 (n=7, G=2; 95% CI undefined—insufficient evidence) |
| km:SMALL2000 | weekend | 1 | -2.552 (n=131, G=17; 95% CI [-6.277, 1.135]) |
| km:SMALL2000 | weekend | 2 | 0.435 (n=113, G=19; 95% CI [-8.810, 9.967]) |
| km:SMALL2000 | weekend | 3 | -3.957 (n=99, G=18; 95% CI [-7.653, 1.335]) |
| km:SMALL2000 | weekend | 4 | -6.298 (n=50, G=9; 95% CI [-8.514, -0.399]) |
| km:SMALL2000 | weekend | 5 | 1.397 (n=23, G=8; 95% CI [-4.806, 14.243]) |
| km:SMALL2000 | weekend | 6 | -2.203 (n=20, G=12; 95% CI [-4.986, 0.894]) |
| km:SMALL2000 | weekend | 7 | -0.647 (n=40, G=14; 95% CI [-3.702, 1.143]) |
| km:SMALL2000 | weekend | 8 | 2.483 (n=35, G=12; 95% CI [-7.099, 11.490]) |
| km:SMALL2000 | weekend | 9 | -0.249 (n=44, G=12; 95% CI [-3.891, 6.840]) |
| km:SMALL2000 | weekend | 10 | -3.783 (n=49, G=11; 95% CI [-6.114, -0.632]) |
| km:SMALL2000 | weekend | 11 | -2.723 (n=20, G=9; 95% CI [-7.418, 0.720]) |
| km:SMALL2000 | weekend | 12 | 3.170 (n=34, G=9; 95% CI [-0.660, 6.583]) |
| km:SMALL2000 | weekend | 13 | 1.385 (n=48, G=12; 95% CI [-4.194, 5.609]) |
| km:SMALL2000 | weekend | 14 | -14.049 (n=37, G=14; 95% CI [-39.349, 4.305]) |
| km:SMALL2000 | weekend | 15 | -1.175 (n=44, G=10; 95% CI [-5.626, 0.340]) |
| km:SMALL2000 | weekend | 16 | -0.729 (n=35, G=13; 95% CI [-2.632, 2.408]) |
| km:SMALL2000 | weekend | 17 | 2.011 (n=45, G=9; 95% CI [-6.212, 10.477]) |
| km:SMALL2000 | weekend | 18 | -1.326 (n=63, G=9; 95% CI [-4.967, 7.824]) |
| km:SMALL2000 | weekend | 19 | -1.825 (n=61, G=11; 95% CI [-3.139, -0.691]) |
| km:SMALL2000 | weekend | 20 | -7.507 (n=97, G=16; 95% CI [-9.114, -2.279]) |
| km:SMALL2000 | weekend | 21 | 17.550 (n=111, G=18; 95% CI [-5.017, 31.532]) |
| km:SMALL2000 | weekend | 22 | -6.868 (n=105, G=13; 95% CI [-11.985, -1.874]) |
| km:SMALL2000 | weekend | 23 | -6.086 (n=92, G=14; 95% CI [-10.027, 2.978]) |
| km:US500 | RTH | 13 | -2.445 (n=11622, G=60; 95% CI [-2.525, -2.365]) |
| km:US500 | RTH | 14 | -2.464 (n=19291, G=61; 95% CI [-2.589, -2.346]) |
| km:US500 | RTH | 15 | -2.452 (n=17434, G=61; 95% CI [-2.527, -2.375]) |
| km:US500 | RTH | 16 | -2.452 (n=13871, G=59; 95% CI [-2.548, -2.358]) |
| km:US500 | RTH | 17 | -2.462 (n=13729, G=61; 95% CI [-2.606, -2.338]) |
| km:US500 | RTH | 18 | -2.317 (n=12167, G=60; 95% CI [-2.382, -2.249]) |
| km:US500 | RTH | 19 | -2.485 (n=11808, G=61; 95% CI [-2.632, -2.350]) |
| km:US500 | off-hours-weekday | 0 | -2.623 (n=4118, G=51; 95% CI [-2.913, -2.388]) |
| km:US500 | off-hours-weekday | 1 | -2.332 (n=4049, G=61; 95% CI [-2.431, -2.212]) |
| km:US500 | off-hours-weekday | 2 | -2.395 (n=3259, G=61; 95% CI [-2.604, -2.209]) |
| km:US500 | off-hours-weekday | 3 | -2.178 (n=2195, G=63; 95% CI [-2.321, -2.025]) |
| km:US500 | off-hours-weekday | 4 | -2.193 (n=2009, G=63; 95% CI [-2.299, -2.083]) |
| km:US500 | off-hours-weekday | 5 | -2.440 (n=2797, G=63; 95% CI [-2.577, -2.298]) |
| km:US500 | off-hours-weekday | 6 | -2.319 (n=3753, G=63; 95% CI [-2.407, -2.224]) |
| km:US500 | off-hours-weekday | 7 | -2.365 (n=5078, G=63; 95% CI [-2.437, -2.286]) |
| km:US500 | off-hours-weekday | 8 | -2.397 (n=6515, G=62; 95% CI [-2.485, -2.317]) |
| km:US500 | off-hours-weekday | 9 | -2.323 (n=6302, G=63; 95% CI [-2.403, -2.238]) |
| km:US500 | off-hours-weekday | 10 | -2.465 (n=6477, G=63; 95% CI [-2.612, -2.328]) |
| km:US500 | off-hours-weekday | 11 | -2.730 (n=6788, G=62; 95% CI [-3.443, -2.333]) |
| km:US500 | off-hours-weekday | 12 | -2.471 (n=8578, G=62; 95% CI [-2.580, -2.360]) |
| km:US500 | off-hours-weekday | 13 | -2.365 (n=4553, G=62; 95% CI [-2.509, -2.239]) |
| km:US500 | off-hours-weekday | 14 | -1.993 (n=24, G=2; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 15 | -3.020 (n=51, G=2; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 16 | -1.631 (n=41, G=2; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 17 | -1.798 (n=20, G=1; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 18 | -2.920 (n=34, G=1; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 19 | -3.272 (n=38, G=2; 95% CI undefined—insufficient evidence) |
| km:US500 | off-hours-weekday | 20 | -2.619 (n=5460, G=62; 95% CI [-2.862, -2.375]) |
| km:US500 | off-hours-weekday | 21 | -1.991 (n=1604, G=62; 95% CI [-2.238, -1.778]) |
| km:US500 | off-hours-weekday | 22 | -2.295 (n=4049, G=63; 95% CI [-2.504, -2.095]) |
| km:US500 | off-hours-weekday | 23 | -2.558 (n=3050, G=63; 95% CI [-3.101, -2.179]) |
| km:US500 | weekend | 0 | -2.571 (n=1544, G=18; 95% CI [-2.779, -2.312]) |
| km:US500 | weekend | 1 | -2.316 (n=1573, G=24; 95% CI [-2.719, -1.879]) |
| km:US500 | weekend | 2 | -2.215 (n=1050, G=25; 95% CI [-2.474, -1.929]) |
| km:US500 | weekend | 3 | -2.124 (n=904, G=25; 95% CI [-2.315, -1.916]) |
| km:US500 | weekend | 4 | -1.376 (n=674, G=20; 95% CI [-1.850, -1.117]) |
| km:US500 | weekend | 5 | -1.637 (n=719, G=21; 95% CI [-2.519, -1.371]) |
| km:US500 | weekend | 6 | -1.890 (n=639, G=24; 95% CI [-3.212, -1.450]) |
| km:US500 | weekend | 7 | -2.129 (n=649, G=26; 95% CI [-2.813, -1.671]) |
| km:US500 | weekend | 8 | -1.775 (n=615, G=24; 95% CI [-2.248, -1.471]) |
| km:US500 | weekend | 9 | -1.542 (n=1023, G=24; 95% CI [-1.847, -1.370]) |
| km:US500 | weekend | 10 | -1.576 (n=1212, G=26; 95% CI [-1.850, -1.443]) |
| km:US500 | weekend | 11 | -1.668 (n=872, G=25; 95% CI [-1.985, -1.489]) |
| km:US500 | weekend | 12 | -1.787 (n=1087, G=25; 95% CI [-2.128, -1.514]) |
| km:US500 | weekend | 13 | -1.785 (n=1011, G=22; 95% CI [-2.125, -1.402]) |
| km:US500 | weekend | 14 | -2.113 (n=1153, G=26; 95% CI [-2.456, -1.628]) |
| km:US500 | weekend | 15 | -1.864 (n=952, G=26; 95% CI [-2.016, -1.728]) |
| km:US500 | weekend | 16 | -1.927 (n=1033, G=25; 95% CI [-2.351, -1.656]) |
| km:US500 | weekend | 17 | -2.059 (n=802, G=25; 95% CI [-2.553, -1.721]) |
| km:US500 | weekend | 18 | -2.682 (n=827, G=26; 95% CI [-3.424, -1.666]) |
| km:US500 | weekend | 19 | -1.872 (n=950, G=26; 95% CI [-2.073, -1.703]) |
| km:US500 | weekend | 20 | -2.036 (n=1098, G=24; 95% CI [-2.467, -1.600]) |
| km:US500 | weekend | 21 | -1.825 (n=902, G=25; 95% CI [-2.769, -1.118]) |
| km:US500 | weekend | 22 | -3.053 (n=2358, G=25; 95% CI [-3.736, -2.381]) |
| km:US500 | weekend | 23 | -2.333 (n=1457, G=24; 95% CI [-2.819, -1.816]) |
| km:USTECH | RTH | 13 | -2.835 (n=4406, G=60; 95% CI [-3.073, -2.585]) |
| km:USTECH | RTH | 14 | -2.727 (n=6173, G=61; 95% CI [-2.933, -2.538]) |
| km:USTECH | RTH | 15 | -2.700 (n=5238, G=61; 95% CI [-2.870, -2.539]) |
| km:USTECH | RTH | 16 | -2.498 (n=6066, G=59; 95% CI [-2.629, -2.364]) |
| km:USTECH | RTH | 17 | -2.641 (n=6721, G=61; 95% CI [-2.886, -2.464]) |
| km:USTECH | RTH | 18 | -2.432 (n=5477, G=60; 95% CI [-2.546, -2.324]) |
| km:USTECH | RTH | 19 | -2.621 (n=5726, G=61; 95% CI [-2.827, -2.429]) |
| km:USTECH | off-hours-weekday | 0 | -2.840 (n=1484, G=49; 95% CI [-3.183, -2.547]) |
| km:USTECH | off-hours-weekday | 1 | -2.596 (n=1373, G=61; 95% CI [-2.816, -2.413]) |
| km:USTECH | off-hours-weekday | 2 | -2.851 (n=1048, G=59; 95% CI [-3.624, -2.346]) |
| km:USTECH | off-hours-weekday | 3 | -2.470 (n=803, G=58; 95% CI [-2.670, -2.275]) |
| km:USTECH | off-hours-weekday | 4 | -2.225 (n=776, G=60; 95% CI [-2.425, -1.983]) |
| km:USTECH | off-hours-weekday | 5 | -2.533 (n=1038, G=61; 95% CI [-2.688, -2.368]) |
| km:USTECH | off-hours-weekday | 6 | -2.398 (n=1232, G=63; 95% CI [-2.569, -2.227]) |
| km:USTECH | off-hours-weekday | 7 | -2.511 (n=1563, G=62; 95% CI [-2.673, -2.367]) |
| km:USTECH | off-hours-weekday | 8 | -2.595 (n=1868, G=62; 95% CI [-2.752, -2.444]) |
| km:USTECH | off-hours-weekday | 9 | -2.395 (n=1834, G=63; 95% CI [-2.571, -2.232]) |
| km:USTECH | off-hours-weekday | 10 | -2.707 (n=1707, G=62; 95% CI [-3.187, -2.354]) |
| km:USTECH | off-hours-weekday | 11 | -2.965 (n=2043, G=62; 95% CI [-3.829, -2.426]) |
| km:USTECH | off-hours-weekday | 12 | -2.579 (n=2711, G=62; 95% CI [-2.799, -2.323]) |
| km:USTECH | off-hours-weekday | 13 | -2.930 (n=1431, G=62; 95% CI [-3.741, -2.456]) |
| km:USTECH | off-hours-weekday | 14 | -2.477 (n=16, G=1; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 15 | -3.514 (n=20, G=2; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 16 | -2.190 (n=6, G=1; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 17 | -2.845 (n=7, G=1; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 18 | -6.528 (n=18, G=1; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 19 | -7.216 (n=20, G=2; 95% CI undefined—insufficient evidence) |
| km:USTECH | off-hours-weekday | 20 | -2.603 (n=2645, G=63; 95% CI [-2.937, -2.269]) |
| km:USTECH | off-hours-weekday | 21 | -3.184 (n=599, G=60; 95% CI [-4.005, -2.382]) |
| km:USTECH | off-hours-weekday | 22 | -2.300 (n=1662, G=62; 95% CI [-2.861, -1.592]) |
| km:USTECH | off-hours-weekday | 23 | -2.306 (n=1169, G=62; 95% CI [-2.587, -2.009]) |
| km:USTECH | weekend | 0 | -3.279 (n=336, G=12; 95% CI [-4.311, -2.520]) |
| km:USTECH | weekend | 1 | -3.357 (n=372, G=21; 95% CI [-4.179, -2.554]) |
| km:USTECH | weekend | 2 | -3.435 (n=269, G=24; 95% CI [-5.246, -2.230]) |
| km:USTECH | weekend | 3 | -2.301 (n=275, G=25; 95% CI [-2.640, -1.997]) |
| km:USTECH | weekend | 4 | -3.223 (n=117, G=20; 95% CI [-4.771, -2.107]) |
| km:USTECH | weekend | 5 | -2.342 (n=99, G=16; 95% CI [-3.490, -1.422]) |
| km:USTECH | weekend | 6 | -2.655 (n=97, G=21; 95% CI [-3.395, -1.966]) |
| km:USTECH | weekend | 7 | -3.233 (n=115, G=23; 95% CI [-4.386, -2.139]) |
| km:USTECH | weekend | 8 | -3.026 (n=120, G=19; 95% CI [-4.680, -1.608]) |
| km:USTECH | weekend | 9 | -2.444 (n=111, G=21; 95% CI [-3.516, -1.364]) |
| km:USTECH | weekend | 10 | -2.896 (n=91, G=20; 95% CI [-3.566, -2.315]) |
| km:USTECH | weekend | 11 | -3.504 (n=101, G=17; 95% CI [-4.202, -2.825]) |
| km:USTECH | weekend | 12 | -5.473 (n=135, G=20; 95% CI [-8.234, -2.266]) |
| km:USTECH | weekend | 13 | -2.764 (n=90, G=18; 95% CI [-3.370, -2.019]) |
| km:USTECH | weekend | 14 | -3.359 (n=153, G=22; 95% CI [-4.565, -1.856]) |
| km:USTECH | weekend | 15 | -3.546 (n=151, G=24; 95% CI [-4.393, -2.856]) |
| km:USTECH | weekend | 16 | -4.479 (n=131, G=24; 95% CI [-5.961, -3.053]) |
| km:USTECH | weekend | 17 | -4.093 (n=124, G=21; 95% CI [-4.992, -3.136]) |
| km:USTECH | weekend | 18 | -3.916 (n=156, G=22; 95% CI [-5.580, -2.006]) |
| km:USTECH | weekend | 19 | -3.589 (n=206, G=25; 95% CI [-4.274, -3.034]) |
| km:USTECH | weekend | 20 | -3.636 (n=220, G=20; 95% CI [-4.635, -2.677]) |
| km:USTECH | weekend | 21 | -0.161 (n=222, G=22; 95% CI [-5.827, 9.254]) |
| km:USTECH | weekend | 22 | -2.506 (n=794, G=23; 95% CI [-3.494, -1.806]) |
| km:USTECH | weekend | 23 | -2.833 (n=494, G=22; 95% CI [-3.769, -2.061]) |
| xyz:SP500 | RTH | 13 | -2.044 (n=32051, G=56; 95% CI [-2.095, -1.995]) |
| xyz:SP500 | RTH | 14 | -2.013 (n=50758, G=56; 95% CI [-2.076, -1.955]) |
| xyz:SP500 | RTH | 15 | -1.994 (n=40706, G=56; 95% CI [-2.037, -1.950]) |
| xyz:SP500 | RTH | 16 | -2.003 (n=32711, G=54; 95% CI [-2.064, -1.949]) |
| xyz:SP500 | RTH | 17 | -2.018 (n=30640, G=56; 95% CI [-2.105, -1.942]) |
| xyz:SP500 | RTH | 18 | -1.946 (n=28599, G=55; 95% CI [-1.999, -1.886]) |
| xyz:SP500 | RTH | 19 | -1.998 (n=29806, G=56; 95% CI [-2.072, -1.925]) |
| xyz:SP500 | off-hours-weekday | 0 | -2.058 (n=16025, G=56; 95% CI [-2.189, -1.960]) |
| xyz:SP500 | off-hours-weekday | 1 | -2.008 (n=13974, G=57; 95% CI [-2.069, -1.937]) |
| xyz:SP500 | off-hours-weekday | 2 | -1.970 (n=11160, G=58; 95% CI [-2.082, -1.871]) |
| xyz:SP500 | off-hours-weekday | 3 | -1.835 (n=7960, G=57; 95% CI [-1.891, -1.776]) |
| xyz:SP500 | off-hours-weekday | 4 | -1.850 (n=8833, G=57; 95% CI [-1.907, -1.790]) |
| xyz:SP500 | off-hours-weekday | 5 | -1.934 (n=10915, G=58; 95% CI [-1.990, -1.880]) |
| xyz:SP500 | off-hours-weekday | 6 | -1.906 (n=14118, G=58; 95% CI [-1.948, -1.862]) |
| xyz:SP500 | off-hours-weekday | 7 | -1.974 (n=17425, G=58; 95% CI [-2.018, -1.932]) |
| xyz:SP500 | off-hours-weekday | 8 | -1.998 (n=19367, G=57; 95% CI [-2.049, -1.949]) |
| xyz:SP500 | off-hours-weekday | 9 | -1.953 (n=17752, G=58; 95% CI [-2.003, -1.908]) |
| xyz:SP500 | off-hours-weekday | 10 | -2.028 (n=18481, G=58; 95% CI [-2.132, -1.942]) |
| xyz:SP500 | off-hours-weekday | 11 | -2.104 (n=20040, G=57; 95% CI [-2.399, -1.946]) |
| xyz:SP500 | off-hours-weekday | 12 | -2.037 (n=24460, G=57; 95% CI [-2.092, -1.983]) |
| xyz:SP500 | off-hours-weekday | 13 | -1.908 (n=12773, G=57; 95% CI [-1.964, -1.858]) |
| xyz:SP500 | off-hours-weekday | 14 | -1.852 (n=197, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 15 | -2.045 (n=339, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 16 | -1.550 (n=279, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 17 | -1.722 (n=213, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 18 | -2.077 (n=217, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 19 | -3.198 (n=325, G=2; 95% CI undefined—insufficient evidence) |
| xyz:SP500 | off-hours-weekday | 20 | -2.123 (n=18895, G=58; 95% CI [-2.279, -1.979]) |
| xyz:SP500 | off-hours-weekday | 21 | -1.911 (n=10774, G=57; 95% CI [-2.033, -1.782]) |
| xyz:SP500 | off-hours-weekday | 22 | -1.932 (n=15456, G=58; 95% CI [-1.983, -1.882]) |
| xyz:SP500 | off-hours-weekday | 23 | -1.896 (n=10888, G=58; 95% CI [-1.989, -1.819]) |
| xyz:SP500 | weekend | 0 | -2.009 (n=5760, G=18; 95% CI [-2.109, -1.875]) |
| xyz:SP500 | weekend | 1 | -2.005 (n=5541, G=23; 95% CI [-2.194, -1.855]) |
| xyz:SP500 | weekend | 2 | -1.915 (n=4257, G=24; 95% CI [-2.047, -1.785]) |
| xyz:SP500 | weekend | 3 | -1.780 (n=4213, G=24; 95% CI [-1.912, -1.659]) |
| xyz:SP500 | weekend | 4 | -1.779 (n=2485, G=24; 95% CI [-1.985, -1.566]) |
| xyz:SP500 | weekend | 5 | -1.925 (n=2094, G=24; 95% CI [-2.238, -1.580]) |
| xyz:SP500 | weekend | 6 | -1.843 (n=2287, G=24; 95% CI [-2.028, -1.705]) |
| xyz:SP500 | weekend | 7 | -2.003 (n=2403, G=24; 95% CI [-2.609, -1.625]) |
| xyz:SP500 | weekend | 8 | -1.765 (n=2582, G=24; 95% CI [-1.959, -1.613]) |
| xyz:SP500 | weekend | 9 | -1.799 (n=2558, G=24; 95% CI [-1.963, -1.630]) |
| xyz:SP500 | weekend | 10 | -1.692 (n=2518, G=24; 95% CI [-1.803, -1.602]) |
| xyz:SP500 | weekend | 11 | -1.722 (n=2667, G=24; 95% CI [-1.855, -1.586]) |
| xyz:SP500 | weekend | 12 | -1.783 (n=3169, G=24; 95% CI [-2.021, -1.593]) |
| xyz:SP500 | weekend | 13 | -1.869 (n=3902, G=24; 95% CI [-2.067, -1.707]) |
| xyz:SP500 | weekend | 14 | -1.900 (n=3670, G=24; 95% CI [-2.039, -1.783]) |
| xyz:SP500 | weekend | 15 | -1.995 (n=4175, G=24; 95% CI [-2.172, -1.786]) |
| xyz:SP500 | weekend | 16 | -1.801 (n=4624, G=24; 95% CI [-1.928, -1.667]) |
| xyz:SP500 | weekend | 17 | -1.917 (n=4281, G=24; 95% CI [-2.106, -1.750]) |
| xyz:SP500 | weekend | 18 | -1.544 (n=5870, G=24; 95% CI [-1.883, -1.315]) |
| xyz:SP500 | weekend | 19 | -1.828 (n=4707, G=24; 95% CI [-2.093, -1.581]) |
| xyz:SP500 | weekend | 20 | -1.726 (n=5108, G=24; 95% CI [-1.931, -1.523]) |
| xyz:SP500 | weekend | 21 | -2.070 (n=5908, G=24; 95% CI [-2.278, -1.775]) |
| xyz:SP500 | weekend | 22 | -1.896 (n=10167, G=24; 95% CI [-2.020, -1.784]) |
| xyz:SP500 | weekend | 23 | -1.828 (n=5744, G=24; 95% CI [-1.959, -1.652]) |
| xyz:XYZ100 | RTH | 13 | -2.289 (n=52665, G=60; 95% CI [-2.358, -2.218]) |
| xyz:XYZ100 | RTH | 14 | -2.213 (n=76925, G=61; 95% CI [-2.283, -2.148]) |
| xyz:XYZ100 | RTH | 15 | -2.154 (n=57688, G=61; 95% CI [-2.194, -2.114]) |
| xyz:XYZ100 | RTH | 16 | -2.156 (n=42703, G=59; 95% CI [-2.237, -2.086]) |
| xyz:XYZ100 | RTH | 17 | -2.147 (n=38394, G=61; 95% CI [-2.210, -2.082]) |
| xyz:XYZ100 | RTH | 18 | -2.055 (n=33023, G=60; 95% CI [-2.098, -2.012]) |
| xyz:XYZ100 | RTH | 19 | -2.150 (n=34817, G=61; 95% CI [-2.227, -2.072]) |
| xyz:XYZ100 | off-hours-weekday | 0 | -2.260 (n=19892, G=62; 95% CI [-2.402, -2.152]) |
| xyz:XYZ100 | off-hours-weekday | 1 | -2.158 (n=16557, G=62; 95% CI [-2.232, -2.076]) |
| xyz:XYZ100 | off-hours-weekday | 2 | -2.262 (n=13581, G=63; 95% CI [-2.635, -2.022]) |
| xyz:XYZ100 | off-hours-weekday | 3 | -2.040 (n=10292, G=62; 95% CI [-2.094, -1.992]) |
| xyz:XYZ100 | off-hours-weekday | 4 | -1.967 (n=10253, G=62; 95% CI [-2.016, -1.917]) |
| xyz:XYZ100 | off-hours-weekday | 5 | -2.073 (n=14819, G=63; 95% CI [-2.146, -2.007]) |
| xyz:XYZ100 | off-hours-weekday | 6 | -2.020 (n=18528, G=63; 95% CI [-2.066, -1.975]) |
| xyz:XYZ100 | off-hours-weekday | 7 | -2.072 (n=22048, G=63; 95% CI [-2.112, -2.032]) |
| xyz:XYZ100 | off-hours-weekday | 8 | -2.082 (n=26831, G=62; 95% CI [-2.143, -2.023]) |
| xyz:XYZ100 | off-hours-weekday | 9 | -2.039 (n=23095, G=63; 95% CI [-2.084, -1.996]) |
| xyz:XYZ100 | off-hours-weekday | 10 | -2.075 (n=23427, G=63; 95% CI [-2.169, -1.990]) |
| xyz:XYZ100 | off-hours-weekday | 11 | -2.232 (n=23146, G=62; 95% CI [-2.613, -2.027]) |
| xyz:XYZ100 | off-hours-weekday | 12 | -2.126 (n=29463, G=62; 95% CI [-2.184, -2.065]) |
| xyz:XYZ100 | off-hours-weekday | 13 | -2.046 (n=15883, G=62; 95% CI [-2.138, -1.963]) |
| xyz:XYZ100 | off-hours-weekday | 14 | -1.841 (n=194, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 15 | -2.174 (n=203, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 16 | -1.868 (n=116, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 17 | -2.210 (n=109, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 18 | -2.462 (n=305, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 19 | -2.874 (n=259, G=2; 95% CI undefined—insufficient evidence) |
| xyz:XYZ100 | off-hours-weekday | 20 | -2.249 (n=20173, G=63; 95% CI [-2.456, -2.054]) |
| xyz:XYZ100 | off-hours-weekday | 21 | -1.955 (n=7204, G=62; 95% CI [-2.101, -1.808]) |
| xyz:XYZ100 | off-hours-weekday | 22 | -2.181 (n=17663, G=63; 95% CI [-2.272, -2.094]) |
| xyz:XYZ100 | off-hours-weekday | 23 | -2.074 (n=12729, G=63; 95% CI [-2.115, -2.032]) |
| xyz:XYZ100 | weekend | 0 | -2.169 (n=7042, G=25; 95% CI [-2.320, -2.039]) |
| xyz:XYZ100 | weekend | 1 | -2.330 (n=7006, G=25; 95% CI [-2.517, -2.048]) |
| xyz:XYZ100 | weekend | 2 | -2.367 (n=4840, G=26; 95% CI [-2.984, -1.985]) |
| xyz:XYZ100 | weekend | 3 | -2.036 (n=4586, G=26; 95% CI [-2.179, -1.926]) |
| xyz:XYZ100 | weekend | 4 | -1.989 (n=2853, G=26; 95% CI [-2.739, -1.587]) |
| xyz:XYZ100 | weekend | 5 | -1.983 (n=2502, G=26; 95% CI [-2.523, -1.681]) |
| xyz:XYZ100 | weekend | 6 | -1.831 (n=3320, G=26; 95% CI [-2.099, -1.690]) |
| xyz:XYZ100 | weekend | 7 | -2.571 (n=3377, G=26; 95% CI [-4.116, -1.780]) |
| xyz:XYZ100 | weekend | 8 | -2.004 (n=3706, G=26; 95% CI [-2.502, -1.653]) |
| xyz:XYZ100 | weekend | 9 | -1.965 (n=3228, G=26; 95% CI [-2.205, -1.780]) |
| xyz:XYZ100 | weekend | 10 | -1.973 (n=2750, G=26; 95% CI [-2.131, -1.854]) |
| xyz:XYZ100 | weekend | 11 | -1.928 (n=3235, G=26; 95% CI [-2.348, -1.652]) |
| xyz:XYZ100 | weekend | 12 | -2.388 (n=4494, G=25; 95% CI [-3.238, -1.579]) |
| xyz:XYZ100 | weekend | 13 | -1.984 (n=3645, G=25; 95% CI [-2.331, -1.750]) |
| xyz:XYZ100 | weekend | 14 | -1.905 (n=4125, G=26; 95% CI [-2.230, -1.678]) |
| xyz:XYZ100 | weekend | 15 | -2.145 (n=3513, G=26; 95% CI [-2.384, -1.934]) |
| xyz:XYZ100 | weekend | 16 | -2.210 (n=3393, G=26; 95% CI [-2.534, -1.916]) |
| xyz:XYZ100 | weekend | 17 | -2.198 (n=3147, G=26; 95% CI [-2.684, -1.833]) |
| xyz:XYZ100 | weekend | 18 | -2.165 (n=3621, G=26; 95% CI [-2.470, -1.781]) |
| xyz:XYZ100 | weekend | 19 | -2.198 (n=4343, G=26; 95% CI [-2.658, -1.895]) |
| xyz:XYZ100 | weekend | 20 | -2.187 (n=4261, G=26; 95% CI [-2.517, -1.883]) |
| xyz:XYZ100 | weekend | 21 | -2.445 (n=4352, G=26; 95% CI [-2.874, -2.006]) |
| xyz:XYZ100 | weekend | 22 | -2.141 (n=11727, G=26; 95% CI [-2.288, -1.983]) |
| xyz:XYZ100 | weekend | 23 | -2.139 (n=6772, G=26; 95% CI [-2.277, -2.009]) |

## Secondary: filling-print size bucket

| market | segment | size_bucket | 30s net bps |
|---|---|---|---|
| cash:USA500 | RTH | sweep | -2.110 (n=26128, G=122; 95% CI [-2.159, -2.058]) |
| cash:USA500 | RTH | trickle | -2.262 (n=213390, G=122; 95% CI [-2.304, -2.221]) |
| cash:USA500 | off-hours-weekday | sweep | -2.014 (n=25115, G=264; 95% CI [-2.117, -1.935]) |
| cash:USA500 | off-hours-weekday | trickle | -2.200 (n=206983, G=264; 95% CI [-2.236, -2.168]) |
| cash:USA500 | weekend | sweep | -1.924 (n=6110, G=116; 95% CI [-2.138, -1.729]) |
| cash:USA500 | weekend | trickle | -2.293 (n=36266, G=117; 95% CI [-2.414, -2.181]) |
| flx:USA100 | RTH | sweep | -22.678 (n=17, G=7; 95% CI [-67.898, -0.258]) |
| flx:USA100 | RTH | trickle | -2.948 (n=328, G=35; 95% CI [-6.148, -0.775]) |
| flx:USA100 | off-hours-weekday | sweep | 3.718 (n=45, G=20; 95% CI [-43.662, 54.069]) |
| flx:USA100 | off-hours-weekday | trickle | -4.401 (n=305, G=61; 95% CI [-13.736, 4.676]) |
| flx:USA100 | weekend | sweep | 12.299 (n=10, G=9; 95% CI [-61.606, 100.860]) |
| flx:USA100 | weekend | trickle | -14.810 (n=89, G=29; 95% CI [-48.248, 15.641]) |
| flx:USA500 | RTH | sweep | -2.195 (n=381, G=60; 95% CI [-3.456, -1.040]) |
| flx:USA500 | RTH | trickle | -2.764 (n=1192, G=89; 95% CI [-3.770, -1.763]) |
| flx:USA500 | off-hours-weekday | sweep | -0.030 (n=346, G=97; 95% CI [-1.607, 1.822]) |
| flx:USA500 | off-hours-weekday | trickle | -1.002 (n=1356, G=176; 95% CI [-1.902, -0.126]) |
| flx:USA500 | weekend | sweep | 2.889 (n=217, G=37; 95% CI [-6.958, 14.773]) |
| flx:USA500 | weekend | trickle | 2.577 (n=550, G=71; 95% CI [-1.838, 7.335]) |
| km:SMALL2000 | RTH | sweep | -3.027 (n=2462, G=105; 95% CI [-3.359, -2.670]) |
| km:SMALL2000 | RTH | trickle | -2.956 (n=8353, G=122; 95% CI [-3.159, -2.744]) |
| km:SMALL2000 | off-hours-weekday | sweep | -2.947 (n=2314, G=197; 95% CI [-5.479, -0.725]) |
| km:SMALL2000 | off-hours-weekday | trickle | -3.327 (n=7314, G=251; 95% CI [-4.536, -2.234]) |
| km:SMALL2000 | weekend | sweep | 0.605 (n=458, G=74; 95% CI [-5.283, 8.555]) |
| km:SMALL2000 | weekend | trickle | -2.228 (n=945, G=91; 95% CI [-4.667, 0.897]) |
| km:US500 | RTH | sweep | -2.434 (n=27998, G=122; 95% CI [-2.493, -2.375]) |
| km:US500 | RTH | trickle | -2.445 (n=71924, G=122; 95% CI [-2.496, -2.393]) |
| km:US500 | off-hours-weekday | sweep | -2.386 (n=22887, G=263; 95% CI [-2.462, -2.305]) |
| km:US500 | off-hours-weekday | trickle | -2.450 (n=57955, G=264; 95% CI [-2.548, -2.373]) |
| km:US500 | weekend | sweep | -2.116 (n=7195, G=114; 95% CI [-2.348, -1.899]) |
| km:US500 | weekend | trickle | -2.090 (n=17909, G=116; 95% CI [-2.284, -1.905]) |
| km:USTECH | RTH | sweep | -2.598 (n=11235, G=121; 95% CI [-2.714, -2.486]) |
| km:USTECH | RTH | trickle | -2.642 (n=28572, G=122; 95% CI [-2.730, -2.556]) |
| km:USTECH | off-hours-weekday | sweep | -2.687 (n=7036, G=258; 95% CI [-2.871, -2.516]) |
| km:USTECH | off-hours-weekday | trickle | -2.590 (n=20037, G=263; 95% CI [-2.715, -2.476]) |
| km:USTECH | weekend | sweep | -2.884 (n=1454, G=106; 95% CI [-4.023, -1.194]) |
| km:USTECH | weekend | trickle | -3.095 (n=3525, G=113; 95% CI [-3.422, -2.795]) |
| xyz:SP500 | RTH | sweep | -1.972 (n=64798, G=112; 95% CI [-2.010, -1.935]) |
| xyz:SP500 | RTH | trickle | -2.015 (n=180473, G=112; 95% CI [-2.044, -1.986]) |
| xyz:SP500 | off-hours-weekday | sweep | -1.970 (n=70926, G=243; 95% CI [-2.010, -1.933]) |
| xyz:SP500 | off-hours-weekday | trickle | -1.993 (n=199940, G=243; 95% CI [-2.026, -1.963]) |
| xyz:SP500 | weekend | sweep | -1.779 (n=30583, G=108; 95% CI [-1.850, -1.703]) |
| xyz:SP500 | weekend | trickle | -1.893 (n=70107, G=108; 95% CI [-1.947, -1.833]) |
| xyz:XYZ100 | RTH | sweep | -2.003 (n=70563, G=122; 95% CI [-2.050, -1.959]) |
| xyz:XYZ100 | RTH | trickle | -2.224 (n=265652, G=122; 95% CI [-2.256, -2.192]) |
| xyz:XYZ100 | off-hours-weekday | sweep | -1.999 (n=61878, G=264; 95% CI [-2.045, -1.957]) |
| xyz:XYZ100 | off-hours-weekday | trickle | -2.145 (n=264892, G=264; 95% CI [-2.195, -2.106]) |
| xyz:XYZ100 | weekend | sweep | -2.080 (n=27331, G=117; 95% CI [-2.233, -1.943]) |
| xyz:XYZ100 | weekend | trickle | -2.179 (n=78507, G=117; 95% CI [-2.308, -2.068]) |

## Era-overlap cross-validation

Window: 2026-05-08 through 2026-06-08. Count agreement is `min(L2,L4)/max(L2,L4)`. Exact-event agreement uses timestamp, price, and size. Timestamp alignment compares unique exchange timestamps; aligned-price difference is mean absolute bps at shared timestamps. All interval metrics resample UTC six-hour clusters.

| Market | Trade counts | Count agreement | Exact-event agreement | Timestamp alignment | Aligned price abs diff bps |
|---|---:|---:|---:|---:|---:|
| xyz:SP500 | L2 n=2075292; L4 n=1880374 | 90.608% (n=2075292, G=128; 95% CI [84.543, 96.511]%) | 88.251% (n=2075292, G=128; 95% CI [82.657, 92.836]%) | 89.874% (n=952206, G=128; 95% CI [84.752, 93.983]%) | 0.000 (n=855783, G=128; 95% CI [0.000, 0.000]) |
| km:US500 | L2 n=523346; L4 n=445220 | 85.072% (n=523346, G=128; 95% CI [76.673, 93.250]%) | 82.163% (n=523346, G=128; 95% CI [74.621, 88.929]%) | 82.539% (n=194960, G=128; 95% CI [74.296, 89.950]%) | 0.000 (n=160918, G=128; 95% CI [0.000, 0.000]) |
| flx:USA500 | L2 n=10010; L4 n=2234 | 22.318% (n=10010, G=113; 95% CI [16.660, 29.085]%) | 20.020% (n=10010, G=113; 95% CI [15.670, 24.716]%) | 61.964% (n=2495, G=113; 95% CI [51.151, 71.681]%) | 0.001 (n=1546, G=113; 95% CI [0.000, 0.001]) |
| cash:USA500 | L2 n=517943; L4 n=480572 | 92.785% (n=517943, G=128; 95% CI [84.323, 99.430]%) | 88.398% (n=517943, G=128; 95% CI [81.340, 93.191]%) | 90.058% (n=215077, G=128; 95% CI [83.615, 94.653]%) | 0.000 (n=193693, G=128; 95% CI [0.000, 0.000]) |
| km:USTECH | L2 n=117082; L4 n=99232 | 84.754% (n=117082, G=128; 95% CI [79.169, 89.306]%) | 83.494% (n=117082, G=128; 95% CI [78.129, 87.756]%) | 89.885% (n=64459, G=128; 95% CI [84.787, 93.978]%) | 0.000 (n=57939, G=128; 95% CI [0.000, 0.000]) |
| xyz:XYZ100 | L2 n=2507196; L4 n=2284774 | 91.129% (n=2507196, G=128; 95% CI [84.838, 97.493]%) | 88.347% (n=2507196, G=128; 95% CI [82.879, 92.958]%) | 88.740% (n=1107292, G=128; 95% CI [83.552, 93.207]%) | 0.000 (n=982616, G=128; 95% CI [0.000, 0.000]) |
| flx:USA100 | L2 n=9256; L4 n=2277 | 24.600% (n=9256, G=94; 95% CI [17.034, 32.376]%) | 24.363% (n=9256, G=94; 95% CI [16.828, 32.113]%) | 74.868% (n=2845, G=94; 95% CI [63.672, 82.077]%) | 0.000 (n=2130, G=94; 95% CI [0.000, 0.001]) |
| km:SMALL2000 | L2 n=19955; L4 n=10777 | 54.007% (n=19955, G=127; 95% CI [42.770, 63.426]%) | 52.528% (n=19955, G=127; 95% CI [41.056, 61.967]%) | 84.326% (n=9264, G=127; 95% CI [75.310, 90.526]%) | 0.001 (n=7812, G=127; 95% CI [0.000, 0.002]) |

Overlap input caveat: the following on-disk file failed gzip decompression and was excluded:
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47427799+SC-HYPERLIQUIDL4_DPERP_XYZ_SP500_USDC+S-XYZ__003ASP500.csv.gz: corrupt deflate stream`
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47427852+SC-HYPERLIQUIDL4_DPERP_KM_US500_USDC+S-KM__003AUS500.csv.gz: corrupt deflate stream`
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47428064+SC-HYPERLIQUIDL4_DPERP_CASH_USA500_USDC+S-CASH__003AUSA500.csv.gz: corrupt deflate stream`
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47427856+SC-HYPERLIQUIDL4_DPERP_KM_USTECH_USDC+S-KM__003AUSTECH.csv.gz: corrupt deflate stream`
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47427754+SC-HYPERLIQUIDL4_DPERP_XYZ_XYZ100_USDC+S-XYZ__003AXYZ100.csv.gz: corrupt deflate stream`
- `data/T-TRADES/D-2026052715/E-HYPERLIQUIDL4/IDDI-47427855+SC-HYPERLIQUIDL4_DPERP_KM_SMALL2000_USDC+S-KM__003ASMALL2000.csv.gz: corrupt deflate stream`

## Exchange-to-CoinAPI latency context

Latency uses L2 trade rows and `time_coinapi-time_exchange`. Each item includes n, G, and a six-hour-cluster-bootstrap interval.

- Mean milliseconds: 110342.295 (n=22704115, G=3211; 95% CI [96115.792, 125247.472])
- Negative: 0.000% (n=22704115, G=3211; 95% CI [0.000, 0.000]%)
- At or below 500 ms: 69.487% (n=22704115, G=3211; 95% CI [68.577, 70.470]%)
- At or below 1,000 ms: 92.085% (n=22704115, G=3211; 95% CI [91.563, 92.611]%)
- At or below 5,000 ms: 99.192% (n=22704115, G=3211; 95% CI [99.134, 99.244]%)

## Funding fetch

The public Hyperliquid funding-history REST endpoint was queried at no more than one request per second. Funding is applied as the latest known hourly rate and held fixed through each short markout horizon.

| Market | API rows (n) | REST calls (n) | Explicit zero series | Initial zero prefix |
|---|---:|---:|---|---|
| xyz:SP500 | 1978 | 4 | false | true |
| km:US500 | 2184 | 5 | false | true |
| flx:USA500 | 2171 | 5 | false | true |
| cash:USA500 | 2184 | 5 | false | true |
| km:USTECH | 2184 | 5 | false | true |
| xyz:XYZ100 | 2184 | 5 | false | true |
| flx:USA100 | 1688 | 4 | false | true |
| km:SMALL2000 | 2184 | 5 | false | true |

The explicit pre-first-record zero prefix was used by n=21 `xyz:SP500` fills before that market's first API funding row; every other market had n=0 fills using the prefix. No market used an all-zero funding series.

## Biases and assumptions

- The passive-fill rule is an optimistic upper bound because prints do not reveal cancellations ahead, hidden liquidity, exact priority, or the order's effect on subsequent flow.
- The maker fee is assumed at 1.5 bps. Funding uses the latest REST hourly rate known at fill and holds it fixed across the horizon.
- One-sided or invalid L1 rows are skipped for microprice and fill eligibility. Trades sharing an exact timestamp with an L1 change are dropped because within-timestamp ordering is unknown (ADV-3).
- Confidence intervals use a pooled nonparametric bootstrap of market × UTC six-hour clusters, 2,000 resamples, seed 0, and minimum G=5. The quote-age ceiling is 60 seconds. Fee, age ceiling, resample count, seed, cluster length, and minimum cluster count are operator-tunable.
- The L2 book is level-aggregated; queue-ahead is displayed touch size at join. The optional L4 quotes-as-L1 run was not executed, so no top-of-book queue-ahead results are mixed into the L2 primary.
- Stable sorting and the feed sanitation counts above address rotated daily chunks and depth-truncated snapshot updates without using future state. Invalid/crossed rows reset eligibility rather than generating a fill.

## Artifacts and follow-ups

- Per-fill L2 artifact: `data/reports/study1_fills_l2.parquet`.
- Funding artifact: `data/reports/study1_funding.parquet`.
- Optional follow-up: run L4 quotes-as-L1 markouts and label their queue-ahead model as top-of-book/coarser.
