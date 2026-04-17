"""
Submit a dependency chain of Slurm jobs that compute all K strongest PD
interpolants (via CADET) for a single (name, K) instance.

Job i depends on job i-1 (afterok), so they run sequentially.
Each job calls compute_spd_cadet.py --name ... --K ... --i ...
"""

import csv
import glob as glob_mod
import os
import sys
import shutil
import argparse

# Allow imports from the scripts/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.utils import get_python_activate_command


REGRESSION_SUMMARY_PATH = "./regression_summary.csv"
SLURM_LOG_DIR = "./SlurmLogs/compute_spd_cadet"


def get_instances_by_category(category):
    """
    Read regression_summary.csv and return instance names whose best_model
    matches the given category ('linear' or 'exponential').
    """
    instances = []
    with open(REGRESSION_SUMMARY_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['best_model'] == category:
                instances.append(row['instance_name'])
    return instances


def _sbatch(cmd, job_name, log_path, mem, time, depend_id=None):
    """
    Submit a single --wrap job to Slurm.
    Returns the submitted job ID as a string.
    """
    activate = get_python_activate_command()
    wrap = f"module load boost/1.85.0 && {activate} && {cmd}"

    sbatch_cmd = (
        f"sbatch"
        f" --job-name={job_name}"
        f" --output={log_path}"
        f" --mem={mem}"
        f" --time={time}"
    )
    if depend_id is not None:
        sbatch_cmd += f" --dependency=afterok:{depend_id}"
    sbatch_cmd += f' --wrap="{wrap}"'

    job_id = os.popen(sbatch_cmd).read().strip().split()[-1]
    return job_id


def submit_spd_cadet_chain(name, K, mem="16g", time="4:00:00"):
    """
    Submit K Slurm jobs as an afterok dependency chain.
    Returns the job ID of the last submitted job.
    """
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH")

    log_dir = os.path.join(SLURM_LOG_DIR, f"k_{K}")
    os.makedirs(log_dir, exist_ok=True)

    wait_id = None
    for i in range(K):
        compute_cmd = (
            f"python ./scripts/spd_cadet/compute_spd_skolem.py"
            f" --name {name} --K {K} --i {i} --backend manthan"
        )
        job_name = f"spdc_{name}.{K}.{i}"
        log_path = os.path.join(log_dir, f"{name}.{K}.%A_{i}.log")

        job_id = _sbatch(compute_cmd, job_name, log_path, mem, time, depend_id=wait_id)
        print(f"  Submitted job {job_id}: {job_name}")
        wait_id = job_id

    print(f"Submitted SPD-CADET chain for {name}.{K} ({K} jobs); last job id: {wait_id}")
    return wait_id


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Submit a Slurm dependency chain to compute all strongest PD "
            "interpolants (via CADET) for one (name, K) instance, or for all "
            "instances of a given regression category."
        )
    )
    parser.add_argument('--name',     help='Instance name (required without --category)')
    parser.add_argument('--K',        type=int, required=True, help='K value')
    parser.add_argument('--category', choices=['linear', 'exponential'],
                        help='Submit jobs for all instances with this regression category')
    parser.add_argument('--mem',  default='20g', help='Memory per job (default: 20g)')
    parser.add_argument('--time', default='15:00:00', help='Wall-clock time per job (default: 15:00:00)')
    args = parser.parse_args()

    if args.category is not None:
        instances = get_instances_by_category(args.category)
        if not instances:
            print(f"No instances found for category '{args.category}'.")
            return
        print(f"Found {len(instances)} '{args.category}' instances. Submitting K={args.K} chains...")
        for name in instances:
            submit_spd_cadet_chain(name, args.K, mem=args.mem, time=args.time)
    else:
        if args.name is None:
            parser.error("--name is required when --category is not specified")
        submit_spd_cadet_chain(args.name, args.K, mem=args.mem, time=args.time)


if __name__ == '__main__':
    main()
