| workload | stream | engine | completed | refused | changed | re-checked | selectivity | precision | t_total median | p90 | p99 | max | t_update med | t_recheck med |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wl_airtel1 | s1 | apkeep | 200 of 200 | 0 | 0 | 641 | 0.013 | 0.000 | 1.97 | 2.56 | 3.76 | 64.86 | 1.2 | 0.75 |
| wl_airtel1 | s1 | ndd-apkeep | 200 of 200 | 0 | 0 | 641 | 0.013 | 0.000 | 2.22 | 2.87 | 4.12 | 30.08 | 1.3 | 0.83 |
| wl_airtel1 | s2 | apkeep | 200 of 200 | 0 | 0 | 911 | 0.018 | 0.000 | 2.48 | 5.28 | 44.29 | 72.9 | 1.33 | 1.19 |
| wl_airtel1 | s2 | ndd-apkeep | 200 of 200 | 0 | 0 | 911 | 0.018 | 0.000 | 2.7 | 5.32 | 37.06 | 44.27 | 1.52 | 1.23 |
| wl_airtel1 | s3 | apkeep | 168 of 168 | 0 | 1804 | 4564 | 0.106 | 0.395 | 558.09 | 584.17 | 597.03 | 603.51 | 555.45 | 2.03 |
| wl_airtel1 | s3 | ndd-apkeep | 168 of 168 | 0 | 1804 | 4564 | 0.106 | 0.395 | 555.53 | 575.2 | 584.0 | 586.97 | 552.0 | 2.15 |
| wl_cloud | s1 | ndd-apkeep | 200 of 200 | 0 | 8 | 3081 | 0.217 | 0.003 | 62.07 | 85.83 | 116.37 | 203.84 | 17.9 | 41.29 |
| wl_cloud | s2 | ndd-apkeep | 200 of 200 | 0 | 15 | 2748 | 0.194 | 0.005 | 61.7 | 100.94 | 129.16 | 240.74 | 18.26 | 39.64 |
| wl_cloud | s3 | ndd-apkeep | 200 of 200 | 0 | 326 | 1866 | 0.131 | 0.175 | 48.95 | 72.16 | 109.69 | 120.81 | 17.96 | 30.79 |
| wl_example | s1 | apkeep | 44 of 44 | 6 | 14 | 154 | 0.350 | 0.091 | 1.37 | 4.62 | 55.97 | 55.97 | 0.42 | 1.07 |
| wl_example | s1 | ndd-apkeep | 44 of 44 | 6 | 14 | 154 | 0.350 | 0.091 | 1.36 | 4.4 | 72.97 | 72.97 | 0.46 | 1.06 |
| wl_example | s2 | apkeep | 8 of 8 | 0 | 4 | 34 | 0.425 | 0.118 | 5.95 | 7.66 | 24.17 | 24.17 | 4.42 | 1.57 |
| wl_example | s2 | ndd-apkeep | 8 of 8 | 0 | 4 | 34 | 0.425 | 0.118 | 6.97 | 7.72 | 22.89 | 22.89 | 4.74 | 2.01 |
| wl_example | s3 | apkeep | 20 of 20 | 0 | 48 | 104 | 0.520 | 0.462 | 5.66 | 7.01 | 22.04 | 22.04 | 4.19 | 1.46 |
| wl_example | s3 | ndd-apkeep | 20 of 20 | 0 | 48 | 104 | 0.520 | 0.462 | 5.83 | 7.5 | 23.16 | 23.16 | 4.16 | 1.48 |
| wl_ifi | s1 | apkeep | 200 of 200 | 0 | 81 | 1745 | 0.029 | 0.046 | 0.66 | 3.67 | 10.95 | 44.15 | 0.64 | 0.02 |
| wl_ifi | s1 | ndd-apkeep | 200 of 200 | 0 | 81 | 2042 | 0.034 | 0.040 | 0.65 | 6.8 | 16.58 | 34.73 | 0.63 | 0.02 |
| wl_ifi | s2 | apkeep | 56 of 56 | 0 | 126 | 2181 | 0.130 | 0.058 | 4.68 | 11.04 | 15.74 | 22.88 | 1.44 | 3.26 |
| wl_ifi | s2 | ndd-apkeep | 56 of 56 | 0 | 126 | 1377 | 0.082 | 0.092 | 3.72 | 14.73 | 26.97 | 28.92 | 1.36 | 2.35 |
| wl_ifi | s3 | apkeep | 132 of 132 | 0 | 606 | 4700 | 0.119 | 0.129 | 2.66 | 10.64 | 17.51 | 25.65 | 1.27 | 1.27 |
| wl_ifi | s3 | ndd-apkeep | 132 of 132 | 0 | 606 | 4700 | 0.119 | 0.129 | 2.81 | 11.38 | 29.95 | 42.21 | 1.35 | 1.28 |

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
