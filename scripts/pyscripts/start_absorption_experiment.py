import time
import os
import argparse

def main():
    
    interested_names=[
        "intel003", # exp
        "intel020", # exp
        # "intel007", # exp 
        # "intel031", # exp 
        # "intel056", # exp 
        # "intel037", # lin
        # "intel001", # poly
        # "intel004", # poly
        # "intel063", # poly
        # # "cal102", # exp
        # # "cal176", # exp
        # # "cal21", # exp
        # # "cal119", # lin
        # # "cal162", # lin
        # # "cal37", # lin
        # # "cal125", # poly
        # # "cal159", # poly
        # # "cal161", # poly
        # "139444p0", # proof empty
        # "139443p0", # proof empty
        # "139452p0", # proof empty
        # "139453p0", # proof empty
        
        # "6s0", # recompute
        # "6s159", # recompute
        # "6s109", # exp
        # "6s43", # exp
        # "6s43", # exp
        # "6s6s410rb043", # exp
        # # "6s31", # smt invalid
        # # "6s119", # smt invalid
        # "6s290", # lin
        # "6s372rb26", # lin
        # # "6s277rb292", # proof empty
        # # "6s164", # proof empty
        
        # # "6s149", # smt invalid
        # # "6s164", # proof empty
        # # "6s173", # UNKNOWN
    ]
    # interested_names=[
    #     # "6s277rb292", # proof empty
    #     # "6s275rb318", # timeout
    #     "6s194", # done
    #     # "6s271rb045", # interpolant fail, proof empty
    #     "6s326rb08", # done 
    #     "beembrptwo3b2", # done
    #     "beemcycschd3b1", # WIP
    #     "6s288", # WIP
    #     "6s0", # done
    #     # "6s31", # smt invalid
    #     # "6s119", # smt invalid
    #     "6s122", # done 
    #     "6s134", # done 
    #     # "6s149", # smt invalid
    #     "6s159", # done
    #     # "6s164", # proof empty
    #     # "6s173", # UNKNOWN
    #     # "139444p0", # proof empty
    #     # "139443p0", # proof empty
    #     # "139452p0", # proof empty
    #     # "139453p0", # proof empty
    #     # "beemtrngt4b1", # too many literals? 
    #     "beemszmsk1f1", # done
    #     # "beemtlphn4f1", # interpolant too large
    #     "beemmsmie1f1", # timeout
    #     "dspfilters_fastfir_second-p16", # timeout
    #     # "dspfilters_fastfir_second-p21", # too many literals?
    #     "dspfilters_fastfir_second-p25", # timeout
    #     "intel020", # done 
    #     "kenoopp1", # done
    # ]

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
        # 10,
        40
        ]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", default=False)
    parser.add_argument("--remove_absorption_result_caches_first", action="store_true", default=False)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")
    activate_python = "source ../general/bin/activate"
    for K in K_set:
        slurm_ids = []
        for name in interested_names:
            if args.remove_absorption_result_caches_first:
                for i in range(K):
                    if os.path.exists(f"ProofDoorBenchmark/absorption_experiments/{name}.k_{K}.i_{i}.check_absorb.json"):
                        os.remove(f"ProofDoorBenchmark/absorption_experiments/{name}.k_{K}.i_{i}.check_absorb.json")
            
            print(f"sbatch --array=0-{K-1} ./scripts/start_absorption_experiments.sh {K} {name}")
            slurm_output = os.popen(f"sbatch --array=0-{K-1} --mem=10g --time=20:00:00 ./scripts/start_absorption_experiments.sh {K} {name} --force_refresh").read()
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