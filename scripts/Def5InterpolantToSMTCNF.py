#!/usr/bin/env python3
"""
Convert pddef=5 interpolants from QDIMACS `.interpolant` into standard DIMACS
CNF (`.smtcnf` extension, for downstream absorption experiment paths).

Input (per index):
  ProofDoorBenchmark/interpolants_def5/<K>/<instance>.<K>.<i>.interpolant

QDIMACS format: "p cnf <vars> <clauses>" header, then an "a <lits> 0" line
listing A-part variables, then clause lines in standard DIMACS form.

Output:
  ProofDoorBenchmark/interpolant_as_cnfs_5/<K>/<instance>.<K>.<i>.smtcnf
Standard DIMACS CNF: "p cnf <nvars> <nclauses>", then one clause per line.
"""

import argparse
import os
from tqdm import tqdm
from typing import List, Set, Tuple

from utils.paths import get_interpolant_cnf_dir, get_interpolant_dir


def _parse_clause_line(line: str) -> List[int]:
    lits: List[int] = []
    for tok in line.strip().split():
        if tok == "0":
            break
        lits.append(int(tok))
    return lits


def convert_one(instance: str, K: int, index: int, force_refresh: bool = False) -> str:
    inp_dir = get_interpolant_dir(K, 5)
    out_dir = get_interpolant_cnf_dir(K, 5)
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
            if not line:
                continue
            # Skip QDIMACS header and quantifier lines
            if line.startswith("p") or line.startswith("c"):
                continue
            if line.startswith("a") or line.startswith("e"):
                continue
            lits = _parse_clause_line(line)
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

    return out_path


def _discover_tasks() -> List[Tuple[str, int, int]]:
    root = os.path.join("./ProofDoorBenchmark", "interpolants_def5")
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
            if not os.path.isfile(os.path.join(folder, fn)):
                continue
            if os.path.getsize(os.path.join(folder, fn)) <= 0:
                continue
            parts = fn.split(".")
            # <instance>.<K>.<i>.interpolant
            if len(parts) < 4 or parts[-1] != "interpolant":
                continue
            k_str, i_str = parts[-3], parts[-2]
            if not (k_str.isdigit() and i_str.isdigit()):
                continue
            if int(k_str) != K_dir:
                continue
            instance = ".".join(parts[:-3])
            if not instance:
                continue
            tasks.add((instance, K_dir, int(i_str)))

    return sorted(tasks)


def _auto_detect_K(instance: str) -> int:
    """Scan interpolants_def5/ for files belonging to instance, return max_index + 1."""
    root = os.path.join("./ProofDoorBenchmark", "interpolants_def5")
    max_index = -1
    for k_dir in os.listdir(root):
        if not k_dir.isdigit():
            continue
        folder = os.path.join(root, k_dir)
        for fn in os.listdir(folder):
            if not fn.endswith(".interpolant"):
                continue
            parts = fn.split(".")
            if len(parts) < 4 or parts[-1] != "interpolant":
                continue
            k_str, i_str = parts[-3], parts[-2]
            if not (k_str.isdigit() and i_str.isdigit()):
                continue
            inst = ".".join(parts[:-3])
            if inst != instance:
                continue
            max_index = max(max_index, int(i_str))
    if max_index < 0:
        raise FileNotFoundError(f"No interpolant files found for instance '{instance}'")
    return max_index + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance", type=str, default=None)
    parser.add_argument("--K", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--force_refresh", action="store_true", default=False)
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Convert all interpolants found under ProofDoorBenchmark/interpolants_def5/",
    )
    parser.add_argument(
        "--auto_K",
        action="store_true",
        default=False,
        help="Infer K from max index + 1 found in interpolants_def5/ (requires --instance)",
    )
    args = parser.parse_args()

    if args.all:
        tasks = _discover_tasks()
        if not tasks:
            print("No interpolant files found under ProofDoorBenchmark/interpolants_def5/")
            return
        print(f"Found {len(tasks)} interpolant files to convert")
        for (instance, K, index) in tqdm(tasks, desc="converting def5"):
            convert_one(instance, K, index, force_refresh=args.force_refresh)
        return

    if args.auto_K:
        if args.instance is None:
            parser.error("--auto_K requires --instance")
        K = _auto_detect_K(args.instance)
        print(f"[auto_K] detected K={K} for instance '{args.instance}'")
        for index in range(K):
            convert_one(args.instance, K, index, force_refresh=args.force_refresh)
        return

    if args.instance is None or args.K is None or args.index is None:
        parser.error("--instance, --K and --index are required when not using --all or --auto_K")
    convert_one(args.instance, args.K, args.index, force_refresh=args.force_refresh)


if __name__ == "__main__":
    main()
