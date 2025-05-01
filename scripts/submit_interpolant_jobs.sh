#!/bin/bash
#SBATCH --time=0-24:0:00
#SBATCH --account=def-vganesh
#SBATCH --mem=24g

# Check if k_value and range are provided
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Error: k_value and range are required"
    echo "Usage: $0 <k_value> <start_index> <end_index>"
    exit 1
fi

k_value=$1
start_index=$2
end_index=$3
scratch_benchmark_path="./ProofDoorBenchmark"

# Submit the batch
echo "Submitting jobs: $start_index-$end_index"
jobid=$(sbatch --array=$start_index-$end_index%1000 --priority 0 -o ./Outputs/interpolant_%A_%a.out ./scripts/check_interpolant.sh ${scratch_benchmark_path}/smts/$k_value/ ${scratch_benchmark_path}/interpolants/$k_value/ | awk '{print $4}')
echo "Submitted array job $start_index-$end_index with ID: $jobid" >> ./running/runningjobs.log
echo "Submitted array job $start_index-$end_index with ID: $jobid"
echo $jobid 