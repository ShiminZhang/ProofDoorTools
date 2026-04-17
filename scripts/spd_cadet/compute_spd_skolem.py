import os
import sys
import subprocess
import argparse

# Allow imports from the scripts/ directory (parent of this file's directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import get_CNF_dir, get_progressive_qdimacs_dir

BACKENDS = ('manthan', 'BFSS')

MANTHAN_DIR = "./External/manthan"
MANTHAN_BIN = "manthan.py"


def get_skolem_dir(k_value, backend):
    d = f"./ProofDoorBenchmark/skolem_spd_{backend}/{k_value}/"
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


def compute_spd_skolem(name, K, i, backend, export_qdimacs_only=False):
    from utils.process_cnf import CNF

    cnf_path = f"{get_CNF_dir(K)}/{name}.{K}.cnf"
    cnf = CNF(cnf_path, use_cache=True, skip_parse_literal_map=True)

    iter_map = cnf.get_iter_map()

    # A: clauses belonging to iteration i
    a_start = iter_map.get(i, 0)
    a_end   = iter_map.get(i + 1, len(cnf.clauses))
    a_clauses = cnf.clauses[a_start:a_end]

    # B: all clauses after iteration i
    b_start   = iter_map.get(i + 1, len(cnf.clauses))
    b_clauses = cnf.clauses[b_start:]

    # I_prev: strongest interpolant from the previous step (empty / True for i == 0)
    # TODO: update this path when the Skolem result format is decided
    if i == 0:
        i_clauses = []
    else:
        raise NotImplementedError("Chained interpolant loading not yet implemented for spd_skolem")

    # Compute variable sets for quantifier prefix
    ia_clauses     = i_clauses + a_clauses
    vars_in_ia     = {abs(lit) for clause in ia_clauses for lit in clause}
    vars_in_b      = {abs(lit) for clause in b_clauses  for lit in clause}
    elim_vars      = vars_in_ia - vars_in_b   # existential: private to I∧A
    remaining_vars = vars_in_ia - elim_vars   # universal: shared with B
    max_var        = max(vars_in_ia) if vars_in_ia else 0

    # Write the input QDIMACS with ∀ remaining_vars ∃ elim_vars prefix
    qdimacs_dir  = get_progressive_qdimacs_dir(K, tag="spd_skolem")
    qdimacs_path = os.path.join(qdimacs_dir, f"{name}.{K}.{i}.qdimacs")
    write_qdimacs_skolem(qdimacs_path, max_var, remaining_vars, elim_vars, ia_clauses)
    print(f"QDIMACS written to: {qdimacs_path}")

    if export_qdimacs_only:
        return qdimacs_path

    skolem_dir  = get_skolem_dir(K, backend)
    skolem_path = os.path.join(skolem_dir, f"{name}.{K}.{i}.skolem.v")

    if backend == 'manthan':
        _run_manthan(qdimacs_path, skolem_path)
    elif backend == 'BFSS':
        # TODO: invoke BFSS and process its output
        raise NotImplementedError("BFSS invocation logic not yet implemented")

    print(f"Skolem function written to: {skolem_path}")
    return skolem_path


def _run_manthan(qdimacs_path, skolem_path):
    # Manthan reads manthan_dependencies.cfg from its own directory at import time,
    # so it must be invoked with cwd=MANTHAN_DIR. Use absolute paths for I/O.
    abs_qdimacs = os.path.abspath(qdimacs_path)
    abs_skolem  = os.path.abspath(skolem_path)
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
        description='Compute one step of the strongest PD Skolem function via a chosen backend'
    )
    parser.add_argument('--name',    required=True, help='Instance name')
    parser.add_argument('--K',       type=int, required=True, help='K value')
    parser.add_argument('--i',       type=int, required=True, help='Iteration index')
    parser.add_argument('--backend', required=True, choices=BACKENDS,
                        help='Skolem function synthesis backend')
    parser.add_argument('--export_qdimacs_only', action='store_true',
                        help='Only write the input QDIMACS; skip the backend step')
    args = parser.parse_args()

    compute_spd_skolem(
        args.name,
        args.K,
        args.i,
        args.backend,
        export_qdimacs_only=args.export_qdimacs_only,
    )


if __name__ == '__main__':
    main()
