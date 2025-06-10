#!/bin/bash

# Check if directory is provided

# Get the directory path from command line argument
directory="./ProofDoorBenchmark/combined_cnfs/"

# Check if the directory exists
if [ ! -d "$directory" ]; then
    echo "Error: Directory '$directory' does not exist."
    exit 1
fi


# Create output directory if it doesn't exist
output_dir="${directory}"

echo "Processing CNF files in $directory..."

# Process each CNF file in the directory
for cnf_file in "$directory"/*.cnf; do
    if [ -f "$cnf_file" ]; then
        # Get the base filename without path and extension
        filename=$(basename "$cnf_file" .cnf)
        
        # Define the output log file
        log_file="$output_dir/$filename.log"
        ./solvers/cadical $cnf_file > $log_file
        # jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh ./solvers/cadical cadical $cnf_file | awk '{print $4}')
        # jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh ./solvers/minisat minisat $cnf_file | awk '{print $4}')
    fi
done
