# FaVe - Fast Formal Security Verification

This repo includes the codebase of FaVe.

 - `fave/` - includes the modeling pipeline and a set of management tools
 - `net_plumber/` - includes the NetPlumber verification backend
 - `policy_translator/` - includes the policy management tool [PolicyTranslator](policy_translator/README.md)
 - `ad6` - includes ad6 for anomaly detection in ip6tables rule sets


## First steps (tested on Ubuntu 20.04)

First, one needs to install some dependencies to compile NetPlumber. The script

    #> net_plumber/setup-ubuntu.sh

performs the necessary steps on an Ubuntu machine. Afterwards, one needs to switch to

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

    $> export PYTHONPATH=fave
    $> python2 fave/test/example.sh

Typically, a session comprises of two processes: `aggregator_service.py` and `net_plumber`. These can be stopped or started using their respective scripts in `fave/scripts`. If one process dies one needs to restart both - first NetPlumber and then FaVe. Logfiles are stored in `/dev/shm/np`.


## Benchmarks

There exist some benchmarks showing the capabilities of FaVe:

 - `fave/bench/wl_example` - A simple example workload.
 - `fave/bench/wl_ifi/` - Implementation of the small IFI benchmark which is a reasonably complex yet still manually explorable network configuration.
 - `fave/bench/wl_up/` - Implementation of the synthetic, mid-sized, and complex UP benchmark which mimics a university campus network.
 - `fave/bench/wl_tum/` - Implementation of the complex TUM-i8 benchmark from literature including a large firewall ruleset.
 - `fave/bench/wl_stanford/` - Implementation of the large Stanford benchmark from literature including ACLs.
 - `fave/bench/wl_i2/` - Implementation of the large Internet2 benchmark from literature.

To run a benchmark `BENCH=fave/bench/wl_your_benchmark_here` use the following commands:

    $> export PYTHONPATH=fave
    $> python2 $BENCH/benchmark.py


## Open Issues

Refer to the [TODOs](TODO.md) for further issues to repair and solve.
