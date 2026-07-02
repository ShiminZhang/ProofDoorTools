import os
import sys
import subprocess
import tempfile
import argparse

# Allow imports from the scripts/ directory (parent of this file's directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import get_CNF_dir, get_interpolant_dir, get_progressive_qdimacs_dir
from utils.utils import generate_cnf
PREPROCESS_BIN = "./External/kissat_bve/build/preprocess"
CADICAL_BIN    = "./solvers/cadical"


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


def read_qdimacs(path):
    """Parse a QDIMACS file into header, prefix, and clauses."""
    max_var = 0
    universal_vars = []
    existential_vars = []
    clauses = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] == 'c':
                continue
            if line[0] == 'p':
                parts = line.split()
                max_var = int(parts[2])
                continue
            if line[0] == 'a':
                universal_vars.extend(int(x) for x in line.split()[1:] if x != '0')
                continue
            if line[0] == 'e':
                existential_vars.extend(int(x) for x in line.split()[1:] if x != '0')
                continue
            lits = [int(x) for x in line.split() if x != '0']
            clauses.append(lits)
    return {
        "max_var": max_var,
        "a_vars": universal_vars,
        "e_vars": existential_vars,
        "clauses": clauses,
    }


def write_qdimacs_full(path, max_var, a_vars, e_vars, clauses):
    """Write a QDIMACS file with explicit quantifier prefixes."""
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


def _normalize_clause(clause):
    """Return a canonical clause tuple, or None if it is tautological."""
    seen = set()
    normalized = []
    for lit in clause:
        if -lit in seen:
            return None
        if lit in seen:
            continue
        seen.add(lit)
        normalized.append(lit)
    normalized.sort(key=lambda lit: (abs(lit), lit < 0))
    return tuple(normalized)


def _dedupe_clauses(clauses):
    """Remove duplicate clauses while preserving canonical literal order."""
    seen = set()
    deduped = []
    for clause in clauses:
        normalized = _normalize_clause(clause)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(list(normalized))
    return deduped


def _apply_exist_assignments(clauses, assignments):
    """Simplify clauses under existential assignments used for projection."""
    simplified = []
    for clause in clauses:
        satisfied = False
        reduced = []
        for lit in clause:
            val = assignments.get(abs(lit))
            if val is None:
                reduced.append(lit)
            elif val == (lit > 0):
                satisfied = True
                break
        if satisfied:
            continue
        if not reduced:
            return [[]]
        simplified.append(reduced)
    return _dedupe_clauses(simplified)


def _propagate_exist_units(clauses, remaining_exist):
    """Propagate unit clauses only for variables still existentially quantified."""
    remaining_exist = set(remaining_exist)
    while True:
        assignments = {}
        for clause in clauses:
            if len(clause) != 1:
                continue
            lit = clause[0]
            var = abs(lit)
            if var not in remaining_exist:
                continue
            value = lit > 0
            prev = assignments.get(var)
            if prev is not None and prev != value:
                return [[]], set()
            assignments[var] = value
        if not assignments:
            return clauses, remaining_exist
        remaining_exist -= set(assignments)
        clauses = _apply_exist_assignments(clauses, assignments)
        if clauses == [[]]:
            return clauses, set()


def forced_eliminate_remaining_vars(path, label=""):
    """
    Eliminate all remaining existential variables by exact resolution.

    This fallback assumes the remaining quantified set is small. It eliminates
    variables one by one, deleting all clauses containing the pivot and adding
    all non-tautological resolvents.
    """
    qdimacs = read_qdimacs(path)
    clauses = _dedupe_clauses(qdimacs["clauses"])
    remaining_exist = set(qdimacs["e_vars"])

    clauses, remaining_exist = _propagate_exist_units(clauses, remaining_exist)
    if clauses == [[]]:
        write_qdimacs_full(path, qdimacs["max_var"], [], [], clauses)
        return []

    step = 0
    while remaining_exist:
        occurrences = {}
        for var in remaining_exist:
            pos_idx = []
            neg_idx = []
            for idx, clause in enumerate(clauses):
                if var in map(abs, clause):
                    if var in clause:
                        pos_idx.append(idx)
                    if -var in clause:
                        neg_idx.append(idx)
            occurrences[var] = (len(pos_idx) * len(neg_idx), pos_idx, neg_idx)

        pivot = min(
            remaining_exist,
            key=lambda var: (
                occurrences[var][0],
                len(occurrences[var][1]) + len(occurrences[var][2]),
                var,
            ),
        )
        _, pos_idx, neg_idx = occurrences[pivot]
        step += 1
        print(
            f"[FORCED_ELIM] {label} step {step}: eliminate {pivot} "
            f"(pos={len(pos_idx)}, neg={len(neg_idx)})"
        )

        touching = set(pos_idx) | set(neg_idx)
        if not touching:
            remaining_exist.remove(pivot)
            continue

        if not pos_idx or not neg_idx:
            clauses = [clause for idx, clause in enumerate(clauses) if idx not in touching]
            remaining_exist.remove(pivot)
            clauses, remaining_exist = _propagate_exist_units(clauses, remaining_exist)
            if clauses == [[]]:
                break
            continue

        pos_clauses = [clauses[idx] for idx in pos_idx]
        neg_clauses = [clauses[idx] for idx in neg_idx]
        resolvents = []
        for p_clause in pos_clauses:
            p_rest = [lit for lit in p_clause if lit != pivot]
            for n_clause in neg_clauses:
                n_rest = [lit for lit in n_clause if lit != -pivot]
                resolvent = _normalize_clause(p_rest + n_rest)
                if resolvent is None:
                    continue
                resolvents.append(list(resolvent))

        kept = [clause for idx, clause in enumerate(clauses) if idx not in touching]
        clauses = _dedupe_clauses(kept + resolvents)
        remaining_exist.remove(pivot)
        clauses, remaining_exist = _propagate_exist_units(clauses, remaining_exist)
        if clauses == [[]]:
            break

    used_vars = {abs(lit) for clause in clauses for lit in clause}
    a_vars = sorted(used_vars)
    write_qdimacs_full(path, qdimacs["max_var"], a_vars, [], clauses)
    return []


def write_dimacs(path, clauses, extra_clauses=()):
    """Write a plain DIMACS CNF file (no quantifiers)."""
    all_clauses = list(clauses) + list(extra_clauses)
    if all_clauses:
        max_var = max(abs(lit) for clause in all_clauses for lit in clause)
    else:
        max_var = 0
    with open(path, 'w') as f:
        f.write(f"p cnf {max_var} {len(all_clauses)}\n")
        for clause in all_clauses:
            if clause:
                f.write(" ".join(str(lit) for lit in clause) + " 0\n")
            else:
                f.write("0\n")


def write_qdimacs(path, max_var, clauses, elim_vars):
    """Write a QDIMACS file with an existential quantifier block for elim_vars."""
    with open(path, 'w') as f:
        f.write(f"p cnf {max_var} {len(clauses)}\n")
        if elim_vars:
            f.write("e " + " ".join(str(v) for v in sorted(elim_vars)) + " 0\n")
        for clause in clauses:
            if clause:
                f.write(" ".join(str(lit) for lit in clause) + " 0\n")
            else:
                f.write("0\n")


def _cnf_is_true(clauses):
    """Return True iff the CNF is the empty conjunction (top)."""
    return len(clauses) == 0


def _cnf_is_false(clauses):
    """Return True iff the CNF contains an empty clause (bottom)."""
    return any(len(clause) == 0 for clause in clauses)


def _run_cadical_unsat(clauses, extra_clauses=()):
    """Return True iff the conjunction of clauses (+ extra_clauses) is UNSAT."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.cnf')
    os.close(tmp_fd)
    try:
        write_dimacs(tmp_path, clauses, extra_clauses)
        result = subprocess.run(
            [CADICAL_BIN, "--plain", tmp_path],
            capture_output=True, text=True
        )
        # cadical exits 20 for UNSAT, 10 for SAT
        return result.returncode == 20
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def verify_interpolant(ia_clauses, i_out_clauses, b_clauses, label=""):
    """
    Verify that I is a valid interpolant between A and B:
      1. A → I  :  A ∧ ¬I is UNSAT
      2. I → ¬B :  I ∧ B  is UNSAT

    A is represented by ia_clauses (I_{i-1} ∧ A_i, the BVE input).
    I is i_out_clauses (BVE output).
    B is b_clauses.

    ¬I is encoded via Tseitin: introduce one selector variable s_j per clause
    c_j in I.  The encoding adds:
      - (s_1 ∨ … ∨ s_k)            — at least one clause is violated
      - (¬s_j ∨ ¬l) for each l∈c_j — if s_j is set, every literal of c_j is false

    Returns True if both checks pass, False otherwise.
    Prints the outcome for each check.
    """
    tag = f"[{label}] " if label else ""

    # --- Check 2: I ∧ B = UNSAT ---
    ib_unsat = _run_cadical_unsat(i_out_clauses, b_clauses)
    print(f"{tag}I → ¬B (I ∧ B UNSAT): {ib_unsat}")

    # --- Check 1: A → I (A ∧ ¬I UNSAT) ---
    # Build Tseitin encoding of ¬I
    if _cnf_is_true(i_out_clauses):
        # Empty I is True; A → True always holds.
        ai_valid = True
    elif _cnf_is_false(i_out_clauses):
        # I is False; A → False iff A itself is UNSAT.
        ai_valid = _run_cadical_unsat(ia_clauses)
    else:
        all_vars = {abs(lit) for clause in ia_clauses + i_out_clauses for lit in clause}
        base_max_var = max(all_vars) if all_vars else 0
        selector_clauses = []
        selector_literals = []
        for j, clause in enumerate(i_out_clauses):
            s_j = base_max_var + 1 + j          # new selector variable
            selector_literals.append(s_j)
            # ¬s_j ∨ ¬l  for each l in clause
            for lit in clause:
                selector_clauses.append([-s_j, -lit])
        # at least one clause must be violated
        selector_clauses.append(selector_literals)
        ai_unsat = _run_cadical_unsat(ia_clauses, selector_clauses)
        ai_valid = ai_unsat
    print(f"{tag}A → I  (A ∧ ¬I UNSAT): {ai_valid}")

    return ai_valid and ib_unsat


def compute_spd(name, K, i, export_qdimacs_only=False,
                initialbound=None,
                eliminatebound=None, eliminaterounds=None,
                eliminateclslim=None, eliminateocclim=None,
                eliminateeffort=None,
                reverse=False):
    from utils.process_cnf import CNF

    cnf_path = f"{get_CNF_dir(K)}/{name}.{K}.cnf"
    if not os.path.exists(cnf_path):
        generate_cnf(cnf_path)
    cnf = CNF(cnf_path, use_cache=True, skip_parse_literal_map=True)

    iter_map = cnf.get_iter_map()

    if not reverse:
        # A: clauses belonging to iteration i
        a_start = iter_map.get(i, 0)
        a_end   = iter_map.get(i + 1, len(cnf.clauses))
        a_clauses = cnf.clauses[a_start:a_end]

        # B: all clauses after iteration i
        b_start   = iter_map.get(i + 1, len(cnf.clauses))
        b_clauses = cnf.clauses[b_start:]

        # I_prev: strongest interpolant from the previous step (empty / True for i == 0)
        interp_dir = get_interpolant_dir(K, pddef=5)
        if i == 0:
            i_clauses = []
        else:
            prev_path = os.path.join(interp_dir, f"{name}.{K}.{i-1}.interpolant")
            if not os.path.exists(prev_path):
                raise FileNotFoundError(f"Previous interpolant not found: {prev_path}")
            i_clauses = read_qdimacs_clauses(prev_path)

        qdimacs_tag = "spd"
        pddef = 5
    else:
        # Reverse (pddef7): compute I_i using A_{i+1} and I_{i+1}.
        # Starting point: I_{K-1} = exists_local(A_K), i.e. i_clauses=[] when i+1==k_max.
        k_max = max(iter_map.keys())

        # A: clauses belonging to iteration i+1
        a_start = iter_map.get(i + 1, 0)
        a_end   = iter_map.get(i + 2, len(cnf.clauses))
        a_clauses = cnf.clauses[a_start:a_end]

        # B: all clauses before iteration i+1 (the "past")
        b_clauses = cnf.clauses[:a_start]

        # I_next: reverse interpolant from the next step (empty / True when i+1 == k_max)
        interp_dir = get_interpolant_dir(K, pddef=7)
        if i + 1 == k_max:
            i_clauses = []
        else:
            next_path = os.path.join(interp_dir, f"{name}.{K}.{i+1}.interpolant")
            if not os.path.exists(next_path):
                raise FileNotFoundError(f"Next reverse interpolant not found: {next_path}")
            i_clauses = read_qdimacs_clauses(next_path)

        qdimacs_tag = "spd7"
        pddef = 7

    # Compute variable sets for the existential quantifier
    ia_clauses = i_clauses + a_clauses
    vars_in_ia = {abs(lit) for clause in ia_clauses for lit in clause}
    vars_in_b  = {abs(lit) for clause in b_clauses  for lit in clause}
    elim_vars  = vars_in_ia - vars_in_b
    max_var    = max(vars_in_ia) if vars_in_ia else 0

    # Write the input QDIMACS
    qdimacs_dir  = get_progressive_qdimacs_dir(K, tag=qdimacs_tag)
    qdimacs_path = os.path.join(qdimacs_dir, f"{name}.{K}.{i}.qdimacs")
    write_qdimacs(qdimacs_path, max_var, ia_clauses, elim_vars)
    print(f"QDIMACS written to: {qdimacs_path}")

    if export_qdimacs_only:
        return qdimacs_path

    # Run preprocess to produce the next strongest interpolant
    output_path = os.path.join(interp_dir, f"{name}.{K}.{i}.interpolant")
    cmd = [PREPROCESS_BIN, qdimacs_path, output_path]
    if initialbound is not None:
        cmd.append(f"--initialbound={initialbound}")
    if eliminatebound is not None:
        cmd.append(f"--eliminatebound={eliminatebound}")
    if eliminaterounds is not None:
        cmd.append(f"--eliminaterounds={eliminaterounds}")
    if eliminateclslim is not None:
        cmd.append(f"--eliminateclslim={eliminateclslim}")
    if eliminateocclim is not None:
        cmd.append(f"--eliminateocclim={eliminateocclim}")
    if eliminateeffort is not None:
        cmd.append(f"--eliminateeffort={eliminateeffort}")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n",
              file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"preprocess failed with exit code {result.returncode}")
    if "[ELIM_WARNING]" in result.stdout:
        print(f"[FORCED_ELIM] {name}.{K}.{i}: attempting exact elimination fallback")
        forced_eliminate_remaining_vars(output_path, label=f"{name}.{K}.{i}")
    print(f"Strongest interpolant written to: {output_path}")

    # Verify the produced interpolant
    i_out_clauses = read_qdimacs_clauses(output_path)
    label = f"{name}.{K}.{i}"
    ok = verify_interpolant(ia_clauses, i_out_clauses, b_clauses, label=label)
    if not ok:
        print(f"ERROR: interpolant validity check FAILED for {label}")
        sys.exit(1)

    print(f"Interpolant validity check passed for {label}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Compute one step of the strongest PD interpolant via BVE preprocessing'
    )
    parser.add_argument('--name', required=True, help='Instance name')
    parser.add_argument('--K',    type=int, required=True, help='K value')
    parser.add_argument('--i',    type=int, required=True, help='Iteration index')
    parser.add_argument('--export_qdimacs_only', action='store_true',
                        help='Only write the input QDIMACS; skip the preprocess step')
    parser.add_argument('--reverse', action='store_true',
                        help='Reverse mode (pddef7): compute I_i using A_{i+1} and I_{i+1}, stepping forward from the last chunk')
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
    args = parser.parse_args()

    compute_spd(
        args.name,
        args.K,
        args.i,
        export_qdimacs_only=args.export_qdimacs_only,
        initialbound=args.initialbound,
        eliminatebound=args.eliminatebound,
        eliminaterounds=args.eliminaterounds,
        eliminateclslim=args.eliminateclslim,
        eliminateocclim=args.eliminateocclim,
        eliminateeffort=args.eliminateeffort,
        reverse=args.reverse,
    )


if __name__ == '__main__':
    main()
