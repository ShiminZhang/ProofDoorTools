#! /bin/bash
#SBATCH --time=0-12:0:00
#SBATCH --mem=16g
#SBATCH --job-name=absorption_experiments
#SBATCH --output=SlurmLogs/absorption_experiments_%A_%a.out
#SBATCH --mail-type=ALL
#SBATCH --mail-user=s568zhan@uwaterloo.ca
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --priority=0

k_value=$1

target_name=$2
if [ -z "$k_value" ]; then
    echo "Error: k_value must be specified"
    exit 1
fi

force_refresh=$3
# instance_index=$2
# if [ -z "$instance_index" ]; then
#     echo "Error: instance_index must be specified"
#     exit 1
# fi

# interested_names=(
#     "6s277rb292"
#     "6s275rb318"
#     "6s194"
#     "6s271rb045"
#     "6s326rb08"
#     "beembrptwo3b2"
#     "beemcycschd3b1"
#     )

echo k=$k_value name="${target_name}" index=$SLURM_ARRAY_TASK_ID
source ../general/bin/activate
# python scripts/check_proof_absorb_PD.py --K $k_value --target_name ${interested_names[$instance_index]} --index $SLURM_ARRAY_TASK_ID
python scripts/check_proof_absorb_PD.py --K $k_value --target_name ${target_name} --index $SLURM_ARRAY_TASK_ID $force_refresh