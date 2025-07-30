import time
import os
import argparse
from utils.paths import get_CNF_dir,get_interpolant_dir
from utils.catagory import get_instance_list
from utils.tosmt import cnf_to_smt2_n_way
from prepare_data import prepare_all_datas, prepare_all_datas_for_one_smt
from tqdm import tqdm

def get_queue_size():
    return int(os.popen("squeue -u $USER -h -r -t RUNNING,PENDING | wc -l").read())

def count_lines(filepath):
    with open(filepath, 'rb') as f:  # open in binary mode for performance
        return sum(1 for line in f)

def main():
    linear = get_instance_list("linear")[50:103]
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
    parser.add_argument("--local_prepare_solving_time_only", action="store_true", default=False)
    parser.add_argument("--check_interpolants", action="store_true", default=False)
    parser.add_argument("--manage", action="store_true", default=False)
    parser.add_argument("--limit", action="store", default=1000)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")

    linear = get_instance_list("linear")
    polynomial = get_instance_list("polynomial")
    
    exponential = get_instance_list("exponential")
    combined = linear + polynomial + exponential
    # interested_names = combined
    interested_names = exponential
    if args.focus_name is not None:
        interested_names = [name for name in interested_names if name.startswith(args.focus_name)]
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

    if args.local_prepare_solving_time_only:
        K = 15
        cnf_dir = get_CNF_dir(K)
        for name in tqdm(os.listdir(cnf_dir)):
            if name.endswith(".cnf"):
                name = name.split(".")[0]
                if name not in combined:
                    continue
                print(f"Processing {name}")
                build = "./solvers/cadical"
                suffix = "cadicalplain"
                path = f"{cnf_dir}/{name}.{K}.cnf"
                log_path = f"{cnf_dir}/{name}.{K}.{suffix}.log"
                # os.system(f"time {build} {path} -inc-init > {log_path} 2>&1")
                os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {path} --plain > {log_path} 2>&1\"")
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
        K = 40
        if args.manage:
            batch_size = K
            limit = int(args.limit)
            index = 1520
            while index < batch_size * len(interested_names):
                queue_size = get_queue_size()
                print(f"Queue size: {queue_size}, Index: {index}")
                while get_queue_size() < limit - batch_size and index < batch_size * len(interested_names):
                    name = interested_names[index // batch_size]
                    for i in range(batch_size):
                        prepare_all_datas_for_one_smt(name,K,i,True)
                    index += batch_size
                print(f"Updated Index: {index}, Queue size: {get_queue_size()}")
                time.sleep(300)
        else:
            print(f"Count: {len(interested_names)}")
            print(interested_names)
            for name in interested_names:
                for i in range(15):
                    prepare_all_datas_for_one_smt(name,15,i,False)
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
            slurm_output = os.popen(f"sbatch --array=0-{K-1} --mem=10g --time=20:00:00 ./scripts/start_absorption_experiments.sh {K} {name}").read()
            # slurm_output = os.popen("echo 123456").read()
            print(slurm_output)
            slurm_id = int(slurm_output.split()[-1])
            # print(f"Slurm id: {slurm_id}")
            # time.sleep(5)
            wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name} --skip_prepare"
            print(f"sbatch --dependency=afterany:{slurm_id} --mem=16g --time=2:00:00 --wrap=\"{wrapped}\"/n")
            os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_{slurm_id}_sum_{K}_{name}.log --dependency=afterany:{slurm_id} --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
            slurm_ids.append(slurm_id)
        print(f"Slurm ids: {slurm_ids}")
        # for name in ready_names:
        #     wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name}"
        #     os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_sum_{K}_{name}.log --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
    

if __name__ == "__main__":
    main()