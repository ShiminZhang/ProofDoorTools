#!/usr/bin/env python3
"""
verify_skolem_interpolant.py

Expand the Skolem-substituted AAG to a logically-equivalent CNF (no auxiliary
variables) and verify the three Craig interpolant conditions using CaDiCaL:

  [VAR]   vars(I) ⊆ remaining_vars
  [LEFT]  ia_clauses ∧ ¬I  is UNSAT      (i.e. I_{prev} ∧ A ⊨ I)
  [RIGHT] I ∧ b_clauses    is UNSAT      (i.e. I is incompatible with B)

The verified interpolant CNF is saved to disk so the next iteration (i+1)
can load it as I_{prev}.

Usage:
    python verify_skolem_interpolant.py --name cal4 --K 7 --i 0
"""

import os
import sys
import argparse
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import get_CNF_dir, get_progressive_qdimacs_dir
from AagToCnfDirect import expand

CADICAL_BIN = os.path.abspath("./solvers/cadical")
AAG_DIR_TEMPLATE        = "./ProofDoorBenchmark/interpolant_aig_manthan/{K}/"
INTERP_CNF_DIR_TEMPLATE = "./ProofDoorBenchmark/interp_cnf_spd_manthan/{K}/"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_aag_path(name, K, i):
    return os.path.join(AAG_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.aag")

def get_qdimacs_path(name, K, i):
    return os.path.join(
        get_progressive_qdimacs_dir(K, tag="spd_skolem"), f"{name}.{K}.{i}.qdimacs"
    )

def get_interp_cnf_path(name, K, i):
    d = INTERP_CNF_DIR_TEMPLATE.format(K=K)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.{K}.{i}.cnf")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_qdimacs(path):
    remaining_vars, elim_vars, clauses = [], [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] == 'c':
                continue
            if line[0] == 'p':
                continue
            if line[0] == 'a':
                remaining_vars = [int(x) for x in line.split()[1:] if x != '0']
            elif line[0] == 'e':
                elim_vars = [int(x) for x in line.split()[1:] if x != '0']
            else:
                lits = [int(x) for x in line.split() if x != '0']
                if lits:
                    clauses.append(lits)
    return remaining_vars, elim_vars, clauses


def _parse_symtab(lines, inputs):
    """Parse AIGER symbol-table lines into var_map."""
    var_map = {}
    for line in lines:
        if line.startswith('c'):
            break
        if line.startswith('i'):
            parts = line.split()
            if len(parts) == 2:
                n         = int(parts[0][1:])
                port_name = parts[1]
                if port_name.startswith('i') and port_name[1:].isdigit():
                    aig_var  = inputs[n] >> 1
                    orig_var = int(port_name[1:])
                    var_map[aig_var] = orig_var
    return var_map


def _parse_aag(lines):
    """Parse ASCII AIGER (aag) from a list of stripped lines."""
    parts = lines[0].split()
    M, I_count, L, O, A = (int(parts[k]) for k in range(1, 6))
    idx = 1

    inputs  = [int(lines[idx + k]) for k in range(I_count)];  idx += I_count
    idx += L
    outputs = [int(lines[idx + k]) for k in range(O)];        idx += O

    and_gates = {}
    for k in range(A):
        p = lines[idx + k].split()
        and_gates[int(p[0])] = (int(p[1]), int(p[2]))
    idx += A

    var_map = _parse_symtab(lines[idx:], inputs)
    return M, I_count, L, O, A, inputs, outputs, and_gates, var_map


def _parse_aig(data):
    """Parse binary AIGER (aig) from raw bytes."""
    nl  = data.index(b'\n')
    hdr = data[:nl].decode('ascii').split()
    M, I_count, L, O, A = (int(hdr[k]) for k in range(1, 6))
    pos = nl + 1

    # Inputs are implicit: literals 2, 4, ..., 2*I_count
    inputs = [2 * (k + 1) for k in range(I_count)]

    # Skip L latch lines
    for _ in range(L):
        pos = data.index(b'\n', pos) + 1

    # Read O output literals
    outputs = []
    for _ in range(O):
        end = data.index(b'\n', pos)
        outputs.append(int(data[pos:end].split()[0]))
        pos = end + 1

    # Read A AND gates (binary delta encoding)
    def decode_uint():
        nonlocal pos
        x = i = 0
        while True:
            ch = data[pos]; pos += 1
            if ch & 0x80:
                x |= (ch & 0x7f) << (7 * i); i += 1
            else:
                return x | (ch << (7 * i))

    and_gates = {}
    for k in range(A):
        lhs    = 2 * (I_count + L + k + 1)
        delta0 = decode_uint()
        delta1 = decode_uint()
        rhs0   = lhs - delta0
        rhs1   = rhs0 - delta1
        and_gates[lhs] = (rhs0, rhs1)

    # Symbol table follows as ASCII text
    symtab_lines = data[pos:].decode('latin-1').splitlines()
    var_map = _parse_symtab(symtab_lines, inputs)
    return M, I_count, L, O, A, inputs, outputs, and_gates, var_map


def parse_aag_with_symtab(aag_path):
    """
    Parse an AIGER file (ASCII .aag or binary .aig).

    Returns (M, I_count, L, O, A, inputs, outputs, and_gates, var_map) where
    var_map maps AIG variable number -> original CNF variable number, derived
    from symbol table entries like 'i0 i3' (AIG input 0, port name 'i3' -> var 3).
    """
    with open(aag_path, 'rb') as f:
        data = f.read()

    nl  = data.index(b'\n')
    fmt = data[:nl].split()[0]

    if fmt == b'aag':
        lines = data.decode('latin-1').splitlines()
        return _parse_aag(lines)
    elif fmt == b'aig':
        return _parse_aig(data)
    else:
        raise ValueError(f"Unknown AIGER format in {aag_path}: first token = {fmt}")


def load_interp_cnf(path):
    """Load a saved interpolant CNF as a list of lists of ints."""
    clauses = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ('c', 'p'):
                continue
            lits = [int(x) for x in line.split() if x != '0']
            if lits:
                clauses.append(lits)
    return clauses


# ---------------------------------------------------------------------------
# CNF utilities
# ---------------------------------------------------------------------------

def dedup(clauses):
    seen, result = set(), []
    for c in clauses:
        if c not in seen:
            seen.add(c); result.append(c)
    return result


def translate_clauses(clauses, var_map):
    """Translate AIG variable numbers (frozensets) to original CNF variable numbers."""
    result = []
    for clause in clauses:
        translated = frozenset(
            var_map.get(abs(lit), abs(lit)) * (1 if lit > 0 else -1)
            for lit in clause
        )
        result.append(translated)
    return result


def clauses_to_dimacs_str(clauses, num_vars):
    lines = [f"p cnf {num_vars} {len(clauses)}"]
    for clause in clauses:
        if not clause:
            lines.append("0")
        else:
            lines.append(" ".join(map(str, sorted(clause, key=abs))) + " 0")
    return "\n".join(lines) + "\n"


def save_interp_cnf(clauses, name, K, i):
    path = get_interp_cnf_path(name, K, i)
    num_vars = max((abs(lit) for c in clauses for lit in c), default=0)
    with open(path, 'w') as f:
        f.write(clauses_to_dimacs_str(clauses, num_vars))
    return path


# ---------------------------------------------------------------------------
# SAT check via CaDiCaL
# ---------------------------------------------------------------------------

def run_cadical(clauses_a, clauses_b=None):
    """
    Check satisfiability of clauses_a ∧ clauses_b.
    Each clause is a frozenset or list of DIMACS ints.
    Returns True if UNSAT, False if SAT.
    """
    all_clauses = list(clauses_a)
    if clauses_b:
        all_clauses.extend(clauses_b)

    num_vars = max((abs(lit) for c in all_clauses for lit in c), default=0)
    content  = clauses_to_dimacs_str(all_clauses, num_vars)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.cnf', delete=False) as f:
        f.write(content)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [CADICAL_BIN, "-q", tmp_path],
            capture_output=True, text=True
        )
        if result.returncode == 20:
            return True    # UNSAT
        elif result.returncode == 10:
            return False   # SAT
        else:
            raise RuntimeError(
                f"CaDiCaL returned unexpected exit code {result.returncode}\n{result.stderr}"
            )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Main verification logic
# ---------------------------------------------------------------------------

def verify_interpolant(name, K, i):
    from utils.process_cnf import CNF

    aag_path     = get_aag_path(name, K, i)
    qdimacs_path = get_qdimacs_path(name, K, i)

    for p in (aag_path, qdimacs_path):
        if not os.path.exists(p):
            raise FileNotFoundError(p)

    # 1. Left-side formula (ia_clauses) and variable partition from QDIMACS
    remaining_vars, elim_vars, ia_clauses = parse_qdimacs(qdimacs_path)
    remaining_set = set(remaining_vars)
    print(f"QDIMACS: remaining={len(remaining_vars)}  elim={len(elim_vars)}  clauses={len(ia_clauses)}")

    # 2. Right-side formula: clauses of iterations > i in the original CNF
    cnf_path  = f"{get_CNF_dir(K)}/{name}.{K}.cnf"
    cnf       = CNF(cnf_path, use_cache=True, skip_parse_literal_map=True)
    iter_map  = cnf.get_iter_map()
    b_start   = iter_map.get(i + 1, len(cnf.clauses))
    b_clauses = cnf.clauses[b_start:]
    print(f"B (clauses after iter {i}): {len(b_clauses)}")

    # 3. Parse AAG + symbol table
    M, I_count, L, O, A, inputs, outputs, and_gates, var_map = parse_aag_with_symtab(aag_path)
    print(f"AAG: M={M}  I={I_count}  L={L}  O={O}  A={A}  symtab={len(var_map)} entries")
    if O != 1:
        raise ValueError(f"Expected 1 output in AAG, got {O}")
    out_lit = outputs[0]

    # 4. Direct expansion: CNF(I) and CNF(¬I)
    memo    = {}
    cnf_I    = translate_clauses(dedup(expand(out_lit,     and_gates, memo)), var_map)
    cnf_notI = translate_clauses(dedup(expand(out_lit ^ 1, and_gates, memo)), var_map)
    print(f"Expansion: CNF(I)={len(cnf_I)} clauses  CNF(¬I)={len(cnf_notI)} clauses")

    # 5. Variable condition
    vars_in_I = {abs(lit) for c in cnf_I for lit in c}
    bad_vars  = vars_in_I - remaining_set
    var_ok    = not bad_vars
    status    = "OK" if var_ok else f"FAIL — spurious vars: {sorted(bad_vars)}"
    print(f"[VAR]   {status}")

    # 6. Left condition: I_{prev} ∧ A ∧ ¬I must be UNSAT
    left_unsat = run_cadical(ia_clauses, cnf_notI)
    print(f"[LEFT]  {'OK (UNSAT)' if left_unsat  else 'FAIL (SAT)'}  — ia_clauses ∧ ¬I")

    # 7. Right condition: I ∧ B must be UNSAT
    right_unsat = run_cadical(cnf_I, b_clauses)
    print(f"[RIGHT] {'OK (UNSAT)' if right_unsat else 'FAIL (SAT)'}  — I ∧ B")

    # 8. Save interpolant CNF for chaining
    saved = save_interp_cnf(cnf_I, name, K, i)
    print(f"Interpolant CNF saved: {saved}")

    return var_ok and left_unsat and right_unsat


def main():
    parser = argparse.ArgumentParser(
        description="Verify the Skolem-based SPD interpolant and save the interpolant CNF"
    )
    parser.add_argument('--name', required=True, help='Instance name')
    parser.add_argument('--K',    type=int, required=True, help='K value')
    parser.add_argument('--i',    type=int, required=True, help='Iteration index')
    args = parser.parse_args()

    valid = verify_interpolant(args.name, args.K, args.i)
    print(f"\n{'VALID' if valid else 'INVALID'} interpolant at iteration {args.i}")
    sys.exit(0 if valid else 1)


if __name__ == '__main__':
    main()
