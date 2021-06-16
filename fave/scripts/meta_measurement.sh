#!/bin/bash

### ARGUMENTS ###

help_string="Usage: measurement.sh [--help] [-r NUMBER_RUNS [-s START_RUN]] [-t THREADS_CONFIGS] [-n NODES_CONFIGS] -b BENCHMARK_NAME"

nb_runs=1
start_run=1
node_configs=(1)
thread_configs=(1)
benchmark_name=wl_ifi

# parse arguments
while [[ "$#" -gt 0 ]]; do
    # parse array of thread numbers to iterate over
    if [ $1 == "-t" ];
    then
        thread_configs=()
        shift
        while [[ $1 != "-"* ]]; do
            thread_configs+=($1)
            shift
        done
        echo "Thread configs: ${thread_configs[@]}"
    fi
    
    # parse array of node numbers to iterate over
    if [ $1 == "-n" ];
    then
        node_configs=()
        shift
        while [[ $1 != "-"* ]]; do
            node_configs+=($1)
            shift
        done
        echo "Node configs: ${node_configs[@]}"
    fi

    case $1 in
        --help) echo $help_string ; exit 0 ;;
        -r) nb_runs="$2"; shift ;;
        -b) benchmark_name="$2"; shift ;;
        -s) start_run="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

### SCRIPT ###

# dense mapping
for nb_threads in "${thread_configs[@]}"; do
  nb_nodes=1
  for run in $(seq $start_run $(($start_run + $nb_runs - 1))); do
    echo "RUNNING MEASUREMENT $run WITH N=$nb_nodes AND T=$nb_threads"
    srun --partition=long --time=00:10:00 --exclusive --nodes=$nb_nodes $FAVE_PATH/scripts/run_benchmark_parallel.sh -n $nb_threads -o ~/np_output -l ~/np_output_logs -p 10041 -b $benchmark_name
    mkdir --parents ~/aggregator-logs/measurements/${benchmark_name}/n${nb_nodes}t${nb_threads}/run${run}; cp ~/np_output_logs/aggregator.log $_
  done
done

# sparse mapping
for nb_nodes in "${node_configs[@]}"; do
  nb_threads=1
  for run in $(seq $start_run $(($start_run + $nb_runs - 1))); do
    echo "RUNNING MEASUREMENT $run WITH N=$nb_nodes AND T=$nb_threads"
    srun --partition=long --time=00:10:00 --exclusive --nodes=$nb_nodes $FAVE_PATH/scripts/run_benchmark_parallel.sh -n $nb_threads -o ~/np_output -l ~/np_output_logs -p 10041 -b $benchmark_name
    mkdir --parents ~/aggregator-logs/measurements/${benchmark_name}/n${nb_nodes}t${nb_threads}/run${run}; cp ~/np_output_logs/aggregator.log $_
  done
done
