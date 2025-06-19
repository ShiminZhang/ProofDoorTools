import time
import os
import argparse

def main():
    interested_names=[
        "6s277rb292",
        "6s275rb318",
        "6s194",
        "6s271rb045",
        "6s326rb08",
        "beembrptwo3b2",
        "beemcycschd3b1"
        "6s288",
        "6s0",
        "6s31",
        "6s119",
        "6s122",
        "6s134",
        "6s149",
        "6s159",
        "6s164",
        "6s173",
        "139444",
        "139443",
        "139452",
        "139453",
        "beemtrngt4b1",
        "beemszmsk1f1",
        "beemtlphn4f1",
        "beemmsmie1f1",
        "dspfilters_fastfir_second-p16",
        "dspfilters_fastfir_second-p21",
        "dspfilters_fastfir_second-p25",
        "intel020",
        "kenoopp1",
    ]

    ready_names = [
        # "6s277rb292",
        # "6s275rb318",
        # "6s194",
        # "6s271rb045",
        # "6s326rb08",
        # "beembrptwo3b2",
        # "beemcycschd3b1"
    ]
    K_set = [
        10,
        # 20
        ]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", default=False)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")
    
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
            print(f"sbatch --dependency=afterany:{slurm_id} --mem=16g --time=2:00:00 --wrap=\"{wrapped}\"/n")
            os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_{slurm_id}_sum_{K}_{name}.log --dependency=afterany:{slurm_id} --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
            slurm_ids.append(slurm_id)
        print(f"Slurm ids: {slurm_ids}")
        # for name in ready_names:
        #     wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name}"
        #     os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_sum_{K}_{name}.log --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
    

if __name__ == "__main__":
    main()