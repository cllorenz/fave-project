#!/bin/bash

### ARGUMENTS ###

help_string="Usage: evaluation.sh [--help] [-o OUTPUT_DIR] [-m MEASUREMENTS_DIR] -b BENCHMARK_NAME"

benchmark_name=wl_ifi
measurements_dir=~/aggregator-logs/measurements
output_dir=~/aggregator_log/evaluation

# parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --help) echo $help_string ; exit 0 ;;
        -b) benchmark_name="$2"; shift ;;
        -m) measurements_dir="$2"; shift ;;
        -o) output_dir="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

measurements_dir=${measurements_dir}/${benchmark_name}
output_dir=${output_dir}/${benchmark_name}

### SCRIPT ###

rm -r $output_dir

# evaluate different configurations that a measurement has been executed on
# (see measurement.sh for running measurements)
for config in $(ls ${measurements_dir}); do
  eval_output_init=${output_dir}/${config}/init.dat
  eval_output_reach=${output_dir}/${config}/reach.dat
  eval_output_result=${output_dir}/${config}/results.dat
  eval_output_global_result=${output_dir}/results.dat
  mkdir --parents $(dirname $eval_output_init)
  touch $eval_output_init
  touch $eval_output_reach
  touch $eval_output_result
  touch $eval_output_global_result

  # collect statistics on multiple runs with same configuration
  for run in $(ls ${measurements_dir}/${config}); do
    aggregator_log=${measurements_dir}/${config}/${run}/aggregator.log
    
    # evaluate measurements of init phase in this run
    grep "seconds" $aggregator_log | grep -v "dump\|stop" | \
    awk 'BEGIN {
      done = 0; result = 0;
    } {
      if (done || $4 == "generators" || $4 == "generator") {
        done = 1;
      } else if (done && $4 == "probe") {
        done = 0;
        result += $6;
      } else {
        result += $6;
      }
    } END {
      print result * 1000.0;
    }' >> $eval_output_init

    # evaluate measurements of reach phase in this run
    grep "seconds" $aggregator_log | grep -v "dump\|stop" | \
    awk 'BEGIN {
      start = 0;
      result = 0;
    } {
      if (start || $4 == "generators" || $4 == "generator") {
        start = 1;
        if ($4 == "generators" || $4 == "generator") {
          result += $6;
        } else if ($4 == "links") {
          result += $6;
        } else if ($4 == "probe") {
          start = 0;
        }
      }
    } END {
      print result * 1000.0
    }' >> $eval_output_reach
  done

  # accumulate mean and standard deviation on init and reach phase
  echo "test"
  echo "${config}:" >> $eval_output_result
  echo "test"
  for DATA in $eval_output_init $eval_output_reach; do
    echo $(basename $DATA) >> $eval_output_result

    mean=$(awk -f $(dirname $0)/../bench/mean.awk -- $DATA)
    echo -n "Mean: " >> $eval_output_result
    if [ "$mean" == "0" ]; then
        echo "NaN" >> $eval_output_result
    else
        echo "$mean" >> $eval_output_result
    fi
    stddev=$(awk -f $(dirname $0)/../bench/stddev.awk -vMEAN=$mean -- $DATA)
    echo -n "Standard dev: " >> $eval_output_result
    if [ "$stddev" == "0" ]; then
        echo "NaN" >> $eval_output_result
    else
        echo "$stddev" >> $eval_output_result
    fi
  done

  cat $eval_output_result >> $eval_output_global_result
done