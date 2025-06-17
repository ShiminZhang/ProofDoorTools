import time
import os

def main():
    interested_names=[
        "6s277rb292",
        "6s275rb318",
        "6s194",
        "6s271rb045",
        "6s326rb08",
        "beembrptwo3b2",
        "beemcycschd3b1"
    ]
    K_set = [
        # 10,
        20
        ]
    
    activate_python = "source ../general/bin/activate"
    for K in K_set:
        slurm_ids = []
        for name in interested_names:
            print(f"sbatch --array=0-{K-1} ./scripts/start_absorption_experiments.sh {K} {name}")
            slurm_output = os.popen(f"sbatch --array=0-{K-1} --mem=10g ./scripts/start_absorption_experiments.sh {K} {name} --force_refresh").read()
            # slurm_output = os.popen("echo 123456").read()
            slurm_id = int(slurm_output.split()[-1])
            # print(f"Slurm id: {slurm_id}")
            # time.sleep(5)
            wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name}"
            print(f"sbatch --dependency=afterany:{slurm_id} --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"/n")
            os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_{slurm_id}_sum_{K}_{name}.log --dependency=afterany:{slurm_id} --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
            slurm_ids.append(slurm_id)
        print(f"Slurm ids: {slurm_ids}")
        
        # Wait for all jobs to complete
        # for slurm_id in slurm_ids:
        #     os.system(f"srun --dependency=afterany:{slurm_id} echo 'Job {slurm_id} completed'")
        # Start next slurm job after all previous jobs are done
        # next_slurm_id = os.system(f"sbatch --dependency=afterany:{','.join(map(str, slurm_ids))} ./scripts/start_next_experiment.sh {target}")
        # print(f"Next slurm job started with ID: {next_slurm_id}")
    

if __name__ == "__main__":
    main()