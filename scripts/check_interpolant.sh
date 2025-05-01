#!/bin/bash                                                    
#SBATCH --time=0-24:0:00                                                      
#SBATCH --account=def-vganesh   
#SBATCH --mem=40g         

# Get the array index
array_index=$SLURM_ARRAY_TASK_ID
# Get the list of SMT files
smt_path=$1
interpolant_path=$2

echo $smt_path
echo $interpolant_path
# Remove trailing slashes from paths
smt_path=${smt_path%/}

# Get the nth file from the list
smt_file=$(ls "$smt_path"/*.smt2 2>/dev/null | sed -n "${array_index}p")

if [ -z "$smt_file" ]; then
    echo "No file found for array index $array_index"
    exit 0
fi

# Extract the instance name from the file path
instance_name=$(basename "$smt_file" .smt2)

if [ ! -f "$smt_file" ]; then
    echo "Formula $smt_file DOES NOT exist." 
    exit 1
fi

# module load python/3.10
# module load scipy-stack
# source ../venv/bin/activate

# Generate interpolant
./z3 "$smt_file" > "$interpolant_path/$instance_name.interpolant"

