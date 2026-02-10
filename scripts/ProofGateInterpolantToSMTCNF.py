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
from typing import List, Set, Tuple

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, default=None, help="Instance name (required unless --all)")
    parser.add_argument("--K", type=int, default=None, help="K (required unless --all)")
    parser.add_argument("--index", type=int, default=None, help="Interpolant index (required unless --all)")
    parser.add_argument("--force_refresh", action="store_true", default=False)
    parser.add_argument("--all", action="store_true", default=False, help="Convert all (instance,K) from linear.scaling.csv and exponential.scaling.csv; for each, run indices 0..K")
    args = parser.parse_args()

    if args.all:
        linear_scaling_summary_csv = "linear.scaling.csv"
        exponential_scaling_summary_csv = "exponential.scaling.csv"
        pairs = _load_instance_k_pairs(linear_scaling_summary_csv, exponential_scaling_summary_csv)
        # Only enqueue (instance, K, index) where interpolant file exists and is non-empty
        tasks: List[Tuple[str, int, int]] = []
        for (instance, K) in sorted(pairs):
            inp_dir = get_interpolant_dir(K, 3)
            for index in range(K + 1):
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

