#!/bin/bash

### ARGUMENTS ###

help_string="Usage: measurement.sh [--help] [-r NUMBER_RUNS [-s START_RUN]] [-t NUMBER_THREADS] [-n NUMBER_NODES] -b BENCHMARK_NAME"

nb_runs=1
start_run=1
nb_nodes=2
nb_threads=1
benchmark_name=wl_ifi

# parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --help) echo $help_string ; exit 0 ;;
        -r) nb_runs="$2"; shift ;;
        -n) nb_nodes="$2"; shift ;;
        -t) nb_threads="$2"; shift ;;
        -b) benchmark_name="$2"; shift ;;
        -s) start_run="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

### SCRIPT ###

# execute same configuration multiple times and
# archive aggregator log in folder structure
# (see evaluation.sh for processing of aggregator logs)
for run in $(seq $start_run $(($start_run + $nb_runs - 1))); do
  echo "RUNNING MEASUREMENT $run WITH N=$nb_nodes AND T=$nb_threads"
  srun --partition=long --time=00:10:00 --exclusive --nodes=$nb_nodes $FAVE_PATH/scripts/run_benchmark_parallel.sh -n $nb_threads -o ~/np_output -l ~/np_output_logs -p 10041 -b $benchmark_name
  mkdir --parents ~/aggregator-logs/measurements/${benchmark_name}/n${nb_nodes}t${nb_threads}/run${run}; cp ~/np_output_logs/aggregator.log $_
done