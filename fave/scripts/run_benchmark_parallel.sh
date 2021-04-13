#!/bin/bash
help_string="Usage: run_benchmark_parallel.sh [--help] [-n NUMBER_PROCESSES_PER_NODE] [-o OUTPUT_DIR] [-l LOG_DIR] [-p START_PORT] -b BENCHMARK_NAME"

# path variables predefined
netplumber_path=$NETPLUMBER_PATH
fave_path=$FAVE_PATH

# default values for options
benchmark_name=wl_ifi
start_port=10041
num_cores_per_node=1
np_flows_output_directory=$HOME/np_output
log_dir=$HOME/np_output_logs

# parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --help) echo $help_string ; exit 0 ;;
        -n) num_cores_per_node="$2"; shift ;;
        -o) np_flows_output_directory="$2"; shift ;;
        -p) start_port="$2"; shift ;;
        -b) benchmark_name="$2"; shift ;;
        -l) log_dir="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

end_port=$(($start_port + $num_cores_per_node - 1))

export num_cores_per_node
export start_port
export end_port
export np_flows_output_directory
export log_dir

# build benchmark paths
echo "Starting benchmark: $benchmark_name"
benchmark_conf_path=$fave_path/bench/$benchmark_name/np.conf
benchmark_entry_point=$fave_path/bench/$benchmark_name/benchmark.py

# assumes slurm as load manager
slurm_proc_id=$SLURM_PROCID
export slurm_node_id=$(env | grep SLURMD_NODENAME | cut -d "=" -f2)

# with while loop for starting multiple instances on one node
if [ $slurm_proc_id == 0 ] 
then
  echo "Master: $slurm_node_id"
  cur_port=$start_port
  
  # start instances on master node
  while [ $cur_port -le $end_port ]
  do
      echo "Start host: $slurm_node_id:$cur_port"
      net_plumber --log4j-config $benchmark_conf_path --hdr-len 1 --server $slurm_node_id $cur_port >> $log_dir/stdout_${slurm_node_id}_${cur_port}.log 2>> $log_dir/stderr_${slurm_node_id}_${cur_port}.log &
      cur_port=$(($cur_port + 1))
  done
  
  # start benchmark on master node
  cd $fave_path
  python2 $benchmark_entry_point $num_cores_per_node
else
  cur_port=$start_port
  while [ $cur_port -le $end_port ]
  do
      echo "Start host: $slurm_node_id:$cur_port"
      net_plumber --log4j-config $benchmark_conf_path --hdr-len 1 --server $slurm_node_id $cur_port >> $log_dir/stdout_${slurm_node_id}_${cur_port}.log 2>> $log_dir/stderr_${slurm_node_id}_${cur_port}.log &
      cur_port=$(($cur_port + 1))
  done
fi