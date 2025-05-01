#!/bin/bash

# Function to get number of running and pending jobs
get_queue_size() {
    # Get all jobs with their array task counts
    local total_tasks=0
    
    # Get detailed job information including array tasks
    while IFS= read -r line; do
        if [[ $line =~ ([0-9]+)_\[([0-9]+)-([0-9]+)%[0-9]+\] ]]; then
            # This is a compact array job notation with %limit
            start="${BASH_REMATCH[2]}"
            end="${BASH_REMATCH[3]}"
            tasks=$((end - start + 1))
            echo "Array job ${BASH_REMATCH[1]} has $tasks tasks (range: $start-$end)"
            total_tasks=$((total_tasks + tasks))
        elif [[ $line =~ ^([0-9]+)_([0-9]+)$ ]]; then
            # This is a single array task
            echo "Single array task ${BASH_REMATCH[1]}_${BASH_REMATCH[2]}"
            total_tasks=$((total_tasks + 1))
        elif [[ $line =~ ^[0-9]+$ ]]; then
            # This is a regular job
            echo "Regular job $line"
            total_tasks=$((total_tasks + 1))
        fi
    done < <(squeue -u $USER -h -o "%i" -t RUNNING,PENDING)
    
    echo "Total tasks: $total_tasks"
}

echo "Testing queue size function..."
get_queue_size 