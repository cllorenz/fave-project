#!/usr/bin/env python2

""" This module benchmarks FaVe with an example workload.
"""

from bench.generic_benchmark import GenericBenchmark

if __name__ == "__main__":
    GenericBenchmark("bench/wl_example").run()
