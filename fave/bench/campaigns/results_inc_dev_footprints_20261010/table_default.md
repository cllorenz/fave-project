| workload | stream | engine | completed | refused | changed | re-checked | selectivity | precision | t_total median | p90 | p99 | max | t_update med | t_recheck med |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wl_airtel1 | s1 | apkeep | 200 of 200 | 0 | 0 | 3306 | 0.065 | 0.000 | 2.54 | 3.18 | 5.11 | 66.41 | 1.23 | 1.27 |
| wl_airtel1 | s1 | ndd-apkeep | 200 of 200 | 0 | 0 | 3698 | 0.072 | 0.000 | 2.7 | 3.58 | 5.19 | 34.38 | 1.3 | 1.31 |
| wl_airtel1 | s2 | apkeep | 200 of 200 | 0 | 0 | 4166 | 0.081 | 0.000 | 3.59 | 12.39 | 44.53 | 87.74 | 1.32 | 1.94 |
| wl_airtel1 | s2 | ndd-apkeep | 200 of 200 | 0 | 0 | 4300 | 0.084 | 0.000 | 3.32 | 7.84 | 44.44 | 276.42 | 1.56 | 1.8 |
| wl_airtel1 | s3 | apkeep | 168 of 168 | 0 | 1804 | 10124 | 0.235 | 0.178 | 553.24 | 587.45 | 628.07 | 666.74 | 548.81 | 2.39 |
| wl_airtel1 | s3 | ndd-apkeep | 168 of 168 | 0 | 1804 | 10086 | 0.235 | 0.179 | 553.83 | 575.04 | 662.48 | 812.19 | 550.54 | 2.49 |
| wl_cloud | s1 | ndd-apkeep | 200 of 200 | 0 | 8 | 5330 | 0.375 | 0.002 | 94.75 | 119.59 | 135.83 | 202.47 | 17.91 | 76.12 |
| wl_cloud | s2 | ndd-apkeep | 200 of 200 | 0 | 15 | 5181 | 0.365 | 0.003 | 83.7 | 143.34 | 190.2 | 233.5 | 18.2 | 63.15 |
| wl_cloud | s3 | ndd-apkeep | 200 of 200 | 0 | 326 | 4540 | 0.320 | 0.072 | 75.03 | 159.53 | 196.42 | 211.74 | 18.05 | 57.02 |
| wl_example | s1 | apkeep | 44 of 44 | 6 | 14 | 166 | 0.377 | 0.084 | 1.04 | 3.25 | 66.09 | 66.09 | 0.43 | 0.56 |
| wl_example | s1 | ndd-apkeep | 44 of 44 | 6 | 14 | 166 | 0.377 | 0.084 | 1.23 | 12.7 | 78.93 | 78.93 | 0.41 | 0.49 |
| wl_example | s2 | apkeep | 8 of 8 | 0 | 4 | 53 | 0.662 | 0.075 | 6.85 | 8.75 | 20.19 | 20.19 | 4.56 | 2.31 |
| wl_example | s2 | ndd-apkeep | 8 of 8 | 0 | 4 | 54 | 0.675 | 0.074 | 7.75 | 9.19 | 28.3 | 28.3 | 4.65 | 2.77 |
| wl_example | s3 | apkeep | 20 of 20 | 0 | 48 | 112 | 0.560 | 0.429 | 5.89 | 7.47 | 20.96 | 20.96 | 4.21 | 1.58 |
| wl_example | s3 | ndd-apkeep | 20 of 20 | 0 | 48 | 116 | 0.580 | 0.414 | 6.51 | 21.95 | 26.31 | 26.31 | 4.18 | 2.07 |
| wl_ifi | s1 | apkeep | 200 of 200 | 0 | 81 | 1864 | 0.031 | 0.043 | 0.65 | 3.97 | 18.2 | 32.76 | 0.63 | 0.02 |
| wl_ifi | s1 | ndd-apkeep | 200 of 200 | 0 | 81 | 2254 | 0.038 | 0.036 | 0.67 | 5.05 | 13.85 | 42.36 | 0.65 | 0.02 |
| wl_ifi | s2 | apkeep | 56 of 56 | 0 | 126 | 2662 | 0.159 | 0.047 | 4.8 | 14.74 | 20.49 | 21.37 | 1.5 | 3.16 |
| wl_ifi | s2 | ndd-apkeep | 56 of 56 | 0 | 126 | 1648 | 0.098 | 0.076 | 3.81 | 12.52 | 21.77 | 65.83 | 1.39 | 2.37 |
| wl_ifi | s3 | apkeep | 132 of 132 | 0 | 606 | 5636 | 0.143 | 0.108 | 2.89 | 13.26 | 24.5 | 35.27 | 1.31 | 1.36 |
| wl_ifi | s3 | ndd-apkeep | 132 of 132 | 0 | 606 | 5772 | 0.146 | 0.105 | 2.7 | 13.0 | 31.01 | 32.01 | 1.34 | 1.28 |

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
