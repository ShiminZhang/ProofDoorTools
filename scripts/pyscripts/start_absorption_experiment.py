import time
import os
import argparse
from utils.paths import get_CNF_dir
from utils.catagory import get_instance_list

def main():
    K_set = [
        10,
        # 40
        ]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", default=False)
    parser.add_argument("--remove_absorption_result_caches_first", action="store_true", default=False)
    parser.add_argument("--prepare_only", action="store_true", default=False)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")
        
    if args.prepare_only:
        cnf_dir = get_CNF_dir(10)
        for name in os.listdir(cnf_dir):
            if name.endswith(".cnf"):
                name = name.split(".")[0]
                print(f"Processing {name}")
                continue
                for K in K_set:
                    for i in range(10):
                        if os.path.exists(f"{cnf_dir}/{name}.k_{K}.i_{i}.cnf"):
                            continue
                        os.system(f"sbatch --array=0-{K-1} --mem=10g --time=16:00:00 ./scripts/start_absorption_experiments.sh {K} {name} --prepare_only")
        exit()
    

if __name__ == "__main__":
    main()