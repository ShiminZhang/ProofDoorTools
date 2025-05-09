#!/bin/bash
#SBATCH --time=0-08:0:00
#SBATCH --account=def-vganesh
#SBATCH --mem=4g
#SBATCH -o managing_sizes.log

if [ -z "$1" ]; then
    echo "Error: k_value is required"
    echo "Usage: $0 <k_value>"
    exit 1
fi

k_value=$1
interpolants_dir="ProofDoorBenchmark/interpolants/${k_value}/"
smt_dir="ProofDoorBenchmark/smts/${k_value}/"
mkdir -p ProofDoorBenchmark/PDsizeLogs
mkdir -p ProofSizeMap/data/${k_value}
# Get all interpolant files
interpolant_files=(${interpolants_dir}/*.interpolant)
total_files=${#interpolant_files[@]}
echo "Total files to process: $total_files"

# Function to get number of running and pending jobs
get_queue_size() {
    squeue -u $USER -h -r -t RUNNING,PENDING | wc -l
}

# Function to submit next batch of jobs
submit_next_batch() {
    local start=$1
    local size=$2
    local end=$((start + size - 1))
    
    if [ $start -le $end ]; then
        sbatch --array=${start}-${end} \
               --mem=20G \
               --time=8:00:00 \
               --output="ProofDoorBenchmark/PDsizeLogs/computePDsize_%A_%a.log" \
               scripts/parallel_compute_interpolant_sizes.sh $k_value
        echo "$(date): Submitted batch $start-$end"
    fi
}

echo "$(date): Starting job management for k_value=$k_value"
mkdir -p ./running

# Main loop
current_index=1007
limit=1000  # Maximum number of jobs to run at once
batch_size=40  # Number of array tasks per batch
while [ $current_index -le $total_files ]; do
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
    if [ $current_index -gt $total_files ] && [ $queue_size -gt 0 ]; then
        echo "$(date): All jobs submitted, waiting for remaining $queue_size jobs to complete..."
        sleep 300
    fi
done

echo "$(date): All interpolant size computation jobs have been processed" 