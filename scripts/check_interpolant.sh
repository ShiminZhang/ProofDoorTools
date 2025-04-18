#!/bin/bash                                                    
#SBATCH --time=0-0:0:10000                                                      
#SBATCH --account=def-vganesh   
#SBATCH --mem=20g         

instance_name=$1
smt_path=$2
interpolant_path=$3

if [ ! -f "$smt_path/$instance_name.smt2" ] 
then
    echo "Formula $smt_path/$instance_name.smt2 DOES NOT exist." 
    exit 1
fi

# module load python/3.10
# module load scipy-stack
# source ../venv/bin/activate

filename=$(basename $3)
./z3 $smt_path/$instance_name.smt2 > $interpolant_path/$instance_name.interpolant

