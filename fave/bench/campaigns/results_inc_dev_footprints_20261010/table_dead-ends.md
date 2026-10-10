| workload | stream | engine | completed | refused | changed | re-checked | selectivity | precision | t_total median | p90 | p99 | max | t_update med | t_recheck med |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wl_airtel1 | s1 | apkeep | 200 of 200 | 0 | 0 | 2665 | 0.052 | 0.000 | 2.34 | 3.07 | 4.25 | 61.51 | 1.22 | 1.09 |
| wl_airtel1 | s1 | ndd-apkeep | 200 of 200 | 0 | 0 | 3057 | 0.060 | 0.000 | 2.53 | 3.35 | 4.78 | 199.59 | 1.31 | 1.16 |
| wl_airtel1 | s2 | apkeep | 200 of 200 | 0 | 0 | 3259 | 0.064 | 0.000 | 2.88 | 8.54 | 45.64 | 82.5 | 1.34 | 1.72 |
| wl_airtel1 | s2 | ndd-apkeep | 200 of 200 | 0 | 0 | 3393 | 0.066 | 0.000 | 3.09 | 6.5 | 44.76 | 251.41 | 1.57 | 1.59 |
| wl_airtel1 | s3 | apkeep | 168 of 168 | 0 | 1804 | 10124 | 0.235 | 0.178 | 551.48 | 575.23 | 581.18 | 589.31 | 546.93 | 2.28 |
| wl_airtel1 | s3 | ndd-apkeep | 168 of 168 | 0 | 1804 | 10086 | 0.235 | 0.179 | 556.41 | 584.15 | 613.94 | 621.4 | 552.45 | 2.5 |
| wl_cloud | s1 | ndd-apkeep | 200 of 200 | 0 | 8 | 2280 | 0.161 | 0.004 | 49.82 | 68.85 | 108.56 | 206.38 | 17.68 | 28.95 |
| wl_cloud | s2 | ndd-apkeep | 200 of 200 | 0 | 15 | 3160 | 0.223 | 0.005 | 52.3 | 112.47 | 188.04 | 215.34 | 18.1 | 32.59 |
| wl_cloud | s3 | ndd-apkeep | 200 of 200 | 0 | 326 | 4540 | 0.320 | 0.072 | 72.78 | 163.59 | 209.16 | 227.4 | 18.3 | 53.26 |
| wl_example | s1 | apkeep | 44 of 44 | 6 | 14 | 114 | 0.259 | 0.123 | 0.49 | 6.87 | 64.35 | 64.35 | 0.43 | 0.03 |
| wl_example | s1 | ndd-apkeep | 44 of 44 | 6 | 14 | 114 | 0.259 | 0.123 | 0.48 | 5.6 | 69.35 | 69.35 | 0.39 | 0.02 |
| wl_example | s2 | apkeep | 8 of 8 | 0 | 4 | 47 | 0.588 | 0.085 | 7.91 | 9.85 | 32.63 | 32.63 | 4.76 | 3.14 |
| wl_example | s2 | ndd-apkeep | 8 of 8 | 0 | 4 | 48 | 0.600 | 0.083 | 7.13 | 8.3 | 25.76 | 25.76 | 4.58 | 2.48 |
| wl_example | s3 | apkeep | 20 of 20 | 0 | 48 | 112 | 0.560 | 0.429 | 5.74 | 7.87 | 26.22 | 26.22 | 4.15 | 1.6 |
| wl_example | s3 | ndd-apkeep | 20 of 20 | 0 | 48 | 116 | 0.580 | 0.414 | 6.66 | 21.76 | 32.69 | 32.69 | 4.27 | 1.97 |
| wl_ifi | s1 | apkeep | 200 of 200 | 0 | 81 | 1054 | 0.018 | 0.077 | 0.65 | 3.41 | 8.36 | 15.23 | 0.62 | 0.02 |
| wl_ifi | s1 | ndd-apkeep | 200 of 200 | 0 | 81 | 1147 | 0.019 | 0.071 | 0.67 | 3.22 | 14.44 | 20.83 | 0.65 | 0.02 |
| wl_ifi | s2 | apkeep | 56 of 56 | 0 | 126 | 2070 | 0.124 | 0.061 | 3.41 | 15.45 | 21.76 | 21.93 | 1.4 | 1.97 |
| wl_ifi | s2 | ndd-apkeep | 56 of 56 | 0 | 126 | 1392 | 0.083 | 0.091 | 3.03 | 14.13 | 33.02 | 39.27 | 1.38 | 1.37 |
| wl_ifi | s3 | apkeep | 132 of 132 | 0 | 606 | 5636 | 0.143 | 0.108 | 2.89 | 11.32 | 24.09 | 25.95 | 1.31 | 1.43 |
| wl_ifi | s3 | ndd-apkeep | 132 of 132 | 0 | 606 | 5772 | 0.146 | 0.105 | 2.75 | 13.47 | 26.47 | 35.65 | 1.33 | 1.29 |

| workload | stream | engines | agree | batches compared | disagreeing | refusals diverge at |
|---|---|---|---|---:|---:|---|
| wl_airtel1 | s1 | apkeep, ndd-apkeep | True | 200 | 0 | - |
| wl_airtel1 | s2 | apkeep, ndd-apkeep | True | 200 | 0 | - |
| wl_airtel1 | s3 | apkeep, ndd-apkeep | True | 168 | 0 | - |
| wl_example | s1 | apkeep, ndd-apkeep | True | 44 | 0 | - |
| wl_example | s2 | apkeep, ndd-apkeep | True | 8 | 0 | - |
| wl_example | s3 | apkeep, ndd-apkeep | True | 20 | 0 | - |
| wl_ifi | s1 | apkeep, ndd-apkeep | True | 200 | 0 | - |
| wl_ifi | s2 | apkeep, ndd-apkeep | True | 56 | 0 | - |
| wl_ifi | s3 | apkeep, ndd-apkeep | True | 132 | 0 | - |
