import time
import os
import argparse
import csv
from utils.paths import get_CNF_dir,get_interpolant_dir, get_shuffled_cnf_dir, get_solving_time_dir
from utils.catagory import get_instance_list
from utils.utils import get_python_activate_command
from utils.tosmt import cnf_to_smt2_n_way
from prepare_single import prepare_all_datas,set_debug, prepare_all_datas_for_one_smt, prepare_all_datas_for_one_smt_with_decompose
from prepare_single import prepare_for_interpolant_computation, prepare_interpolant_only
from tqdm import tqdm
import random

def get_queue_size():
    return int(os.popen("squeue -u $USER -h -r -t RUNNING,PENDING | wc -l").read())

def count_lines(filepath):
    with open(filepath, 'rb') as f:  # open in binary mode for performance
        return sum(1 for line in f)

def load_regression_summary_tasks(csv_path: str, category_filter=None):
    """
    Load (instance, K) pairs from regression_summary.csv.

    Expected columns: instance_name, local_max_k.
    Rows with local_max_k < 0 are skipped by default.
    """
    tasks = []
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"regression summary CSV not found: {csv_path}")
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if "instance_name" not in reader.fieldnames or "local_max_k" not in reader.fieldnames:
            raise ValueError(
                f"Unexpected CSV columns in {csv_path}: {reader.fieldnames}. "
                "Need at least: instance_name, local_max_k"
            )
        for row in reader:
            name = (row.get("instance_name") or "").strip()
            if not name:
                continue
            if category_filter is not None:
                # regression_summary.csv uses "best_model" as category label
                # (linear/polynomial/exponential/None). We normalize None -> "none".
                best_model = (row.get("best_model") or "").strip()
                best_model_norm = "none" if best_model.lower() == "none" else best_model.lower()
                if best_model_norm not in category_filter:
                    continue
            try:
                k = int(str(row.get("local_max_k", "")).strip())
            except Exception:
                continue
            if k < 0:
                continue
            tasks.append((name, k))
    # Deduplicate while preserving order.
    seen = set()
    deduped = []
    for name, k in tasks:
        key = (name, k)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped

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
    parser.add_argument("--from_regression_summary", action="store_true", default=False)
    parser.add_argument("--regression_summary_path", action="store", default="regression_summary.csv")
    parser.add_argument("--check_interpolants", action="store_true", default=False)
    parser.add_argument("--manage", action="store_true", default=False)
    parser.add_argument("--limit", action="store", default=1000)
    parser.add_argument("--max_index",type=int, action="store", default=10000000)
    parser.add_argument("--pddef", action="store", default=1)
    parser.add_argument("--debug", action="store_true", default=False)
    parser.add_argument("--no_interpolant", action="store_true", default=False)
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--permute_and_run", action="store_true", default=False)
    parser.add_argument("--prepare_sequential", action="store_true", default=False)
    parser.add_argument("--prepare_scaling", action="store_true", default=False)
    parser.add_argument("--force_refresh", action="store_true", default=False)
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
        interested_names = [args.focus_name]
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
        # K = int(args.K)
        # K = 100
        if args.focus_name is not None:
            interested_names = [args.focus_name]
        # interested_names = args
        # interested_names = ["6s339rb22"]
        # interested_names = interested_names[:2]
        if args.manage:
            print(f"Preparing {len(interested_names)} instances")
            cmd = get_python_activate_command()
            reverse_flag = "--reverse" if args.reverse else ""
            for instance in interested_names[:10]:
                cmd = f"{cmd} && python ./scripts/prepare.py --focus_name {instance} --K {K} --prepare_sequential {reverse_flag}"
                os.system(f"sbatch --output=./SlurmLogs/prepare_sequential/{instance}.{K}.prepare_sequential.log --mem=10g --time=20:00:00 --wrap=\"{cmd}\"")
            # batch_size = K + 1
            # limit = int(args.limit)
            # index = 0
            # while index < batch_size * len(interested_names) and index < args.max_index:
            #     queue_size = get_queue_size()
            #     print(f"Queue size: {queue_size}, Index: {index}")
            #     while get_queue_size() < limit - batch_size and index < batch_size * len(interested_names):
            #         name = interested_names[index // batch_size]
            #         prepare_all_datas_for_one_smt_with_decompose(name,K,args.pddef,force_refresh=False)
            #         index += batch_size
            #     print(f"Updated Index: {index}, Queue size: {get_queue_size()}")
            #     time.sleep(300)
        else:
            print(f"Preparing {len(interested_names)} instances")
            for name in interested_names:
                print(f"Preparing {name}.{K} with pddef {args.pddef}")
                prepare_for_interpolant_computation(name,K,force_refresh=True,pddef=int(args.pddef),reverse=args.reverse)
                for index in range(K):
                    prepare_interpolant_only(name,K,index,pddef=int(args.pddef),force_refresh=True,reverse=args.reverse)
        exit()

    if args.compute_strongest_interpolant:
        # Use the already-computed interested_names (category/focus_name).
        if args.from_regression_summary:
            # Apply --category filter using regression_summary.csv's "best_model" column.
            category_filter = None
            if args.category is not None and args.category != "all":
                requested = [c.strip().lower() for c in str(args.category).split(",") if c.strip()]
                if requested:
                    category_filter = set(requested)
            tasks = load_regression_summary_tasks(args.regression_summary_path, category_filter=category_filter)
            if args.focus_name is not None:
                tasks = [(n, k) for (n, k) in tasks if n == args.focus_name]
            if not tasks:
                print("No (instance, K) tasks loaded from regression summary (after filtering).")
                exit()
        else:
            K_list = [int(args.K)]
            tasks = [(name, K_list[0]) for name in interested_names]
        # random.shuffle(tasks)
        # tasks = tasks[:20]
        activate_python = "source ../../general/bin/activate"
        force_refresh_flag = "--force_refresh" if args.force_refresh else ""
        os.makedirs("./SlurmLogs/compute_strongest_interpolant", exist_ok=True)
        for name, K in tasks:
            # Strongest interpolants are sequential: index i depends on (i-1).
            # So submit ONE job per (instance, K) to compute all indices in order.
            output = f"./SlurmLogs/compute_strongest_interpolant/{name}.{K}.all.log"
            wrapped = (
                f"{activate_python} && python ./scripts/prepare_single.py "
                f"--name {name} --K {K} --compute_strongest_interpolants {force_refresh_flag}"
            )
            os.system(f"sbatch --output={output} --mem=2g --time=2:00:00 --wrap=\"{wrapped}\"")
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
    

    activate_python = "source ../../general/bin/activate"
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