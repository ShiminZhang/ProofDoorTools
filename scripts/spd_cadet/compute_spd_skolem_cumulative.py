"""
compute_spd_skolem_cumulative.py

Compute Skolem functions for Craig interpolants with CUMULATIVE partitioning.

For each iteration i, computes the interpolant from:
    - Left part:  A_0 ∧ A_1 ∧ ... ∧ A_i  (all clauses from iterations 0 to i)
    - Right part: A_{i+1} ∧ ... ∧ A_K     (all clauses from iterations i+1 to K)

This differs from compute_spd_skolem.py which uses:
    - Left part:  I_{i-1} ∧ A_i           (previous interpolant + current iteration)
    - Right part: A_{i+1} ∧ ... ∧ A_K     (remaining iterations)

The cumulative approach is independent at each step (no I_prev dependency).

Backend: Manthan or BFSS
"""

import os
import sys
import subprocess
import argparse

# Allow imports from the scripts/ directory (parent of this file's directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import get_CNF_dir, get_progressive_qdimacs_dir
from utils.utils import generate_cnf

BACKENDS = ('manthan', 'BFSS')

MANTHAN_DIR = "./External/manthan"
MANTHAN_BIN = "manthan.py"


def get_skolem_dir(k_value, backend):
    """Directory for Skolem functions with cumulative partitioning."""
    d = f"./ProofDoorBenchmark/skolem_spd_{backend}_cumulative/{k_value}/"
    os.makedirs(d, exist_ok=True)
    return d


def read_qdimacs_clauses(path):
    """Parse a QDIMACS file and return only the clause lines as lists of ints."""
    clauses = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line[0] in ('c', 'p', 'e', 'a'):
                continue
            lits = [int(x) for x in line.split() if x != '0']
            clauses.append(lits)
    return clauses


def write_qdimacs_skolem(path, max_var, a_vars, e_vars, clauses):
    """Write a QDIMACS file with ∀ a_vars ∃ e_vars prefix."""
    with open(path, 'w') as f:
        f.write(f"p cnf {max_var} {len(clauses)}\n")
        if a_vars:
            f.write("a " + " ".join(str(v) for v in sorted(a_vars)) + " 0\n")
        if e_vars:
            f.write("e " + " ".join(str(v) for v in sorted(e_vars)) + " 0\n")
        for clause in clauses:
            if clause:
                f.write(" ".join(str(lit) for lit in clause) + " 0\n")
            else:
                f.write("0\n")


def compute_spd_skolem_cumulative(name, K, i, backend, export_qdimacs_only=False):
    """
    Compute Skolem function for cumulative partition at iteration i.

    Args:
        name: Instance name
        K: Total number of iterations
        i: Current iteration (0 <= i < K)
        backend: 'manthan' or 'BFSS'
        export_qdimacs_only: If True, only generate QDIMACS and return path

    Returns:
        Path to the Skolem file (or QDIMACS path if export_qdimacs_only=True)
    """
    from utils.process_cnf import CNF

    if i < 0 or i >= K:
        raise ValueError(f"Iteration i={i} out of range [0, {K})")

    cnf_path = f"{get_CNF_dir(K)}/{name}.{K}.cnf"
    if not os.path.exists(cnf_path):
        generate_cnf(f"{name}.{K}.cnf")
    
    cnf = CNF(cnf_path, use_cache=True, skip_parse_literal_map=True)

    iter_map = cnf.get_iter_map()

    # Left part: A_0 ∧ A_1 ∧ ... ∧ A_i
    left_start = 0
    left_end = iter_map.get(i + 1, len(cnf.clauses))
    left_clauses = cnf.clauses[left_start:left_end]

    # Right part: A_{i+1} ∧ ... ∧ A_K
    right_start = iter_map.get(i + 1, len(cnf.clauses))
    right_clauses = cnf.clauses[right_start:]

    print(f"Cumulative partition i={i}:")
    print(f"  Left  (A_0...A_{i}): clauses[0:{left_end}] = {len(left_clauses)} clauses")
    print(f"  Right (A_{i+1}...A_K): clauses[{right_start}:end] = {len(right_clauses)} clauses")

    # Compute variable sets for quantifier prefix
    vars_in_left = {abs(lit) for clause in left_clauses for lit in clause}
    vars_in_right = {abs(lit) for clause in right_clauses for lit in clause}

    # Shared variables: universal (can be witnessed to either side)
    shared_vars = vars_in_left & vars_in_right

    # Existential variables: private to left part
    elim_vars = vars_in_left - vars_in_right

    # All variables
    all_vars = vars_in_left | vars_in_right
    max_var = max(all_vars) if all_vars else 0

    print(f"  Variables: left={len(vars_in_left)}, right={len(vars_in_right)}, "
          f"shared={len(shared_vars)}, elim={len(elim_vars)}")

    # Write the input QDIMACS with ∀ shared_vars ∃ elim_vars (left_clauses) prefix
    # Only left clauses go in the QBF; right clauses are checked in verification
    qdimacs_dir = get_progressive_qdimacs_dir(K, tag="spd_skolem_cumulative")
    qdimacs_path = os.path.join(qdimacs_dir, f"{name}.{K}.{i}.qdimacs")
    write_qdimacs_skolem(qdimacs_path, max_var, shared_vars, elim_vars, left_clauses)
    print(f"QDIMACS written to: {qdimacs_path}")

    if export_qdimacs_only:
        return qdimacs_path

    skolem_dir = get_skolem_dir(K, backend)
    skolem_path = os.path.join(skolem_dir, f"{name}.{K}.{i}.skolem.v")

    if backend == 'manthan':
        _run_manthan(qdimacs_path, skolem_path)
    elif backend == 'BFSS':
        # TODO: invoke BFSS and process its output
        raise NotImplementedError("BFSS invocation logic not yet implemented")

    print(f"Skolem function written to: {skolem_path}")
    return skolem_path


def _run_manthan(qdimacs_path, skolem_path):
    """Run Manthan solver on QDIMACS file."""
    # Manthan reads manthan_dependencies.cfg from its own directory at import time,
    # so it must be invoked with cwd=MANTHAN_DIR. Use absolute paths for I/O.
    abs_qdimacs = os.path.abspath(qdimacs_path)
    abs_skolem = os.path.abspath(skolem_path)
    abs_manthan = os.path.abspath(MANTHAN_DIR)

    env = os.environ.copy()
    static_bin = os.path.join(abs_manthan, "dependencies", "static_bin")
    env["LD_LIBRARY_PATH"] = static_bin + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    cmd = ["python", MANTHAN_BIN, "-o", abs_skolem, abs_qdimacs]
    print(f"Running: {' '.join(cmd)}  (cwd={abs_manthan})")
    result = subprocess.run(cmd, cwd=abs_manthan, env=env, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Manthan failed with exit code {result.returncode}")


def main():
    parser = argparse.ArgumentParser(
        description='Compute one step of cumulative-partitioned Skolem function via Manthan'
    )
    parser.add_argument('--name', required=True, help='Instance name')
    parser.add_argument('--K', type=int, required=True, help='Total number of iterations')
    parser.add_argument('--i', type=int, required=True, help='Current iteration (0-indexed)')
    parser.add_argument('--backend', default='manthan', choices=BACKENDS,
                        help='Solver backend')
    parser.add_argument('--export-qdimacs-only', action='store_true',
                        help='Only export QDIMACS, do not run solver')
    args = parser.parse_args()

    compute_spd_skolem_cumulative(
        args.name, args.K, args.i, args.backend,
        export_qdimacs_only=args.export_qdimacs_only
    )


if __name__ == '__main__':
    main()
