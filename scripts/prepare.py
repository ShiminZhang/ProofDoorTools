import time
import os
import argparse
from utils.paths import get_CNF_dir,get_interpolant_dir, get_shuffled_cnf_dir, get_solving_time_dir
from utils.catagory import get_instance_list
from utils.tosmt import cnf_to_smt2_n_way
from prepare_single import prepare_all_datas,set_debug, prepare_all_datas_for_one_smt, prepare_all_datas_for_one_smt_with_decompose
from tqdm import tqdm
import random

def get_queue_size():
    return int(os.popen("squeue -u $USER -h -r -t RUNNING,PENDING | wc -l").read())

def count_lines(filepath):
    with open(filepath, 'rb') as f:  # open in binary mode for performance
        return sum(1 for line in f)

def main():
    linear = get_instance_list("linear")
    polynomial = get_instance_list("polynomial")
    exponential = get_instance_list("exponential")
    
    K_set = [
        10,
        # 40
        ]
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", default=False)
    parser.add_argument("--remove_absorption_result_caches_first", action="store_true", default=False)
    parser.add_argument("--prepare_only", action="store_true", default=False)
    parser.add_argument("--category", action="store", default="all")
    parser.add_argument("--focus_name", action="store", default=None)
    parser.add_argument("--K", action="store", default=10)
    parser.add_argument("--prepare_solving_time_only", action="store_true", default=False)
    parser.add_argument("--local_prepare_solving_time_only", action="store_true", default=False)
    # parser.add_argument("--prepare_solving_time_only", action="store_true", default=False)
    parser.add_argument("--compute_strongest_interpolant", action="store_true", default=False)
    parser.add_argument("--check_interpolants", action="store_true", default=False)
    parser.add_argument("--manage", action="store_true", default=False)
    parser.add_argument("--limit", action="store", default=1000)
    parser.add_argument("--max_index",type=int, action="store", default=10000000)
    parser.add_argument("--pddef", action="store", default=0)
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--no_interpolant", action="store_true", default=False)
    parser.add_argument("--permute_and_run", action="store_true", default=False)
    parser.add_argument("--prepare_sequential", action="store_true", default=False)
    parser.add_argument("--prepare_scaling", action="store_true", default=False)
    args = parser.parse_args()
    if args.clean:
        os.system("rm ProofDoorBenchmark/absorption_experiments/*.json")
        os.system("rm ./SlurmLogs/absorption_experiments_*")
    if args.debug:
        set_debug(True)

    #category can be comma separated list of categories
    if "," in args.category:
        categories = args.category.split(",")
        interested_names = []
        for category in categories:
            interested_names.extend(get_instance_list(category))
    else:
        interested_names = get_instance_list(args.category)
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

    if args.permute_and_run:
        K = args.K
        cnf_dir = get_CNF_dir(K)
        shuffled_cnf_dir = get_shuffled_cnf_dir(K)
        limit = 200
        for name in interested_names:
            cnf_path = f"{cnf_dir}/{name}.{K}.cnf"
            if not os.path.exists(cnf_path):
                continue
            if limit <= 0:
                break
            limit -= 1
            shuffled_cnf_path = f"{shuffled_cnf_dir}/{name}.{K}.cnf"
            # if not os.path.exists(shuffled_cnf_path):
            #     # shuffle the cnf file except the first 1 line
            #     with open(cnf_path, "r") as file:
            #         lines = file.readlines()
            #         with open(shuffled_cnf_path, "w") as shuffled_file:
            #             shuffled_file.write(lines[0])
            #             clauses = lines[1:]
            #             random.shuffle(clauses)
            #             for line in clauses:
            #                 shuffled_file.write(line)
            lrat_path = f"{shuffled_cnf_path}.lrat"
            shuffle_log_path = f"{shuffled_cnf_path}.shuffled.log"
            original_log_path = f"{shuffled_cnf_dir}/{name}.{K}.original.log"
            
            build = "./solvers/cadical"
            os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {cnf_path} --lrat {lrat_path} --no-binary --plain > {original_log_path} 2>&1\"")
            os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {shuffled_cnf_path} --lrat {lrat_path} --no-binary --plain > {shuffle_log_path} 2>&1\"")

            minisat_solver = "./solvers/minisat"
            minisat_shuffle_log_path = f"{shuffled_cnf_path}.minisat_shuffled.log"
            minisat_original_log_path = f"{shuffled_cnf_dir}/{name}.{K}.minisat_original.log"
            os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {minisat_solver} {shuffled_cnf_path}  > {minisat_shuffle_log_path} 2>&1\"")
            os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {minisat_solver} {cnf_path}  > {minisat_original_log_path} 2>&1\"")


    if args.local_prepare_solving_time_only:
        K_range = range(1,20,1)
        interested_names = get_instance_list(args.category)
        for K in tqdm(K_range):
            cnf_dir = get_CNF_dir(K)
            solving_time_dir = get_solving_time_dir(K)
            build = "./solvers/cadical"
            for file in tqdm(os.listdir(cnf_dir)):
                if file.endswith(".cnf"):
                    name = file.split(".")[0]
                    if name not in interested_names:
                        continue
                    cadical_original_solving_time_path = f"{solving_time_dir}/{name}.{K}.cadical_original.log"
                    if not os.path.exists(cadical_original_solving_time_path):
                        os.system(f"time {build} {cnf_dir}/{file} --plain > {cadical_original_solving_time_path} 2>&1")

    if args.prepare_solving_time_only:
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
                # build = "./solvers/minisat"
                # suffix = "minisat"
                path = f"{cnf_dir}/{name}.{K}.cnf"
                lrat_path = f"{cnf_dir}/{name}.{K}.lrat"
                log_path = f"{cnf_dir}/{name}.{K}.{suffix}.log"
                # os.system(f"time {build} {path} -inc-init > {log_path} 2>&1")
                # os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {path} --plain > {log_path} 2>&1\"")
                # os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {path} > {log_path} 2>&1\"")
                os.system(f"sbatch --mem=16g --time=00:00:5000 --wrap=\"time {build} {path} --lrat {lrat_path} --no-binary --plain > {log_path} 2>&1\"")
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

    if args.prepare_scaling:
        exponential_names = get_instance_list("exponential")
        linear_names = get_instance_list("linear")
        n_names = len(exponential_names) + len(linear_names)
        if args.manage:
            # K_range = range(14,21,1)
            k_limit = 20
            limit = 1000
            current_K = 14
            queue_size = get_queue_size()
            batch_size = (current_K + 1) * n_names
            while get_queue_size() < limit - batch_size and current_K <= k_limit:
                for name in exponential_names:
                    prepare_all_datas_for_one_smt_with_decompose(name,current_K,1,force_refresh=False,no_interpolant=args.no_interpolant)
                for name in linear_names:
                    prepare_all_datas_for_one_smt_with_decompose(name,current_K,1,force_refresh=False,no_interpolant=args.no_interpolant)
                current_K += 1
                batch_size = (current_K + 1) * n_names if not args.no_interpolant else n_names
                print(f"Updated K: {current_K}, Queue size: {get_queue_size()}")
                while get_queue_size() > limit - batch_size:
                    time.sleep(600)
            pass
        else:
            K_range = range(1,21,1)

            for K in K_range:
                for name in exponential_names:
                    prepare_all_datas_for_one_smt_with_decompose(name,K,1,force_refresh=False)
                for name in linear_names:
                    prepare_all_datas_for_one_smt_with_decompose(name,K,1,force_refresh=False)
        exit()


    if args.prepare_sequential:
        K = int(args.K)
        # interested_names = interested_names[:2]
        if args.manage:
            batch_size = K + 1
            limit = int(args.limit)
            index = 0
            while index < batch_size * len(interested_names) and index < args.max_index:
                queue_size = get_queue_size()
                print(f"Queue size: {queue_size}, Index: {index}")
                while get_queue_size() < limit - batch_size and index < batch_size * len(interested_names):
                    name = interested_names[index // batch_size]
                    prepare_all_datas_for_one_smt_with_decompose(name,K,args.pddef,force_refresh=False)
                    index += batch_size
                print(f"Updated Index: {index}, Queue size: {get_queue_size()}")
                time.sleep(300)
        else:
            for name in interested_names:
                prepare_all_datas_for_one_smt_with_decompose(name,K,args.pddef,force_refresh=False)
        exit()

    if args.compute_strongest_interpolant:
        exponential_names = get_instance_list("exponential")
        linear_names = get_instance_list("linear")
        interested_names = exponential_names + linear_names
        K_list = [5]
        activate_python = "source ../general/bin/activate"
        for name in interested_names:
            for K in K_list:
                prepare_cnf_obj_cmd = f"{activate_python} && python ./scripts/prepare_single.py --name {name} --K {K} --build_cnf_obj"
                wrapped = f"{prepare_cnf_obj_cmd}"
                os.system(f"sbatch --output=./SlurmLogs/compute_strongest_interpolant/{name}.{K}.build_cnf_obj.log --mem=20g --time=10:00:00 --wrap=\"{wrapped}\"")
                for index in range(K):
                    output=f"./SlurmLogs/compute_strongest_interpolant/{name}.{K}.{index}.log"
                    wrapped = f"{activate_python} && python ./scripts/prepare_single.py --name {name} --K {K} --compute_strongest_interpolant --index {index}"
                    os.system(f"sbatch --output={output} --mem=30g --time=12:00:00 --wrap=\"{wrapped}\"")
        exit()

    if args.prepare_only:
        K = 40
        if args.manage:
            batch_size = K
            limit = int(args.limit)
            index = 0
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
        for name in interested_names[:10]:
        # for name in ["6s0"]:
            if args.remove_absorption_result_caches_first:
                for i in range(K):
                    if os.path.exists(f"ProofDoorBenchmark/absorption_experiments/{name}.k_{K}.i_{i}.check_absorb.json"):
                        os.remove(f"ProofDoorBenchmark/absorption_experiments/{name}.k_{K}.i_{i}.check_absorb.json")
            
            print(f"sbatch --array=0-{K-1} ./scripts/start_absorption_experiments.sh {K} {name}")
            slurm_output = os.popen(f"sbatch --array=0-{K-1} --mem=10g --time=20:00:00 ./scripts/start_absorption_experiments.sh {K} {name} {args.pddef}").read()
            # slurm_output = os.popen("echo 123456").read()
            print(slurm_output)
            slurm_id = int(slurm_output.split()[-1])
            # print(f"Slurm id: {slurm_id}")
            # time.sleep(5)
            wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name} --skip_prepare --pddef {args.pddef}"
            print(f"sbatch --dependency=afterany:{slurm_id} --mem=16g --time=2:00:00 --wrap=\"{wrapped}\"/n")
            os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_{slurm_id}_sum_{K}_{name}.log --dependency=afterany:{slurm_id} --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
            slurm_ids.append(slurm_id)
        print(f"Slurm ids: {slurm_ids}")
        # for name in ready_names:
        #     wrapped = f"{activate_python} && python ./scripts/check_proof_absorb_PD.py --K {K} --target_name {name}"
        #     os.system(f"sbatch --output=./SlurmLogs/absorption_experiments_sum_{K}_{name}.log --mem=10g --time=2:00:00 --wrap=\"{wrapped}\"")
    

if __name__ == "__main__":
    main()