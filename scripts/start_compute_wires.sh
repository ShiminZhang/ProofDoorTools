#! /bin/bash
#SBATCH --time=0-3:00:00                                                      
#SBATCH --account=def-vganesh   
#SBATCH --mem=20g    
#SBATCH --array=1-351
#SBATCH --output=./SlurmLogs/WireLogs/compute_wires_%A_%a.out
array_index=$SLURM_ARRAY_TASK_ID
# array_index=$1

cnf_dir=./ProofDoorBenchmark/cnfs/10/
cnf_path=$(ls $cnf_dir/*.cnf | sed -n ${array_index}p)
echo $cnf_path

source ../general/bin/activate
python scripts/compute_wires.py --cnf_path $cnf_path
deactivate
