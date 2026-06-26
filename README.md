# FaVe - Fast Formal Network Security Verification

This repository contains the codebases of the FaVe project.
FaVe aims to offer accessible and scalable tooling to support network security management processes.
It enables to verify the security compliance of network configurations and provides further insights into firewall rule sets, i.e., by detecting firewall anomalies.
The concept behind FaVe is called _Domain oriented Header Space Analysis_ (DHSA).
In contrast to the original _Header Space Analysis_ by Kazemian et al. (refer to [1]), DHSA offers more accessible yet compatible means to specify policies and model network configuration.
Nevertheless, we reuse the fast _NetPlumber_ (originally by Kazemian et al.) verification engine to solve DHSA instances.

We benchmarked DHSA using several different workloads - synthetic and real-world alike - covering a broad variety of scenarios.
Also, we compared our results with the state of the art by running the benchmark with the tools from [2], [3], [4], and [5].
See our publication list for the results.


## Publications

We published our results in a series of scientific papers:

 - C. Lorenz and B. Schnor, “Policy Anomaly Detection for Distributed IPv6 Firewalls,” in SECRYPT, 2015, [DOI: 10.5220/0005517402100219](https://doi.org/10.5220/0005517402100219).
 - C. Lorenz, S. Kiekheben, and B. Schnor, “FaVe: Modeling IPv6 firewalls for fast formal verification,” in NetSys, 2017, [DOI: 10.1109/NETSYS.2017.7903956](https://doi.org/10.1109/NETSYS.2017.7903956).
 - C. Lorenz, V. Clemens, M. Schrötter, and B. Schnor, “Continuous Verification of Network Security Compliance,” in IEEE TNSM, 2021, [DOI: 10.1109/TNSM.2021.3130290](https://doi.org/10.1109/TNSM.2021.3130290).
 - C. Lorenz and B. Schnor, “Firewall Management: Rapid Anomaly Detection,“ in HPCC, 2022, [DOI: 10.1109/HPCC-DSS-SmartCity-DependSys57074.2022.00226](https://doi.org/10.1109/HPCC-DSS-SmartCity-DependSys57074.2022.00226).


## Repository Overview

This repository is organized as follows:

 - `fave/` - includes the modeling pipeline and a set of management tools
 - `net_plumber/` - includes the NetPlumber verification backend which was published originally in [1]
 - `policy_translator/` - includes the policy management tool [PolicyTranslator](policy_translator/README.md)
 - `ad6` - includes ad6 for anomaly detection in ip6tables rule sets
 - `z3-anomalies` - includes an implementation of [4] to detect anomalies in ip6tables rule sets using the Z3 SMT solver
 - `stl-anomalies` - includes an implementation of [5] to detect anomalies in ip6tables rule sets using the STL algorithm
 - `np_reproduction` - includes scripts to reproduce the original HSA benchmark results from [1]


## First Steps (tested on Ubuntu 24.04)

First, one needs to install some dependencies to compile NetPlumber.
The script

    #> net_plumber/setup-ubuntu.sh

performs the necessary steps on an Ubuntu machine.
Afterwards, one needs to switch to

    $> cd net_plumber/build/

and then compile NetPlumber using

    $> make all

Then, one can use NetPlumber from the compilation directory or

    #> make install

to install it permanently.

For developers it might be more convenient to link the `net_plumber` binary to some `$PATH` directory like `/usr/bin`.


To set up FaVe one can use the script

    #> fave/setup.sh

Afterwards, one can test the installation running

    $> cd fave
    $> export PYTHONPATH=.
    $> source ~/.venv/bin/activate
    $> bash examples/example.sh

Typically, a session comprises of two processes: `aggregator_service.py` and `net_plumber`.
These can be stopped or started using their respective scripts in `fave/scripts`.
If one process dies one needs to restart both - first NetPlumber and then FaVe.
Logfiles are stored in `/dev/shm/np`.


## Testing

Tests are run through a single entry point, `test.sh`, organized into tiers by
dependency footprint. The same command is used locally and by CI — CI only
selects a tier, it never defines its own tests.

    $> ./test.sh fast          # pure-Python unit tests, no native deps (<1s)
    $> ./test.sh integration   # NetPlumber C++ tests + bison-dependent FaVe tests (no live backend)
    $> ./test.sh e2e           # live-backend tests: test_rpc + smoke
    $> ./test.sh smoke         # just the smoke subset of e2e: example.sh + wl_example + wl_ifi
    $> ./test.sh bench         # large benchmarks (wl_up/wl_tum/wl_stanford/wl_i2)
    $> ./test.sh all           # fast + integration + e2e (excludes bench)

Tiers are split by dependency footprint. `fast` is pure Python. `integration`
needs the build + `pybison` but **no running backend**, so it is deterministic
and suitable to gate merges. `e2e` additionally needs a live `net_plumber`
process and `/dev/shm` state (process orchestration), so it is non-gating.
`bench` runs the large benchmarks (CI / nightly only).

The `fast` tier needs only the pure-Python dependencies and is meant to run on
every change before pushing:

    $> python3 -m venv .venv
    $> . .venv/bin/activate
    $> pip install -r requirements.txt
    $> ./test.sh fast

The heavier tiers need the full native stack (compiled NetPlumber, `pybison`),
as installed by `net_plumber/setup-ubuntu.sh` + `fave/setup.sh` or provided by
the `Dockerfile`. Set `COVERAGE=1` to additionally print a coverage report
(`COVERAGE=1 ./test.sh fast`). Additionally setting `COVERAGE_MIN=<pct>` gates
on coverage (`coverage report --fail-under`): the tier fails if total coverage
drops below the floor. CI runs the `fast` tier this way as a ratchet — bump the
floor up as coverage rises, never down.

Alongside the test tiers there is a static type-checking gate that runs `mypy`
over the typed modules and fails on any type error (`mypy` ships in
`requirements.txt`, so the `fast`-tier venv already has it):

    $> bash fave/test/typecheck_test.sh

Like the `fast` tier it is pure-Python (mypy analyses statically, so no native
stack is needed). `fave` and `PolicyTranslator` are independent tools and are
checked independently — each with its own `mypy.ini` and source root — and the
gate fails if either does. Which modules are checked is governed by the
per-module sections in the respective `mypy.ini`, so typing a new module is a
matter of adding its section. In CI this runs as a gating `typecheck` job.


## Benchmarks

There exist some benchmarks showing the capabilities of FaVe:

 - `fave/bench/wl_example` - A simple example workload.
 - `fave/bench/wl_ifi/` - Implementation of the small IFI benchmark which is a reasonably complex yet still manually explorable network configuration.
 - `fave/bench/wl_up/` - Implementation of the synthetic, mid-sized, and complex UP benchmark which mimics a university campus network.
 - `fave/bench/wl_tum/` - Implementation of the complex TUM-i8 benchmark from literature including a large firewall ruleset.
 - `fave/bench/wl_stanford/` - Implementation of the large Stanford benchmark from literature including ACLs.
 - `fave/bench/wl_i2/` - Implementation of the large Internet2 benchmark from literature.

To run a benchmark `BENCH=fave/bench/wl_your_benchmark_here` use the following commands:

    $> cd fave
    $> export PYTHONPATH=.
    $> source ~/.venv/bin/activate
    $> python3 $BENCH/benchmark.py

For instance, run the `example` benchmark as follows:

    $> cd fave
    $> export PYTHONPATH=.
    $> source ~/.venv/bin/activate
    $> python3 bench/wl_example/benchmark.py


## Credits

The original implementation of NetPlumber by Peyman Kazemian stems from [here](https://bitbucket.org/peymank/hassel-public/wiki/Home).

The original implementation of the PolicyTranslator by Vera Clemens stems from [here](https://github.com/veracl/fave-policy-translator.git).

The `apkeep/` directory vendors (via git-subtree, from our fork) the APKeep verifier by Peng Zhang et al., originally from [here](https://github.com/XJTU-NetVerify/apkeep) (MIT). It is being integrated as an alternative verification backend — see [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md). APKeep depends on the JDD BDD library by Arash Vahidi (zlib/public-domain), vendored under `apkeep/local-maven-repo/`.


## Selected References

[1] P. Kazemian, M. Chan, H. Zeng, G. Varghese, N. McKeown, and S. Whyte, “Real Time Network Policy Checking Using Header Space Analysis,” in NSDI, 2013.

[2] C. Diekmann, J. Michaelis, M. P. L. Haslbeck, and G. Carle, “Verified IPtables Firewall Analysis,” in IFIP Networking, 2016.

[3] D. Dumitrescu, R. Stoenescu, M. Popovici, L. Negreanu, and C. Raiciu, “Dataplane equivalence and its applications,” in NSDI, 2019.

[4] Y. Yin, Y. Tateiwa, Y. Wang, G. Zhang, Y. Katayama, N. Takahashi, and C. Zhang, “An Analysis Method for IPv6 Firewall Policy,” in HPCC, 2019.

[5] N. Basumatary and S. Hazarika, “Model Checking a Firewall for Anomalies,” in ICETACS, 2013.
