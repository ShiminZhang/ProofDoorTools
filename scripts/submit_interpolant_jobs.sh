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
formula_category=$4
testmode=$5
scratch_benchmark_path="./ProofDoorBenchmark"

# Submit the batch
echo "Submitting jobs: $start_index-$end_index"
# If in test mode, run check_interpolant.sh directly instead of submitting to SLURM
if [ "$testmode" = "true" ]; then
    echo "Running in test mode for indices $start_index to $end_index"
    for i in $(seq $start_index $end_index); do
        export SLURM_ARRAY_TASK_ID=$i
        echo "Running task $i directly"
        ./scripts/check_interpolant.sh ${scratch_benchmark_path}/smts/$k_value/ ${scratch_benchmark_path}/interpolants/$k_value/ $formula_category
    done
    echo "Test mode completed"
    exit 0
fi

# Continue with SLURM submission if not in test mode

jobid=$(sbatch --array=$start_index-$end_index%1000 --priority 0 -o ./Outputs/compute_interpolant_%A_%a.out ./scripts/check_interpolant.sh ${scratch_benchmark_path}/smts/$k_value/ ${scratch_benchmark_path}/interpolants/$k_value/ $formula_category | awk '{print $4}')
echo "Submitted array job $start_index-$end_index with ID: $jobid" >> ./running/runningjobs.log
echo "Submitted array job $start_index-$end_index with ID: $jobid"
echo $jobid 