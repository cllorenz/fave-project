| workload | engine | stream | mode | re-checked | vs default | verdicts = default | t_recheck median ms | t_total median ms |
|---|---|---|---|---:|---:|---|---:|---:|
| wl_example | apkeep | s1 | default | 166 |  | True | 0.56 | 1.04 |
| wl_example | apkeep | s1 | witness | 154 | -7% | True | 1.07 | 1.37 |
| wl_example | apkeep | s1 | dead-ends | 114 | -31% | True | 0.03 | 0.49 |
| wl_example | apkeep | s1 | witness+dead-ends | 102 | -39% | True | 0.03 | 0.48 |
| wl_example | apkeep | s2 | default | 53 |  | True | 2.31 | 6.85 |
| wl_example | apkeep | s2 | witness | 34 | -36% | True | 1.57 | 5.95 |
| wl_example | apkeep | s2 | dead-ends | 47 | -11% | True | 3.14 | 7.91 |
| wl_example | apkeep | s2 | witness+dead-ends | 26 | -51% | True | 1.74 | 6.25 |
| wl_example | apkeep | s3 | default | 112 |  | True | 1.58 | 5.89 |
| wl_example | apkeep | s3 | witness | 104 | -7% | True | 1.46 | 5.66 |
| wl_example | apkeep | s3 | dead-ends | 112 | +0% | True | 1.60 | 5.74 |
| wl_example | apkeep | s3 | witness+dead-ends | 104 | -7% | True | 1.63 | 5.84 |
| wl_example | ndd-apkeep | s1 | default | 166 |  | True | 0.49 | 1.23 |
| wl_example | ndd-apkeep | s1 | witness | 154 | -7% | True | 1.06 | 1.36 |
| wl_example | ndd-apkeep | s1 | dead-ends | 114 | -31% | True | 0.02 | 0.48 |
| wl_example | ndd-apkeep | s1 | witness+dead-ends | 102 | -39% | True | 0.04 | 0.59 |
| wl_example | ndd-apkeep | s2 | default | 54 |  | True | 2.77 | 7.75 |
| wl_example | ndd-apkeep | s2 | witness | 34 | -37% | True | 2.01 | 6.97 |
| wl_example | ndd-apkeep | s2 | dead-ends | 48 | -11% | True | 2.48 | 7.13 |
| wl_example | ndd-apkeep | s2 | witness+dead-ends | 26 | -52% | True | 2.14 | 6.62 |
| wl_example | ndd-apkeep | s3 | default | 116 |  | True | 2.07 | 6.51 |
| wl_example | ndd-apkeep | s3 | witness | 104 | -10% | True | 1.48 | 5.83 |
| wl_example | ndd-apkeep | s3 | dead-ends | 116 | +0% | True | 1.97 | 6.66 |
| wl_example | ndd-apkeep | s3 | witness+dead-ends | 104 | -10% | True | 1.68 | 5.95 |
| wl_ifi | apkeep | s1 | default | 1864 |  | True | 0.02 | 0.65 |
| wl_ifi | apkeep | s1 | witness | 1745 | -6% | True | 0.02 | 0.66 |
| wl_ifi | apkeep | s1 | dead-ends | 1054 | -43% | True | 0.02 | 0.65 |
| wl_ifi | apkeep | s1 | witness+dead-ends | 935 | -50% | True | 0.02 | 0.65 |
| wl_ifi | apkeep | s2 | default | 2662 |  | True | 3.16 | 4.80 |
| wl_ifi | apkeep | s2 | witness | 2181 | -18% | True | 3.26 | 4.68 |
| wl_ifi | apkeep | s2 | dead-ends | 2070 | -22% | True | 1.97 | 3.41 |
| wl_ifi | apkeep | s2 | witness+dead-ends | 1589 | -40% | True | 1.43 | 3.29 |
| wl_ifi | apkeep | s3 | default | 5636 |  | True | 1.36 | 2.89 |
| wl_ifi | apkeep | s3 | witness | 4700 | -17% | True | 1.27 | 2.66 |
| wl_ifi | apkeep | s3 | dead-ends | 5636 | +0% | True | 1.43 | 2.89 |
| wl_ifi | apkeep | s3 | witness+dead-ends | 4700 | -17% | True | 1.47 | 2.93 |
| wl_ifi | ndd-apkeep | s1 | default | 2254 |  | True | 0.02 | 0.67 |
| wl_ifi | ndd-apkeep | s1 | witness | 2042 | -9% | True | 0.02 | 0.65 |
| wl_ifi | ndd-apkeep | s1 | dead-ends | 1147 | -49% | True | 0.02 | 0.67 |
| wl_ifi | ndd-apkeep | s1 | witness+dead-ends | 935 | -59% | True | 0.02 | 0.66 |
| wl_ifi | ndd-apkeep | s2 | default | 1648 |  | True | 2.37 | 3.81 |
| wl_ifi | ndd-apkeep | s2 | witness | 1377 | -16% | True | 2.35 | 3.72 |
| wl_ifi | ndd-apkeep | s2 | dead-ends | 1392 | -16% | True | 1.37 | 3.03 |
| wl_ifi | ndd-apkeep | s2 | witness+dead-ends | 1121 | -32% | True | 1.37 | 2.79 |
| wl_ifi | ndd-apkeep | s3 | default | 5772 |  | True | 1.28 | 2.70 |
| wl_ifi | ndd-apkeep | s3 | witness | 4700 | -19% | True | 1.28 | 2.81 |
| wl_ifi | ndd-apkeep | s3 | dead-ends | 5772 | +0% | True | 1.29 | 2.75 |
| wl_ifi | ndd-apkeep | s3 | witness+dead-ends | 4700 | -19% | True | 1.30 | 2.77 |
| wl_airtel1 | apkeep | s1 | default | 3306 |  | True | 1.27 | 2.54 |
| wl_airtel1 | apkeep | s1 | witness | 641 | -81% | True | 0.75 | 1.97 |
| wl_airtel1 | apkeep | s1 | dead-ends | 2665 | -19% | True | 1.09 | 2.34 |
| wl_airtel1 | apkeep | s1 | witness+dead-ends | 0 | -100% | True | 0.03 | 1.17 |
| wl_airtel1 | apkeep | s2 | default | 4166 |  | True | 1.94 | 3.59 |
| wl_airtel1 | apkeep | s2 | witness | 911 | -78% | True | 1.19 | 2.48 |
| wl_airtel1 | apkeep | s2 | dead-ends | 3259 | -22% | True | 1.72 | 2.88 |
| wl_airtel1 | apkeep | s2 | witness+dead-ends | 4 | -100% | True | 0.05 | 1.27 |
| wl_airtel1 | apkeep | s3 | default | 10124 |  | True | 2.39 | 553.24 |
| wl_airtel1 | apkeep | s3 | witness | 4564 | -55% | True | 2.03 | 558.09 |
| wl_airtel1 | apkeep | s3 | dead-ends | 10124 | +0% | True | 2.28 | 551.48 |
| wl_airtel1 | apkeep | s3 | witness+dead-ends | 4564 | -55% | True | 2.20 | 549.07 |
| wl_airtel1 | ndd-apkeep | s1 | default | 3698 |  | True | 1.31 | 2.70 |
| wl_airtel1 | ndd-apkeep | s1 | witness | 641 | -83% | True | 0.83 | 2.22 |
| wl_airtel1 | ndd-apkeep | s1 | dead-ends | 3057 | -17% | True | 1.16 | 2.53 |
| wl_airtel1 | ndd-apkeep | s1 | witness+dead-ends | 0 | -100% | True | 0.03 | 1.25 |
| wl_airtel1 | ndd-apkeep | s2 | default | 4300 |  | True | 1.80 | 3.32 |
| wl_airtel1 | ndd-apkeep | s2 | witness | 911 | -79% | True | 1.23 | 2.70 |
| wl_airtel1 | ndd-apkeep | s2 | dead-ends | 3393 | -21% | True | 1.59 | 3.09 |
| wl_airtel1 | ndd-apkeep | s2 | witness+dead-ends | 4 | -100% | True | 0.05 | 1.48 |
| wl_airtel1 | ndd-apkeep | s3 | default | 10086 |  | True | 2.49 | 553.83 |
| wl_airtel1 | ndd-apkeep | s3 | witness | 4564 | -55% | True | 2.15 | 555.53 |
| wl_airtel1 | ndd-apkeep | s3 | dead-ends | 10086 | +0% | True | 2.50 | 556.41 |
| wl_airtel1 | ndd-apkeep | s3 | witness+dead-ends | 4564 | -55% | True | 2.21 | 555.68 |
| wl_cloud | ndd-apkeep | s1 | default | 5330 |  | True | 76.12 | 94.75 |
| wl_cloud | ndd-apkeep | s1 | witness | 3081 | -42% | True | 41.29 | 62.07 |
| wl_cloud | ndd-apkeep | s1 | dead-ends | 2280 | -57% | True | 28.95 | 49.82 |
| wl_cloud | ndd-apkeep | s1 | witness+dead-ends | 10 | -100% | True | 0.04 | 17.41 |
| wl_cloud | ndd-apkeep | s2 | default | 5181 |  | True | 63.15 | 83.70 |
| wl_cloud | ndd-apkeep | s2 | witness | 2748 | -47% | True | 39.64 | 61.70 |
| wl_cloud | ndd-apkeep | s2 | dead-ends | 3160 | -39% | True | 32.59 | 52.30 |
| wl_cloud | ndd-apkeep | s2 | witness+dead-ends | 466 | -91% | True | 0.04 | 17.85 |
| wl_cloud | ndd-apkeep | s3 | default | 4540 |  | True | 57.02 | 75.03 |
| wl_cloud | ndd-apkeep | s3 | witness | 1866 | -59% | True | 30.79 | 48.95 |
| wl_cloud | ndd-apkeep | s3 | dead-ends | 4540 | +0% | True | 53.26 | 72.78 |
| wl_cloud | ndd-apkeep | s3 | witness+dead-ends | 1866 | -59% | True | 25.81 | 47.16 |

P1 verdicts equal everywhere: True
P3 witness+dead-ends <= default everywhere: True []
P4 wl_cloud witness cut S1 42%, S2 47% (>= 25% each)
P5 wl_airtel1 S3 witness cut: apkeep 55%, ndd-apkeep 55% (>= 30% each)
P6 wl_ifi S2 dead-ends cut: apkeep 22%, ndd-apkeep 16% (>= 20% each)
P7 largest t_recheck median ratio vs default: 2.15 at ('wl_example', 'ndd-apkeep', 's1', 'witness') (<= 1.5)
