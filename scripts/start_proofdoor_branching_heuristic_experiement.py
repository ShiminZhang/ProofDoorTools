import argparse
import os
from utils.paths import get_branching_order_dir,get_cnfs_dir,get_exp_pbh_dir
from utils.utils import get_python_activate_command,generate_cnf

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--force_name", type=str, required=False)
    parser.add_argument("--top_n", type=int, default=100)
    parser.add_argument("--original", action="store_true", default=False)
    parser.add_argument("--compose", action="store_true", default=False)
    args = parser.parse_args()
    if args.compose:
        activate_python_command = get_python_activate_command()
        os.system(f"{activate_python_command} && python scripts/extract_branching_order_from_interpolants.py --K {args.K} --use_cache --extract_dir --force_name {args.force_name}")
        os.system(f"{activate_python_command} && python scripts/start_proofdoor_branching_heuristic_experiement.py --K {args.K} --force_name={args.force_name} --top_n {args.top_n}")
        os.system(f"{activate_python_command} && python scripts/start_proofdoor_branching_heuristic_experiement.py --K {args.K} --force_name={args.force_name} --top_n {args.top_n} --original")
        return
    branching_order_dir = get_branching_order_dir(args.K)
    for file in os.listdir(branching_order_dir):
        if file.endswith('.branching_order'):
            if args.force_name and file.split('.')[0] != args.force_name:
                continue
            branching_order_file = os.path.join(branching_order_dir, file)
            basename = file.split('.')[0]
            cnf_file = os.path.join(get_cnfs_dir(args.K), f"{basename}.{args.K}.cnf")
            if not os.path.exists(cnf_file):
                generate_cnf(f"{basename}.{args.K}.cnf")
            solver = "./solvers/minisat_pbh"
            if args.original:
                log_file = f"{basename}.k_{args.K}.top_{args.top_n}.original.minisat.log"
            else:
                log_file = f"{basename}.k_{args.K}.top_{args.top_n}.minisat.log"
            exp_pbh_dir = get_exp_pbh_dir(args.K)
            log_file = os.path.join(exp_pbh_dir, log_file)
            print(f"Running {basename} with {solver} {cnf_file} -PDB_top_n={args.top_n} -branch-file: {branching_order_file} > {log_file}")
            if args.original:
                os.system(f"{solver} {cnf_file} -PDB_top_n={args.top_n} > {log_file}")
            else:
                os.system(f"{solver} {cnf_file} -PDB_top_n={args.top_n} -branch-file={branching_order_file} > {log_file}")
            

if __name__ == "__main__":
    main()