"""
Submit a dependency chain of Slurm jobs that compute all K strongest PD
interpolants for a single (name, K) instance.

Job i depends on job i-1 (afterok), so they run sequentially.
Each job calls compute_spd.py --name ... --K ... --i ..., which also
verifies the produced interpolant and exits non-zero on failure.
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


SLURM_LOG_DIR      = "./SlurmLogs/compute_spd"
SLURM_LOG_DIR_REV  = "./SlurmLogs/compute_spd7"


def _sbatch(cmd, job_name, log_path, mem, time, depend_id=None):
    """
    Submit a single --wrap job to Slurm.
    Returns the submitted job ID as a string.
    """
    activate = get_python_activate_command()
    wrap = f"{activate} && {cmd}"

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


def submit_spd_chain(name, K, mem="16g", time="4:00:00", reverse=False):
    """
    Submit K Slurm jobs as an afterok dependency chain.

    Forward  (reverse=False): jobs run i=0,1,...,K-1 in order.
    Reverse  (reverse=True):  jobs run i=K-1,K-2,...,0 in order (pddef7).

    Returns the job ID of the last submitted job.
    """
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH")

    log_dir = os.path.join(SLURM_LOG_DIR_REV if reverse else SLURM_LOG_DIR, f"k_{K}")
    os.makedirs(log_dir, exist_ok=True)

    prefix = "spd7" if reverse else "spd"
    indices = range(K - 1, -1, -1) if reverse else range(K)

    wait_id = None
    for i in indices:
        reverse_flag = " --reverse" if reverse else ""
        compute_cmd = (
            f"python ./scripts/strongest_pd/compute_spd.py"
            f" --name {name} --K {K} --i {i}{reverse_flag}"
        )
        job_name = f"{prefix}_{name}.{K}.{i}"
        log_path = os.path.join(log_dir, f"{name}.{K}.%A_{i}.log")

        job_id = _sbatch(compute_cmd, job_name, log_path, mem, time, depend_id=wait_id)
        print(f"  Submitted job {job_id}: {job_name}")
        wait_id = job_id

    direction = "reverse" if reverse else "forward"
    print(f"Submitted SPD {direction} chain for {name}.{K} ({K} jobs); last job id: {wait_id}")
    return wait_id


def get_successful_instances(K, instances=None):
    """
    For the given K, return instance names where all K indices (0..K-1) have
    a log containing 'Interpolant validity check passed'.
    If instances is None, discover instance names from the log directory.
    """
    log_dir = os.path.join(SLURM_LOG_DIR, f"k_{K}")
    if not os.path.isdir(log_dir):
        print(f"Log directory not found: {log_dir}")
        return []

    if instances is None:
        marker = f".{K}."
        seen = set()
        for f in glob_mod.glob(os.path.join(log_dir, f"*.{K}.*_*.log")):
            basename = os.path.basename(f)
            idx = basename.find(marker)
            if idx >= 0:
                seen.add(basename[:idx])
        instances = list(seen)

    successful = []
    for name in sorted(instances):
        all_ok = True
        for i in range(K):
            logs = sorted(glob_mod.glob(os.path.join(log_dir, f"{name}.{K}.*_{i}.log")))
            if not logs:
                all_ok = False
                break
            success_str = f"Interpolant validity check passed for {name}.{K}.{i}"
            found = any(success_str in open(log).read() for log in logs)
            if not found:
                all_ok = False
                break
        if all_ok:
            successful.append(name)

    return successful


def get_forward_count_instances(instances, min_count):
    """
    Return instances where the total number of forward interpolant files
    (interpolants_def5/{K}/{name}.{K}.{i}.interpolant) across ALL K values
    is >= min_count.
    """
    result = []
    for name in sorted(instances):
        count = len(glob_mod.glob(
            f"./ProofDoorBenchmark/interpolants_def5/*/{name}.*.*.interpolant"
        ))
        if count >= min_count:
            result.append(name)
    return result


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Submit a Slurm dependency chain to compute all strongest PD "
            "interpolants for one (name, K) instance, or for all instances "
            "of a given regression category."
        )
    )
    parser.add_argument('--name',     help='Instance name (required without --category)')
    parser.add_argument('--K',        type=int, required=True, help='K value')
    parser.add_argument('--category', choices=['linear', 'exponential'],
                        help='Submit jobs for all instances with this regression category')
    parser.add_argument('--mem',  default='20g', help='Memory per job (default: 20g)')
    parser.add_argument('--time', default='15:00:00', help='Wall-clock time per job (default: 15:00:00)')
    parser.add_argument('--show_success', action='store_true',
                        help='Print instance names where all K indices succeeded; '
                             'uses --category to filter, or scans the log directory if omitted')
    parser.add_argument('--use_success_only', type=int, metavar='NUM',
                        help='Only submit jobs for instances where all NUM indices succeeded for K=NUM')
    parser.add_argument('--reverse', action='store_true',
                        help='Submit reverse chains (pddef7): jobs run i=K-1 down to 0')
    parser.add_argument('--min_forward_success', type=int, metavar='X',
                        help='Only submit for instances where forward success count >= X (for the current K)')
    args = parser.parse_args()

    if args.show_success:
        if args.category is not None:
            instances = get_instances_by_category(args.category)
        elif args.name is not None:
            instances = [args.name]
        else:
            instances = None  # discover from log dir
        successful = get_successful_instances(args.K, instances)
        if successful:
            print(f"{len(successful)} instance(s) fully successful for K={args.K}:")
            for name in successful:
                print(f"  {name}")
        else:
            print(f"No fully successful instances found for K={args.K}.")
        return

    if args.category is not None:
        instances = get_instances_by_category(args.category)
        if not instances:
            print(f"No instances found for category '{args.category}'.")
            return
        if args.use_success_only is not None:
            num = args.use_success_only
            instances = get_successful_instances(num, instances)
            if not instances:
                print(f"No instances fully succeeded for K={num}.")
                return
            print(f"{len(instances)} instance(s) passed K={num}; submitting K={args.K} chains...")
        elif args.min_forward_success is not None:
            instances = get_forward_count_instances(instances, args.min_forward_success)
            if not instances:
                print(f"No instances with >= {args.min_forward_success} forward successes for K={args.K}.")
                return
            print(f"{len(instances)} instance(s) have >= {args.min_forward_success} forward successes; "
                  f"submitting K={args.K} chains...")
        else:
            print(f"Found {len(instances)} '{args.category}' instances. Submitting K={args.K} chains...")
        for name in instances:
            submit_spd_chain(name, args.K, mem=args.mem, time=args.time, reverse=args.reverse)
    else:
        if args.name is None:
            parser.error("--name is required when --category is not specified")
        if args.min_forward_success is not None:
            instances = get_forward_count_instances([args.name], args.min_forward_success)
            if not instances:
                print(f"{args.name} does not have >= {args.min_forward_success} forward successes for K={args.K}; skipping.")
                return
        submit_spd_chain(args.name, args.K, mem=args.mem, time=args.time, reverse=args.reverse)


if __name__ == '__main__':
    main()
