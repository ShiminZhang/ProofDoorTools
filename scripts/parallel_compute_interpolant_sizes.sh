#!/bin/bash
#SBATCH --account=def-vganesh

k=$1
interpolants_dir="ProofDoorBenchmark/interpolants/${k}/"
smt_dir="ProofDoorBenchmark/smts/${k}/"

# Get all interpolant files
interpolant_files=(${interpolants_dir}/*.interpolant)
total_files=${#interpolant_files[@]}

# Get the file to process based on array task ID
file=${interpolant_files[SLURM_ARRAY_TASK_ID-1]}

if [ -f "$file" ]; then
    echo "Processing $file"
    base_name=$(basename $file .interpolant)
    smt_file="${smt_dir}/${base_name}.smt2"
    # source /home/s568zhan/.myenv
    # source $python_generall
    source /home/s568zhan/scratch/general/bin/activate
    python3 scripts/count_interpolant_byz3.py $file --smt $smt_file --save --timeout -1
    deactivate
fi
