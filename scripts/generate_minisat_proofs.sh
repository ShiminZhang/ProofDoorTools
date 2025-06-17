#!/bin/bash

k_value=$1

# Check if directory is provided

# Get the directory path from command line argument
directory="./ProofDoorBenchmark/cnfs/$k_value/"

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
        log_file=$(echo $cnf_file | sed 's/\.cnf/.drat/')
        # ./solvers/minisat_pf $cnf_file | grep "PDLOG Learnt clause:" | sed 's/PDLOG Learnt clause: //' > $log_file
        echo "saved to $log_file"
        jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out --mem=10g --time=1:30:00 --wrap="./solvers/minisat_nodel $cnf_file | grep 'PDLOG Learnt clause:' | sed 's/PDLOG Learnt clause: //' > $log_file")
        # jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh ./solvers/minisat minisat $cnf_file | awk '{print $4}')
    fi
done
