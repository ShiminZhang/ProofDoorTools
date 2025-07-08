#!/bin/bash                                                    
#SBATCH --time=0-8:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=20G
source ../general/bin/activate
# Function to check if required directories exist and create them if needed
check_and_create_dirs() {
    local dirs=("pds_st_correlation")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            echo "Creating directory: $dir"
            mkdir -p "$dir"
        fi
    done
}

# Function to run a single experiment with error handling
run_experiment() {
    local focus_name=$1
    local output_file="pds_st_correlation/${focus_name}.out"
    
    echo "Starting experiment for: $focus_name"
    
    python scripts/process_interpolants.py \
        --K 10 \
        --UseCache \
        --Solver cadicalplain \
        --FocusName "$focus_name" \
        > "$output_file"
}

# Function to run all experiments
run_all_experiments() {
    local focus_names=("6s" "beem" "bob" "eijks" "gen" "intel" "kenflash" "mentor" "neclaft" "nusmv" "oc805" "oski15" "pdt" "qspiflash") 
    
    echo "Starting batch experiments..."
    echo "=================================="
    
    for focus_name in "${focus_names[@]}"; do
        run_experiment "$focus_name"
        echo "----------------------------------"
    done
    
    echo "All experiments completed!"
}

# Main execution
echo "Initializing experiment environment..."
check_and_create_dirs

echo "Starting experiments..."
run_all_experiments