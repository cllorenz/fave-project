#!/usr/bin/env python3

""" This module benchmarks FaVe with an example workload.
"""

from bench.generic_benchmark import GenericBenchmark


def workload():
    """ The benchmark, as configured here; test/gen_wl_example_inputs.sh
    generates its inputs from this same object. """
    return GenericBenchmark(
        "bench/wl_example",
        anomalies={'use_shadow' : True}
    )


if __name__ == "__main__":
    workload().run()
