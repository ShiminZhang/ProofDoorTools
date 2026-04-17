"""
Submit a dependency chain of Slurm jobs that compute all K minimum PD
interpolants for a single (name, K) instance.

Job i depends on job i-1 (afterok), so they run sequentially from 0 to K-1
(same forward direction as SPD).
Each job calls compute_mpd.py --name ... --K ... --i ..., which also
verifies the produced interpolant and exits non-zero on failure.
"""

import csv
import glob as glob_mod
import os
import sys
import shutil
import argparse
import shlex

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


SLURM_LOG_DIR = "./SlurmLogs/compute_mpd"
SUMMARY_LOG_DIR = "./SlurmLogs/compute_mpd_summary"
RESULTS_DIR = "./results"


def _sbatch(cmd, job_name, log_path, mem, time, depend_ids=None, dependency_type="afterok"):
    """
    Submit a single --wrap job to Slurm.
    Returns the submitted job ID as a string.
    """
    activate = get_python_activate_command()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    wrap = f"cd {repo_root} && {activate} && source ./.env && {cmd}"

    sbatch_cmd = (
        f"sbatch"
        f" --job-name={job_name}"
        f" --output={log_path}"
        f" --mem={mem}"
        f" --time={time}"
    )
    if depend_ids:
        if isinstance(depend_ids, str):
            depend_ids = [depend_ids]
        dep_expr = ":".join(str(job_id) for job_id in depend_ids)
        sbatch_cmd += f" --dependency={dependency_type}:{dep_expr}"
    sbatch_cmd += f' --wrap="{wrap}"'

    job_id = os.popen(sbatch_cmd).read().strip().split()[-1]
    return job_id


def submit_mpd_chain(
    name,
    K,
    mem="16g",
    time="4:00:00",
    backend="preprocess",
    conversion_mode="slurm",
    initialbound=50,
    eliminatebound=16000,
    eliminaterounds=2000,
    eliminateclslim=100000,
    eliminateocclim=2000000,
    eliminateeffort=100000,
):
    """
    Submit K Slurm jobs as a forward afterok dependency chain (0 → 1 → … → K-1).
    Returns the job ID of the last submitted job.
    """
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH")

    log_dir = os.path.join(SLURM_LOG_DIR, f"k_{K}")
    os.makedirs(log_dir, exist_ok=True)

    wait_id = None
    for i in range(K):
        compute_cmd_parts = [
            "python", "./scripts/minimum_pd/compute_mpd.py",
            "--name", name,
            "--K", str(K),
            "--i", str(i),
            "--backend", backend,
            "--conversion_mode", conversion_mode,
        ]
        if initialbound is not None:
            compute_cmd_parts.extend(["--initialbound", str(initialbound)])
        if eliminatebound is not None:
            compute_cmd_parts.extend(["--eliminatebound", str(eliminatebound)])
        if eliminaterounds is not None:
            compute_cmd_parts.extend(["--eliminaterounds", str(eliminaterounds)])
        if eliminateclslim is not None:
            compute_cmd_parts.extend(["--eliminateclslim", str(eliminateclslim)])
        if eliminateocclim is not None:
            compute_cmd_parts.extend(["--eliminateocclim", str(eliminateocclim)])
        if eliminateeffort is not None:
            compute_cmd_parts.extend(["--eliminateeffort", str(eliminateeffort)])
        compute_cmd = " ".join(shlex.quote(part) for part in compute_cmd_parts)
        job_name = f"mpd_{name}.{K}.{i}"
        log_path = os.path.join(log_dir, f"{name}.{K}.%A_{i}.log")

        job_id = _sbatch(compute_cmd, job_name, log_path, mem, time, depend_ids=wait_id)
        print(f"  Submitted job {job_id}: {job_name}")
        wait_id = job_id

    print(f"Submitted MPD chain for {name}.{K} ({K} jobs); last job id: {wait_id}")
    return wait_id


def _summary_output_path(name, category, K, backend, conversion_mode):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if name is not None:
        scope = name
    elif category is not None:
        scope = category
    else:
        scope = "all"
    return os.path.join(
        RESULTS_DIR,
        f"mpd_status_{scope}_k_{K}_{backend}_{conversion_mode}.csv",
    )


def submit_summary_job(
    *,
    K,
    name=None,
    category=None,
    backend="preprocess",
    conversion_mode="slurm",
    depend_ids=None,
    mem="8g",
    time="00:30:00",
):
    if not depend_ids:
        return None

    os.makedirs(SUMMARY_LOG_DIR, exist_ok=True)
    output_csv = _summary_output_path(name, category, K, backend, conversion_mode)
    summary_cmd_parts = [
        "python", "./scripts/minimum_pd/stat_mpd.py",
        "--K", str(K),
        "--output", output_csv,
    ]
    if name is not None:
        summary_cmd_parts.extend(["--name", name])
    if category is not None:
        summary_cmd_parts.extend(["--category", category])
    summary_cmd = " ".join(shlex.quote(part) for part in summary_cmd_parts)

    scope = name or category or "all"
    job_name = f"mpd_summary_{scope}.{K}"
    log_path = os.path.join(SUMMARY_LOG_DIR, f"{scope}.{K}.%A.log")
    job_id = _sbatch(
        summary_cmd,
        job_name,
        log_path,
        mem,
        time,
        depend_ids=depend_ids,
        dependency_type="afterany",
    )
    print(f"Submitted summary job {job_id}: {job_name}")
    print(f"Summary CSV will be written to: {output_csv}")
    return job_id


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


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Submit a Slurm forward dependency chain to compute all minimum PD "
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
    parser.add_argument('--backend', choices=['preprocess', 'not_b', 'z3_not_b'],
                        default='preprocess',
                        help='Backend passed through to compute_mpd.py')
    parser.add_argument('--conversion_mode', choices=['slurm', 'local'],
                        default='slurm',
                        help='Conversion mode passed through to compute_mpd.py')
    parser.add_argument('--initialbound', type=int, default=50,
                        help='Override preprocess initial additional_clauses bound')
    parser.add_argument('--eliminatebound', type=int, default=16000,
                        help='Override kissat eliminatebound')
    parser.add_argument('--eliminaterounds', type=int, default=2000,
                        help='Override kissat eliminaterounds')
    parser.add_argument('--eliminateclslim', type=int, default=100000,
                        help='Override kissat eliminateclslim')
    parser.add_argument('--eliminateocclim', type=int, default=2000000,
                        help='Override kissat eliminateocclim')
    parser.add_argument('--eliminateeffort', type=int, default=100000,
                        help='Override kissat eliminateeffort')
    parser.add_argument('--show_success', action='store_true',
                        help='Print instance names where all K indices succeeded; '
                             'uses --category to filter, or scans the log directory if omitted')
    parser.add_argument('--use_success_only', type=int, metavar='NUM',
                        help='Only submit jobs for instances where all NUM indices succeeded for K=NUM')
    parser.add_argument('--no_summary', action='store_true',
                        help='Do not auto-submit a dependent summary job')
    args = parser.parse_args()

    if args.backend == 'z3_not_b':
        args.backend = 'not_b'
    if args.conversion_mode != 'slurm' and args.backend == 'preprocess':
        args.backend = 'not_b'
    if args.backend == 'not_b' and args.conversion_mode == 'slurm':
        parser.error(
            "--backend not_b requires --conversion_mode local in batch mode, "
            "otherwise job i+1 may start before index i conversion finishes"
        )

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
        else:
            print(f"Found {len(instances)} '{args.category}' instances. Submitting K={args.K} chains...")
        last_job_ids = []
        for name in instances:
            last_job_id = submit_mpd_chain(
                name,
                args.K,
                mem=args.mem,
                time=args.time,
                backend=args.backend,
                conversion_mode=args.conversion_mode,
                initialbound=args.initialbound,
                eliminatebound=args.eliminatebound,
                eliminaterounds=args.eliminaterounds,
                eliminateclslim=args.eliminateclslim,
                eliminateocclim=args.eliminateocclim,
                eliminateeffort=args.eliminateeffort,
            )
            if last_job_id:
                last_job_ids.append(last_job_id)
        if not args.no_summary:
            submit_summary_job(
                K=args.K,
                category=args.category,
                backend=args.backend,
                conversion_mode=args.conversion_mode,
                depend_ids=last_job_ids,
            )
    else:
        if args.name is None:
            parser.error("--name is required when --category is not specified")
        last_job_id = submit_mpd_chain(
            args.name,
            args.K,
            mem=args.mem,
            time=args.time,
            backend=args.backend,
            conversion_mode=args.conversion_mode,
            initialbound=args.initialbound,
            eliminatebound=args.eliminatebound,
            eliminaterounds=args.eliminaterounds,
            eliminateclslim=args.eliminateclslim,
            eliminateocclim=args.eliminateocclim,
            eliminateeffort=args.eliminateeffort,
        )
        if not args.no_summary:
            submit_summary_job(
                K=args.K,
                name=args.name,
                backend=args.backend,
                conversion_mode=args.conversion_mode,
                depend_ids=[last_job_id] if last_job_id else None,
            )


if __name__ == '__main__':
    main()
