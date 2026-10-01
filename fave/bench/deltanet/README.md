# The Delta-net dataset family

Tier 2 of three (`CLOUD_BENCH_PLAN.md` §2.2, D6). Everything here is shared by
the workloads built from the NSDI'17 Delta-net distribution and owned by none of
them.

| tier | what it holds |
|---|---|
| `bench/` | cross-workload harness — `generic_benchmark.py`, the shared `np.conf`, the input stamp |
| **`bench/deltanet/`** | **this: the dataset family — how to read a trace, and what a model derived from one looks like** |
| `bench/wl_<trace>/` | one workload: a ~15-line driver, and the artifacts generated from it |

## Why the middle tier exists

The raw data forces it. One `SHA256SUMS` under `traces/` covers both CSVs and
every workload reads it through `util/raw_data.verify_raw`. Giving each workload
its own copy would duplicate the pin, and **a guard that exists twice is a guard
that can disagree with itself** — which is the failure `util/raw_data.py` was
written to prevent in the first place.

The rest follows the same rule. `TRACES.md` compares *both* traces, so it cannot
belong to either workload. `topology.py`, `preparation.py` and `policy.py`
mention no trace at all — they are pure functions of a parsed insert list, and
were already so while they sat in a workload directory.

What that directory layout costs when it is not done is visible elsewhere in
`bench/`: `np.conf` exists in twelve copies with five distinct contents, and
`tf_to_json.py` has drifted between `wl_i2` and `wl_stanford`, the Stanford copy
having grown port-offset logic the i2 copy never learned. Neither divergence was
chosen.

## `deltanet` is the distribution, not a network

The archive holds eleven CSVs spanning `inet`, `rf3257`, `rf6461` and
`berkley-ribs-*` as well as the two Airtel traces, so `deltanet` names where the
data came from. The workloads are named after their traces instead.

**And `airtel1` and `airtel2` are ONE network, not two.** Both are AS 9498
(Airtel), sixteen Open vSwitches under ONOS and SDN-IP with Quagga border
routers, and they differ by *failure regime*: Airtel 1 fails a single
inter-switch link at a time and recovers it before the next, Airtel 2 induces
all 2-pair link failures including their recovery. A directory name in a
position where every sibling means a network therefore reads slightly wrong.

It is used anyway, because **`Airtel 1` and `Airtel 2` are the paper's own
names** for the data sets (Table 2), and matching the source's vocabulary beats
inventing a more accurate word that nothing else uses. This paragraph is the
correction; `traces/README.md` has the provenance.

## What is derived, and what is not

Everything except `traces/` is derived, and `traces/README.md` states only what
the data cannot state about itself — scope and provenance. Three figures once
written there by hand were all wrong, which is why `TRACES.md` is generated:

    python3 -m bench.deltanet.census      # from fave/

`test/test_deltanet_census.py` pins it byte for byte, so editing it by hand is a
test failure and a change to it is a change in how the traces are read.

## The modules

| file | what it refuses to guess |
|---|---|
| `trace.py` | the CSV format; D1's `priority = 5*plen + 100`, asserted per row; a withdrawal in an `only-inserts` file |
| `topology.py` | the switch/port graph behind the `s<i>-<j>` names — one link per pair, injective neighbour-to-port, symmetry, ports `1..degree+1`, no U-turn |
| `preparation.py` | the FaVe device model, longest-prefix-first |
| `policy.py` | the FPL inventory and the reachability matrix (§2.5) |
| `census.py` | `TRACES.md` |
| `routers.py` | the port-free reading (`wl_berkeley`): bare router names, one INVENTED port per neighbour, symmetric adjacency (§2.15) |
| `fib_walk.py` | a reference walk of a model's rules, per address region; states `wl_berkeley`'s matrix, validated on airtel's |
| `sample.py` | `keep_every=k`: 1/k of the prefixes plus every LPM witness, for size series |
| `registry.py` | `WORKLOADS` (vendored traces; `test.sh` loops over it) and `DERIVED` (`wl_berkeley`; built only by name) |
| `eval/` | engine runs, series and their results; `eval/README.md` |
