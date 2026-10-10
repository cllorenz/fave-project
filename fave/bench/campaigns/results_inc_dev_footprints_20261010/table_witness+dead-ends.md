| workload | stream | engine | completed | refused | changed | re-checked | selectivity | precision | t_total median | p90 | p99 | max | t_update med | t_recheck med |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| wl_airtel1 | s1 | apkeep | 200 of 200 | 0 | 0 | 0 | 0.000 | - | 1.17 | 1.24 | 1.88 | 29.38 | 1.14 | 0.03 |
| wl_airtel1 | s1 | ndd-apkeep | 200 of 200 | 0 | 0 | 0 | 0.000 | - | 1.25 | 1.37 | 6.35 | 30.5 | 1.21 | 0.03 |
| wl_airtel1 | s2 | apkeep | 200 of 200 | 0 | 0 | 4 | 0.000 | 0.000 | 1.27 | 2.0 | 36.34 | 42.1 | 1.2 | 0.05 |
| wl_airtel1 | s2 | ndd-apkeep | 200 of 200 | 0 | 0 | 4 | 0.000 | 0.000 | 1.48 | 2.23 | 37.86 | 45.29 | 1.41 | 0.05 |
| wl_airtel1 | s3 | apkeep | 168 of 168 | 0 | 1804 | 4564 | 0.106 | 0.395 | 549.07 | 576.25 | 597.05 | 636.71 | 546.3 | 2.2 |
| wl_airtel1 | s3 | ndd-apkeep | 168 of 168 | 0 | 1804 | 4564 | 0.106 | 0.395 | 555.68 | 601.83 | 634.99 | 671.56 | 552.2 | 2.21 |
| wl_cloud | s1 | ndd-apkeep | 200 of 200 | 0 | 8 | 10 | 0.001 | 0.800 | 17.41 | 22.74 | 27.35 | 67.24 | 17.38 | 0.04 |
| wl_cloud | s2 | ndd-apkeep | 200 of 200 | 0 | 15 | 466 | 0.033 | 0.032 | 17.85 | 36.17 | 117.3 | 167.32 | 17.8 | 0.04 |
| wl_cloud | s3 | ndd-apkeep | 200 of 200 | 0 | 326 | 1866 | 0.131 | 0.175 | 47.16 | 84.81 | 132.69 | 163.11 | 18.11 | 25.81 |
| wl_example | s1 | apkeep | 44 of 44 | 6 | 14 | 102 | 0.232 | 0.137 | 0.48 | 2.48 | 69.44 | 69.44 | 0.42 | 0.03 |
| wl_example | s1 | ndd-apkeep | 44 of 44 | 6 | 14 | 102 | 0.232 | 0.137 | 0.59 | 12.78 | 68.16 | 68.16 | 0.43 | 0.04 |
| wl_example | s2 | apkeep | 8 of 8 | 0 | 4 | 26 | 0.325 | 0.154 | 6.25 | 7.5 | 30.36 | 30.36 | 4.49 | 1.74 |
| wl_example | s2 | ndd-apkeep | 8 of 8 | 0 | 4 | 26 | 0.325 | 0.154 | 6.62 | 7.55 | 21.91 | 21.91 | 4.56 | 2.14 |
| wl_example | s3 | apkeep | 20 of 20 | 0 | 48 | 104 | 0.520 | 0.462 | 5.84 | 7.17 | 27.32 | 27.32 | 4.19 | 1.63 |
| wl_example | s3 | ndd-apkeep | 20 of 20 | 0 | 48 | 104 | 0.520 | 0.462 | 5.95 | 7.35 | 25.79 | 25.79 | 4.22 | 1.68 |
| wl_ifi | s1 | apkeep | 200 of 200 | 0 | 81 | 935 | 0.016 | 0.087 | 0.65 | 2.95 | 11.66 | 23.34 | 0.63 | 0.02 |
| wl_ifi | s1 | ndd-apkeep | 200 of 200 | 0 | 81 | 935 | 0.016 | 0.087 | 0.66 | 2.48 | 12.82 | 23.09 | 0.64 | 0.02 |
| wl_ifi | s2 | apkeep | 56 of 56 | 0 | 126 | 1589 | 0.095 | 0.079 | 3.29 | 9.9 | 22.87 | 25.7 | 1.4 | 1.43 |
| wl_ifi | s2 | ndd-apkeep | 56 of 56 | 0 | 126 | 1121 | 0.067 | 0.112 | 2.79 | 13.75 | 39.79 | 57.12 | 1.36 | 1.37 |
| wl_ifi | s3 | apkeep | 132 of 132 | 0 | 606 | 4700 | 0.119 | 0.129 | 2.93 | 11.79 | 23.86 | 23.92 | 1.33 | 1.47 |
| wl_ifi | s3 | ndd-apkeep | 132 of 132 | 0 | 606 | 4700 | 0.119 | 0.129 | 2.77 | 11.38 | 28.99 | 61.09 | 1.32 | 1.3 |

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
