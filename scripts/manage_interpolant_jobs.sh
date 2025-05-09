#!/bin/bash
#SBATCH --time=0-16:0:00
#SBATCH --account=def-vganesh
#SBATCH --mem=4g
#SBATCH -o managing.log

# Check if this script is being run directly (not through sbatch)
testmode=false
if [ -z "$SLURM_JOB_ID" ]; then
    testmode=true
fi

mkdir -p ./ProofDoorBenchmark/data/
mkdir -p ./ProofDoorBenchmark/interpolants/
mkdir -p ./ProofDoorBenchmark/data/PDComputationTime/
mkdir -p ./ProofDoorBenchmark/interpolant_as_cnfs/
if [ -z "$1" ]; then
    echo "Error: k_value is required"
    echo "Usage: $0 <k_value>"
    exit 1
fi
k_value=$1
formula_category=$2
mkdir -p ./ProofDoorBenchmark/interpolants/${k_value}/
file_count=$(ls ./ProofDoorBenchmark/smts/$k_value/ | wc -l)
echo "File count: $file_count"
empty_file_count=$(find ./ProofDoorBenchmark/smts/$k_value/ -type f -empty | wc -l)
echo "Empty SMT2 count: $empty_file_count"
interpolants_file_count=$(ls ./ProofDoorBenchmark/interpolants/$k_value/ | wc -l)
echo "Interpolant file count: $interpolants_file_count"
empty_interpolant_file_count=$(find ./ProofDoorBenchmark/interpolants/$k_value/ -type f -empty | wc -l)
echo "Empty interpolant file count: $empty_interpolant_file_count"
sleep 10s
max_jobs=5000
batch_size=1441  # Smaller batch size for more gradual queue filling
current_index=1
limit=1000
priority=1

# Function to get number of running and pending jobs
get_queue_size() {
    # Count all running and pending tasks, including expanded array tasks
    squeue -u $USER -h -r -t RUNNING,PENDING | wc -l
}

# Function to submit next batch of jobs
submit_next_batch() {
    local start=$1
    local size=$2
    local end=$((start + size - 1))
    
    # Ensure we don't exceed max_jobs
    if [ $end -gt $max_jobs ]; then
        end=$max_jobs
    fi
    
    if [ $start -le $end ]; then
        job_id=$(./scripts/submit_interpolant_jobs.sh $k_value $start $end $formula_category $testmode)
        echo "$(date): Submitted batch $start-$end with job ID $job_id"
    fi
}

echo "$(date): Starting job management for k_value=$k_value"
mkdir -p ./running

# Main loop
while [ $current_index -le $max_jobs ]; do
    # Get current queue size
    queue_size=$(get_queue_size)
    echo "$(date): Current queue size: $queue_size tasks"
    
    # Calculate how many jobs we can submit
    available_slots=$((limit - queue_size))
    echo "$(date): Available slots: $available_slots"
    
    if [ $available_slots -ge $batch_size ]; then
        # We have room for at least one batch
        submit_next_batch $current_index $batch_size
        current_index=$((current_index + batch_size))
        echo "$(date): Next index: $current_index"
    else
        # Wait before checking again
        echo "$(date): Queue has $queue_size tasks. Waiting 5 minutes before next check..."
        sleep 300  # 5 minutes
    fi
    
    # If we're at the end, but still have jobs running, keep monitoring
    if [ $current_index -gt $max_jobs ] && [ $queue_size -gt 0 ]; then
        echo "$(date): All jobs submitted, waiting for remaining $queue_size jobs to complete..."
        sleep 300
    fi
done

echo "$(date): All interpolant jobs have been processed" 