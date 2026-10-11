| workload | stream | mode | re-checked | vs coarse | verdicts = coarse | t_update med ms | t_recheck med ms | t_total med ms |
|---|---|---|---:|---:|---|---:|---:|---:|
| wl_example | s1 | coarse | 292 |  | True | 0.04 | 2.15 | 2.22 |
| wl_example | s1 | witness | 258 | -12% | True | 0.04 | 1.75 | 1.79 |
| wl_example | s1 | dead-ends | 126 | -57% | True | 0.08 | 0.01 | 0.19 |
| wl_example | s1 | witness+dead-ends | 112 | -62% | True | 0.08 | 0.01 | 0.19 |
| wl_example | s2 | coarse | 41 |  | True | 0.07 | 2.05 | 2.14 |
| wl_example | s2 | witness | 20 | -51% | True | 0.10 | 1.81 | 1.93 |
| wl_example | s2 | dead-ends | 30 | -27% | True | 0.10 | 1.85 | 1.95 |
| wl_example | s2 | witness+dead-ends | 14 | -66% | True | 0.09 | 0.86 | 1.02 |
| wl_example | s3 | coarse | 100 |  | True | 0.02 | 1.87 | 1.89 |
| wl_example | s3 | witness | 76 | -24% | True | 0.03 | 1.79 | 1.82 |
| wl_example | s3 | dead-ends | 92 | -8% | True | 0.03 | 1.78 | 1.81 |
| wl_example | s3 | witness+dead-ends | 72 | -28% | True | 0.03 | 1.75 | 1.79 |
| wl_ifi | s1 | coarse | 2670 |  | True | 0.03 | 0.02 | 0.07 |
| wl_ifi | s1 | witness | 2275 | -15% | True | 0.09 | 0.02 | 0.10 |
| wl_ifi | s1 | dead-ends | 1213 | -55% | True | 0.08 | 0.02 | 0.10 |
| wl_ifi | s1 | witness+dead-ends | 818 | -69% | True | 0.09 | 0.02 | 0.10 |
| wl_ifi | s2 | coarse | 2981 |  | True | 0.06 | 2.11 | 2.21 |
| wl_ifi | s2 | witness | 2234 | -25% | True | 0.21 | 2.36 | 2.56 |
| wl_ifi | s2 | dead-ends | 2187 | -27% | True | 0.19 | 2.29 | 2.48 |
| wl_ifi | s2 | witness+dead-ends | 1440 | -52% | True | 0.23 | 2.28 | 2.46 |
| wl_ifi | s3 | coarse | 5624 |  | True | 0.03 | 1.85 | 1.88 |
| wl_ifi | s3 | witness | 3856 | -31% | True | 0.10 | 1.82 | 1.83 |
| wl_ifi | s3 | dead-ends | 4217 | -25% | True | 0.08 | 1.81 | 1.83 |
| wl_ifi | s3 | witness+dead-ends | 2449 | -56% | True | 0.10 | 1.80 | 1.81 |
| wl_airtel1 | s1 | coarse | 51200 |  | True | 1.29 | 605.75 | 607.10 |
| wl_airtel1 | s1 | witness | 9200 | -82% | True | 1.30 | 604.27 | 605.56 |
| wl_airtel1 | s1 | dead-ends | 42000 | -18% | True | 1.37 | 595.63 | 596.98 |
| wl_airtel1 | s1 | witness+dead-ends | 0 | -100% | True | 0.91 | 0.01 | 0.92 |
| wl_airtel1 | s2 | coarse | 51200 |  | True | 1.25 | 599.71 | 600.95 |
| wl_airtel1 | s2 | witness | 9204 | -82% | True | 1.33 | 601.77 | 603.23 |
| wl_airtel1 | s2 | dead-ends | 42000 | -18% | True | 1.50 | 596.01 | 597.59 |
| wl_airtel1 | s2 | witness+dead-ends | 4 | -100% | True | 0.95 | 0.01 | 0.96 |
| wl_airtel1 | s3 | coarse | 34272 |  | True | 0.04 | 600.41 | 600.46 |
| wl_airtel1 | s3 | witness | 7962 | -77% | True | 0.12 | 605.17 | 605.30 |
| wl_airtel1 | s3 | dead-ends | 31239 | -9% | True | 0.13 | 603.99 | 604.11 |
| wl_airtel1 | s3 | witness+dead-ends | 4929 | -86% | True | 0.12 | 560.73 | 560.98 |
| wl_cloud | s1 | coarse | 13210 |  | True | 0.07 | 222.68 | 222.75 |
| wl_cloud | s1 | witness | 1860 | -86% | True | 0.19 | 89.67 | 89.85 |
| wl_cloud | s1 | dead-ends | 11360 | -14% | True | 0.27 | 152.31 | 152.62 |
| wl_cloud | s1 | witness+dead-ends | 10 | -100% | True | 0.11 | 0.01 | 0.12 |
| wl_cloud | s2 | coarse | 7083 |  | True | 0.12 | 129.57 | 129.65 |
| wl_cloud | s2 | witness | 1653 | -77% | True | 0.19 | 16.93 | 17.13 |
| wl_cloud | s2 | dead-ends | 5639 | -20% | True | 0.25 | 130.55 | 130.69 |
| wl_cloud | s2 | witness+dead-ends | 136 | -98% | True | 0.13 | 0.01 | 0.15 |
| wl_cloud | s3 | coarse | 7712 |  | True | 0.06 | 140.58 | 140.65 |
| wl_cloud | s3 | witness | 1662 | -78% | True | 0.09 | 89.33 | 89.42 |
| wl_cloud | s3 | dead-ends | 7315 | -5% | True | 0.09 | 140.77 | 140.86 |
| wl_cloud | s3 | witness+dead-ends | 1016 | -87% | True | 0.08 | 4.23 | 4.30 |

## Predictions

- P1 every mode changes the same verdicts as coarse on every update: **held**
- P2 the three oracle runs pass: **held** -- wl_ifi pass (56 records, 2 full checkpoints); wl_airtel1 pass (200 records, 4 full checkpoints); wl_cloud pass (200 records, 4 full checkpoints)
- P3 both <= coarse re-checks on every stream: **held**
- P4 wl_airtel1 S1/S2 both: re-checks <= 1%, median t_recheck <= 10% of coarse: **held** -- s1 re-checks 0.00%, t_recheck 0.0%; s2 re-checks 0.01%, t_recheck 0.0%
- P5 wl_ifi S1/S2 both: re-checks <= 40% of coarse: **FALSIFIED** -- s1 31%; s2 48%
- P6 wl_airtel1 S3 witness alone: >= 30% below coarse: **held** -- 77% below
- P7 both: median t_update <= 3x coarse on every stream: **FALSIFIED on [('wl_ifi', 's2', 3.67), ('wl_ifi', 's3', 3.02)]** -- worst wl_ifi s2 3.67x
- P8 wl_airtel1 S1/S2 both: median t_total below coarse: **held** -- s1 0.92 vs 607.10 ms; s2 0.96 vs 600.95 ms
- P9 wl_ifi S1 dead-ends alone: <= 70% of coarse: **held** -- 45%
