"""
manage_spd_manthan_computation.py

Submit SLURM jobs for the SPD-Manthan interpolant chain.

Each iteration i is one job (run_spd_manthan_step.py) sized for the heaviest
step (Manthan).  When --i is omitted, all iterations 0..K-1 are submitted as
a dependency chain so any failure stops downstream jobs.

Resource note: the job must accommodate all three steps; Manthan dominates.
Default: 20g / 2:00:00.  Tune with --mem / --time.

Examples
--------
# Full chain, one instance
python manage_spd_manthan_computation.py --name cal4 --K 7

# Full chain, all 'linear' instances
python manage_spd_manthan_computation.py --K 7 --category linear

# Continue chain from i=1 for instances where i=0 is already done
python manage_spd_manthan_computation.py --K 7 --category linear --start-after 0

# Single iteration
python manage_spd_manthan_computation.py --name cal4 --K 7 --i 2

# Override resources
python manage_spd_manthan_computation.py --name cal4 --K 7 --mem 40g --time 4:00:00
"""

import csv
import os
import sys
import shutil
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import get_CNF_dir
from utils.utils import get_python_activate_command


REGRESSION_SUMMARY_PATH = "./regression_summary.csv"
SLURM_LOG_DIR           = "./SlurmLogs/compute_spd_manthan"
SKOLEM_DIR_TEMPLATE = "./ProofDoorBenchmark/skolem_spd_manthan/{K}/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_instances_by_category(category):
    instances = []
    with open(REGRESSION_SUMMARY_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['best_model'] == category:
                instances.append(row['instance_name'])
    return list(dict.fromkeys(instances))


def skolem_exists(name, K, i):
    path = os.path.join(SKOLEM_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.skolem.v")
    return os.path.exists(path)


def get_num_iters(name, K):
    """Count 'c iter' markers in the CNF to determine the number of iterations."""
    cnf_path = os.path.join(get_CNF_dir(K), f"{name}.{K}.cnf")
    count = 0
    with open(cnf_path) as f:
        for line in f:
            if line.startswith('c iter'):
                count += 1
    return count


def _sbatch(cmd, job_name, log_path, mem, time, depends_on=None):
    activate = get_python_activate_command()
    wrap     = f"module load boost/1.85.0 && {activate} && {cmd}"
    dep_flag = f" --dependency=afterok:{depends_on}" if depends_on else ""
    sbatch_cmd = (
        f"sbatch"
        f" --job-name={job_name}"
        f" --output={log_path}"
        f" --mem={mem}"
        f" --time={time}"
        f"{dep_flag}"
        f' --wrap="{wrap}"'
    )
    output = os.popen(sbatch_cmd).read().strip()
    return output.split()[-1]


def submit_iter(name, K, i, mem, time, depends_on=None, force=False):
    log_dir = os.path.join(SLURM_LOG_DIR, f"k_{K}")
    os.makedirs(log_dir, exist_ok=True)

    force_flag = " --force" if force else ""
    cmd      = (f"python ./scripts/spd_cadet/run_spd_manthan_step.py"
                f" --name {name} --K {K} --i {i}{force_flag}")
    job_name = f"spdm_{name}.{K}.{i}"
    log_path = os.path.join(log_dir, f"{name}.{K}.%A_{i}.log")

    job_id   = _sbatch(cmd, job_name, log_path, mem, time, depends_on=depends_on)
    dep_note = f" (after {depends_on})" if depends_on else ""
    print(f"  Submitted {job_id}: {job_name}{dep_note}")
    return job_id


def submit_chain(name, K, mem, time, start_i=0, only_i=None, force=False):
    if only_i is not None:
        print(f"  {name}.{K}: single iteration i={only_i}")
        submit_iter(name, K, only_i, mem, time, force=force)
        return

    num_iters = K
    print(f"  {name}.{K}: {num_iters} iterations, chain from i={start_i}")
    prev_jid = None
    for i in range(start_i, num_iters):
        prev_jid = submit_iter(name, K, i, mem, time, depends_on=prev_jid, force=force)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Submit SLURM jobs for the SPD-Manthan interpolant chain.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--name',        help='Instance name (required without --category)')
    parser.add_argument('--K',           type=int, required=True)
    parser.add_argument('--i',           type=int, default=None,
                        help='Submit only this single iteration (default: full chain)')
    parser.add_argument('--category',    choices=['linear', 'exponential', 'polynomial'])
    parser.add_argument('--start-after', type=int, default=None, metavar='N',
                        help=('Filter to instances where iteration N is already complete, '
                              'then start chain from i=N+1'))
    parser.add_argument('--force',       action='store_true',
                        help='Pass --force to jobs (rerun even if outputs exist)')
    parser.add_argument('--mem',         default='20g',      help='Memory per job (default: 20g)')
    parser.add_argument('--time',        default='20:00:00',  help='Wall time per job (default: 2:00:00)')
    args = parser.parse_args()

    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH")

    if args.category is not None:
        instances = get_instances_by_category(args.category)
        if not instances:
            print(f"No instances found for category '{args.category}'.")
            return
        print(f"Found {len(instances)} '{args.category}' instances for K={args.K}.")
    else:
        if args.name is None:
            parser.error("--name is required when --category is not specified")
        instances = [args.name]

    start_i = 0
    if args.start_after is not None:
        n = args.start_after
        completed = [name for name in instances if skolem_exists(name, args.K, n)]
        skipped   = [name for name in instances if name not in completed]
        start_i   = n + 1
        print(f"--start-after {n}: {len(completed)} ready, {len(skipped)} not done yet.")
        if skipped:
            print(f"  Skipping: {skipped}")
        instances = completed

    for name in instances:
        submit_chain(name, args.K, args.mem, args.time,
                     start_i=start_i, only_i=args.i, force=args.force)


if __name__ == '__main__':
    main()
