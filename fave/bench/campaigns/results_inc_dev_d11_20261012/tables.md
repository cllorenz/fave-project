# D11 A cells: median ms per update (share of the stream done)

Made by analyze.py from cells/. `-`: no cell. `hollow`: every operation refused. Outcome marks: `cap` stopped by the wall cap, `mem` by the memory limit, `ERR` error.

## s1

| workload | netplumber | veriflow | apkeep | ndd-apkeep |
|---|---:|---:|---:|---:|
| wl_example | 0.026 (100%) | 2.25 (100%) | 0.491 (100%) | 0.567 (100%) |
| wl_ifi | 0.036 (100%) | 0.071 (100%) | 0.688 (100%) | 0.641 (100%) |
| wl_airtel1 | 0.08 (100%) | 470 (20%) cap | 1.32 (100%) | 1.68 (100%) |
| wl_airtel2 | 0.08 (100%) | 478 (20%) cap | 1.31 (100%) | 1.61 (100%) |
| wl_cloud | 0.019 (100%) | 145 (100%) | 686 (100%) | 12.7 (100%) |
| wl_up | 0.687 (100%) | 193 (3%) cap | 125 (65%) cap | 120 (86%) cap |
| wl_stanford | 0.058 (100%) | 2.03e+05 (0%) cap | - | 121 (12%) mem |
| wl_i2 | 0.589 (100%) | 1.25e+05 (0%) cap | - | 1.62e+03 (3%) cap |
| wl_tum | 0.089 (100%) | hollow | hollow | hollow |

## s2

| workload | netplumber | veriflow | apkeep | ndd-apkeep |
|---|---:|---:|---:|---:|
| wl_example | 0.643 (100%) | 2.17 (100%) | 7.68 (100%) | 6.84 (100%) |
| wl_ifi | 0.467 (100%) | 2.51 (100%) | 4.12 (100%) | 2.83 (100%) |
| wl_airtel1 | 0.417 (100%) | 517 (90%) cap | 7.36 (100%) | 7.41 (100%) |
| wl_airtel2 | 0.417 (100%) | 501 (92%) cap | 7.61 (100%) | 7.48 (100%) |
| wl_cloud | 0.029 (100%) | 63.4 (100%) | 1.08e+04 (100%) | 17.6 (100%) |
| wl_up | 2.04 (100%) | 1.05e+03 (10%) cap | 176 (4%) cap | 150 (19%) cap |
| wl_stanford | 5.86 (9%) mem | 1.81e+05 (2%) cap | - | 143 (8%) mem |
| wl_i2 | 5.55 (100%) | 1.21e+05 (0%) cap | - | 1.66e+03 (13%) cap |
| wl_tum | 14.2 (100%) | hollow | hollow | hollow |

## s3

| workload | netplumber | veriflow | apkeep | ndd-apkeep |
|---|---:|---:|---:|---:|
| wl_example | 0.747 (100%) | 1.8 (100%) | 6.26 (100%) | 7.24 (100%) |
| wl_ifi | 0.545 (100%) | 1.85 (100%) | 2.86 (100%) | 2.78 (100%) |
| wl_airtel1 | 2.76 (100%) | 632 (100%) | 563 (100%) | 560 (100%) |
| wl_airtel2 | 2.62 (100%) | 608 (100%) | 568 (100%) | 565 (100%) |
| wl_cloud | 0.114 (100%) | 134 (100%) | 195 (100%) | 39.9 (100%) |
| wl_up | 5.04 (100%) | 1.68e+05 (4%) cap | 1.31e+05 (5%) cap | 5.22e+04 (18%) cap |
| wl_stanford | 0.025 (100%) | 2.03e+05 (1%) cap | - | 155 (3%) mem |
| wl_i2 | 1.86 (100%) | 1.25e+05 (12%) cap | - | 1.76e+03 (100%) |
| wl_tum | 16.7 (100%) | hollow | hollow | hollow |
