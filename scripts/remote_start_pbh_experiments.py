import argparse
import os
from utils.utils import get_python_activate_command,group_files_by_basename
from utils.paths import get_branching_order_dir

def main():
    K=10
    activate_python_command = get_python_activate_command()
    file_groups = group_files_by_basename(
            get_branching_order_dir(K),
            K,
            file_extension='.literals')
    log_dir = "pbh_experiments_logs/"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    for basename, files in file_groups.items():
        cmd = f"python scripts/start_proofdoor_branching_heuristic_experiement.py --K {K} --force_name={basename} --top_n 100 --compose"
        wrapped = f"{activate_python_command} && {cmd}"
        log_file = f"{log_dir}/remote_start_pbh_experiments.k_{K}.{basename}.log"
        print(f"basename: {basename}, n_files: {len(files)}")
        print(wrapped)
        os.system(f"sbatch --time=02:00:00 --output={log_file} --mem=10G --wrap=\"{wrapped}\"")

if __name__ == "__main__":
    main()