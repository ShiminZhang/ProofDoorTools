"""
Compute consecutive-interpolant dependence for pddef=5.

Files live in ProofDoorBenchmark/interpolants_def5/{K}/{name}.{K}.{index}.interpolant.
K does not affect the interpolant content — the same index across any K gives the same result.
For each instance we collect all available indices across all K directories, sort them, and
compute ub_dependence between each consecutive valid pair (skipping files with 'e' lines).

Output: ProofDoorBenchmark/interpolant_dependence_pddef_5/{name}.csv
Columns: name, K (= index), i (= index), ub_dependence

Usage:
  # Process all instances in a category (local, sequential):
  python scripts/experiments/compute_dependence_pddef5.py --category linear

  # Submit one Slurm job per instance:
  python scripts/experiments/compute_dependence_pddef5.py --category linear --manage

  # Single instance (used by --manage jobs):
  python scripts/experiments/compute_dependence_pddef5.py --instance 6s41
"""

import argparse
import csv
import os
import sys
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

INTERPOLANT_DIR = "./ProofDoorBenchmark/interpolants_def5"
OUTPUT_DIR = "./ProofDoorBenchmark/interpolant_dependence_pddef_5"
REGRESSION_SUMMARY = "./regression_summary.csv"
SLURM_LOG_DIR = "./SlurmLogs/compute_dependence_pddef5"


# ---------------------------------------------------------------------------
# Instance list helpers
# ---------------------------------------------------------------------------

def load_instance_names(summary_path: str, category: Optional[str]) -> List[str]:
    names = []
    with open(summary_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("instance_name") or "").strip()
            if not name:
                continue
            if category and category != "all":
                cat = (row.get("best_model") or row.get("category") or "").strip().lower()
                if cat != category.lower():
                    continue
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# QDIMACS reader
# ---------------------------------------------------------------------------

def read_qdimacs_clauses(path: str) -> Optional[List[List[int]]]:
    """Return clauses from a QDIMACS file, or None if an 'e' quantifier line is found."""
    clauses = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ("c", "p", "a"):
                continue
            if line[0] == "e":
                return None
            lits = [int(x) for x in line.split() if x != "0"]
            if lits:
                clauses.append(lits)
    return clauses


# ---------------------------------------------------------------------------
# Dependence computation
# ---------------------------------------------------------------------------

def get_upper_bound_of_dependence(
    reference: List[List[int]], interpolant: List[List[int]]
) -> int:
    """Max over interpolant clauses of (# reference clauses sharing >= 1 literal)."""
    lit_to_count: Dict[int, int] = {}
    for clause in reference:
        for lit in clause:
            lit_to_count[lit] = lit_to_count.get(lit, 0) + 1
    max_count = 0
    for clause in interpolant:
        seen: set = set()
        for lit in clause:
            if lit in lit_to_count:
                seen.add(lit)
        if len(seen) > max_count:
            max_count = len(seen)
    return max_count


def collect_index_to_path(name: str) -> Dict[int, str]:
    """Scan all K directories and return {index: first_found_path}."""
    index_to_path: Dict[int, str] = {}
    if not os.path.isdir(INTERPOLANT_DIR):
        return index_to_path
    for k_name in os.listdir(INTERPOLANT_DIR):
        k_dir = os.path.join(INTERPOLANT_DIR, k_name)
        if not k_name.isdigit() or not os.path.isdir(k_dir):
            continue
        prefix = f"{name}."
        suffix = ".interpolant"
        for fname in os.listdir(k_dir):
            if not fname.startswith(prefix) or not fname.endswith(suffix):
                continue
            inner = fname[len(prefix):-len(suffix)]  # "{K}.{index}"
            parts = inner.split(".")
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1])
                if idx not in index_to_path:
                    index_to_path[idx] = os.path.join(k_dir, fname)
    return index_to_path


def compute_instance(name: str) -> List[Tuple[str, int, int, int]]:
    """Return result rows for one instance."""
    index_to_path = collect_index_to_path(name)
    rows: List[Tuple[str, int, int, int]] = []
    prev_clauses: Optional[List[List[int]]] = None
    for i in sorted(index_to_path):
        try:
            clauses = read_qdimacs_clauses(index_to_path[i])
        except Exception:
            prev_clauses = None
            continue
        if clauses is None:  # has 'e' line — invalid
            prev_clauses = None
            continue
        if prev_clauses is not None:
            ub = get_upper_bound_of_dependence(prev_clauses, clauses)
            rows.append((name, i, i, ub))
        prev_clauses = clauses
    return rows


def write_instance_csv(name: str, rows: List[Tuple[str, int, int, int]]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{name}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "K", "i", "ub_dependence"])
        w.writerows(rows)
    return out_path


# ---------------------------------------------------------------------------
# Main modes
# ---------------------------------------------------------------------------

def run_single(name: str) -> None:
    rows = compute_instance(name)
    out_path = write_instance_csv(name, rows)
    print(f"[pddef5-dep] {name}: {len(rows)} rows -> {out_path}")


def run_all(names: List[str]) -> None:
    for name in tqdm(names, desc="computing dependence", unit="inst"):
        run_single(name)


def run_manage(names: List[str], category: str, summary: str, mem: str, time_limit: str) -> None:
    import shutil
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found; cannot use --manage")
    os.makedirs(SLURM_LOG_DIR, exist_ok=True)
    script = os.path.abspath(__file__)
    cmds = []
    for name in names:
        log = os.path.join(SLURM_LOG_DIR, f"{name}.%j.log")
        cmd = (
            f"sbatch --output={log} --mem={mem} --time={time_limit} "
            f"--wrap=\"python {script} --instance {name}\""
        )
        cmds.append(cmd)
    print(f"[pddef5-dep] submitting {len(cmds)} jobs...")
    for cmd in cmds:
        os.system(cmd)
    print(f"[pddef5-dep] done submitting.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute pddef=5 interpolant dependence.")
    parser.add_argument("--instance", type=str, default=None,
                        help="Process a single instance (used by --manage jobs).")
    parser.add_argument("--category", type=str, default="all",
                        help="Instance category filter (default: all).")
    parser.add_argument("--summary", type=str, default=REGRESSION_SUMMARY,
                        help="Path to regression_summary.csv.")
    parser.add_argument("--manage", action="store_true",
                        help="Submit one Slurm job per instance instead of running locally.")
    parser.add_argument("--mem", type=str, default="16g",
                        help="Slurm memory per job (default: 16g).")
    parser.add_argument("--time", type=str, default="2:00:00",
                        help="Slurm time limit per job (default: 2:00:00).")
    args = parser.parse_args()

    if args.instance is not None:
        run_single(args.instance)
        return

    names = load_instance_names(args.summary, args.category)
    if not names:
        print(f"[pddef5-dep] no instances found in {args.summary} for category={args.category}")
        sys.exit(1)
    print(f"[pddef5-dep] {len(names)} instances, category={args.category}")

    if args.manage:
        run_manage(names, args.category, args.summary, args.mem, args.time)
    else:
        run_all(names)


if __name__ == "__main__":
    main()
