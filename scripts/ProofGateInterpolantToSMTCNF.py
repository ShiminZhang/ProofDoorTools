#!/usr/bin/env python3
"""
Convert pddef=3 ("proofgate") interpolants from DIMACS-like `.interpolant` into
standard DIMACS CNF (`.smtcnf` filename kept for downstream paths).

Input (per index):
  ProofDoorBenchmark/interpolants_def3/<K>/<instance>.<K>.<i>.interpolant
Each line is a clause in DIMACS form, typically ending with trailing 0.

Output:
  ProofDoorBenchmark/interpolant_as_cnfs_3/<K>/<instance>.<K>.<i>.smtcnf
Standard DIMACS CNF: header "p cnf <num_variables> <num_clauses>", then one line
per clause with space-separated integer literals ending with 0.
"""

import argparse
import csv
import os
from tqdm import tqdm
from typing import Dict, Iterable, List, Optional, Set, Tuple

from utils.paths import get_interpolant_cnf_dir, get_interpolant_dir


def _parse_dimacs_clause_line(line: str) -> List[int]:
    lits: List[int] = []
    for tok in line.strip().split():
        if tok == "0":
            break
        lits.append(int(tok))
    return lits


def convert_one(instance: str, K: int, index: int, force_refresh: bool = False) -> str:
    inp_dir = get_interpolant_dir(K, 3)
    out_dir = get_interpolant_cnf_dir(K, 3)
    in_path = os.path.join(inp_dir, f"{instance}.{K}.{index}.interpolant")
    out_path = os.path.join(out_dir, f"{instance}.{K}.{index}.smtcnf")

    if (not force_refresh) and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        print(f"[SKIP] {out_path} exists")
        return out_path

    if not os.path.exists(in_path) or os.path.getsize(in_path) == 0:
        raise FileNotFoundError(f"Interpolant file missing/empty: {in_path}")

    clauses: List[List[int]] = []
    with open(in_path, "r") as fin:
        for raw in fin:
            line = raw.strip()
            if not line or line.startswith("c") or line.startswith("p"):
                continue
            lits = _parse_dimacs_clause_line(line)
            if not lits:
                continue
            clauses.append(lits)

    nclauses = len(clauses)
    nvars = 0
    for cl in clauses:
        for lit in cl:
            nvars = max(nvars, abs(lit))

    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as fout:
        fout.write(f"p cnf {nvars} {nclauses}\n")
        for lits in clauses:
            fout.write(" ".join(str(l) for l in lits) + " 0\n")

    # if nclauses == 0:
    #     print(f"[WARN] wrote 0 clauses to {out_path}")
    # else:
    #     print(f"[OK] wrote {nclauses} clauses (nvars={nvars}) to {out_path}")
    return out_path


def _load_instance_k_pairs(linear_csv: str, exponential_csv: str) -> Set[Tuple[str, int]]:
    """Read (instance_name, K) from both summary CSVs and return deduplicated set."""
    pairs: Set[Tuple[str, int]] = set()
    for path in (linear_csv, exponential_csv):
        if not os.path.isfile(path):
            continue
        with open(path, "r", newline="") as f:
            for row in csv.DictReader(f):
                name = row.get("instance_name", "").strip()
                k_str = row.get("K", "").strip()
                if name and k_str:
                    pairs.add((name, int(k_str)))
    return pairs


def _discover_interpolant_tasks(pddef: int = 3) -> List[Tuple[str, int, int]]:
    """
    Discover all available (instance, K, index) directly from the interpolant tree:
      ProofDoorBenchmark/interpolants_def{pddef}/<K>/<instance>.<K>.<i>.interpolant

    This is the most reliable source for '--all' because it reflects what exists
    on disk, regardless of what summary CSVs include/exclude.
    """
    root = os.path.join("./ProofDoorBenchmark", f"interpolants_def{pddef}")
    if not os.path.isdir(root):
        return []

    tasks: Set[Tuple[str, int, int]] = set()
    for k_dir in os.listdir(root):
        if not k_dir.isdigit():
            continue
        K_dir = int(k_dir)
        folder = os.path.join(root, k_dir)
        try:
            files = os.listdir(folder)
        except Exception:
            continue
        for fn in files:
            if not fn.endswith(".interpolant"):
                continue
            path = os.path.join(folder, fn)
            if not os.path.isfile(path) or os.path.getsize(path) <= 0:
                continue

            parts = fn.split(".")
            # instance may contain dots; parse from the end:
            # <instance>.<K>.<i>.interpolant
            if len(parts) < 4:
                continue
            if parts[-1] != "interpolant":
                continue
            k_str = parts[-3]
            i_str = parts[-2]
            if not (k_str.isdigit() and i_str.isdigit()):
                continue
            K_file = int(k_str)
            if K_file != K_dir:
                continue
            index = int(i_str)
            instance = ".".join(parts[:-3])
            if not instance:
                continue
            tasks.add((instance, K_file, index))

    return sorted(tasks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, default=None, help="Instance name (required unless --all)")
    parser.add_argument("--K", type=int, default=None, help="K (required unless --all)")
    parser.add_argument("--index", type=int, default=None, help="Interpolant index (required unless --all)")
    parser.add_argument("--force_refresh", action="store_true", default=False)
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Convert all interpolants found under ProofDoorBenchmark/interpolants_def3/<K>/ (indices are whatever exists on disk).",
    )
    args = parser.parse_args()

    if args.all:
        tasks = _discover_interpolant_tasks(pddef=3)
        if not tasks:
            # Fallback for older setups where only summary CSVs exist.
            linear_scaling_summary_csv = "linear.scaling.csv"
            exponential_scaling_summary_csv = "exponential.scaling.csv"
            pairs = _load_instance_k_pairs(linear_scaling_summary_csv, exponential_scaling_summary_csv)
            # Only enqueue (instance, K, index) where interpolant file exists and is non-empty
            tasks = []
            for (instance, K) in sorted(pairs):
                inp_dir = get_interpolant_dir(K, 3)
                for index in range(K):
                    in_path = os.path.join(inp_dir, f"{instance}.{K}.{index}.interpolant")
                    if os.path.isfile(in_path) and os.path.getsize(in_path) > 0:
                        tasks.append((instance, K, index))

        for (instance, K, index) in tqdm(tasks, desc="smtcnf"):
            convert_one(instance, K, index, force_refresh=args.force_refresh)
        return

    if args.instance is None or args.K is None or args.index is None:
        parser.error("--instance, --K and --index are required when not using --all")
    convert_one(args.instance, args.K, args.index, force_refresh=args.force_refresh)


if __name__ == "__main__":
    main()

