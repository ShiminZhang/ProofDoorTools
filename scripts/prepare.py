import time
import os
import argparse
from utils.paths import get_CNF_dir,get_interpolant_dir
from utils.catagory import get_instance_list
from prepare_data import prepare_all_datas, prepare_all_datas_for_one_smt
from tqdm import tqdm

def count_lines(filepath):
    with open(filepath, 'rb') as f:  # open in binary mode for performance
        return sum(1 for line in f)

def main():
    linear = get_instance_list("linear")[0:103]
    polynomial = get_instance_list("polynomial")[0:100]
    exponential = get_instance_list("exponential")[0:100]
    
    K_set = [
        10,
        # 40
        ]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", default=False)
    parser.add_argument("--remove_absorption_result_caches_first", action="store_true", default=False)
    parser.add_argument("--prepare_only", action="store_true", default=False)
    parser.add_argument("--focus_name", action="store", default=None)
    parser.add_argument("--prepare_solving_time_only", action="store_true", default=False)
    parser.add_argument("--check_interpolants", action="store_true", default=False)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")

    if args.check_interpolants:
        interpolant_dir = get_interpolant_dir(10)
        count = 0
        for name in os.listdir(interpolant_dir):
            file_path = f"{interpolant_dir}/{name}"
            length = count_lines(file_path)
            basename = name.split(".")[0]
            k_value = int(name.split(".")[1])
            index = int(name.split(".")[2])
            assert k_value == 10
            if length < 3:
                with open(file_path, "r") as file:
                    lines = file.readlines()
                    if len(lines) == 0 or "error" in lines[0]:
                        count += 1
                        print(f"error in {file_path}")
                        prepare_all_datas_for_one_smt(basename,k_value,index,False)
        print(f"Count: {count}")
        exit()

    if args.prepare_solving_time_only:
        combined = polynomial + exponential + linear
        cnf_dir = get_CNF_dir(10)
        for name in tqdm(os.listdir(cnf_dir)):
            if name.endswith(".cnf"):
                name = name.split(".")[0]
                if name not in combined:
                    continue
                print(f"Processing {name}")
                build = "./solvers/cadical"
                suffix = "cadical_original"
                path = f"{cnf_dir}/{name}.{10}.cnf"
                os.system(f"sbatch --mem=16g --time=00:00:5000 ./scripts/submit_solver.sh {build} {suffix} {path}")
        exit()

    if args.prepare_only:

        linear = get_instance_list("linear")
        polynomial = get_instance_list("polynomial")
        exponential = get_instance_list("exponential")
        combined = linear + polynomial + exponential
        interested_names = combined
        if args.focus_name is not None:
            interested_names = [name for name in interested_names if name.startswith(args.focus_name)]
        for name in interested_names:
            prepare_all_datas_for_one_smt(name,10,0,False)
        print(f"Count: {len(interested_names)}")
        exit()
    
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