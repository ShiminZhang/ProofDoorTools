#!/usr/bin/env python3
"""
For each (name, K, i) in a success CSV (produced by manage_spd_computation.py
--show_success --reverse), read the corresponding pddef7 interpolant (QDIMACS),
negate it globally, convert the negation to CNF via Z3, and write DIMACS output.

Pipeline per entry:
  1. Parse QDIMACS clauses (list[list[int]]) from interpolants_def7/.
  2. Reconstruct the interpolant as a Z3 boolean formula (CNF → And[Or[...]]).
  3. Negate with z3.Not(...).
  4. Apply Z3 tactics: nnf → simplify.
  5. Expand to CNF with expand_to_cnf (from StrongestInterpolantToCNF).
  6. Write DIMACS to interpolant_as_cnfs_spd7/{K}/{name}.{K}.{i}.cnf.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.paths import get_interpolant_dir, get_reverse_spd_cnf_dir, get_spd7_success_csv, get_CNF_dir

# Reuse helpers already defined in sibling modules.
from strongest_pd.compute_spd import read_qdimacs_clauses, _run_cadical_unsat
from StrongestInterpolantToCNF import (
    expand_to_cnf,
    simplify_and_subsume,
    _as_smtcnf_literals,
    _write_dimacs,
    _CNF_CACHE,
)


def _clauses_to_z3(clauses):
    """
    Convert a list[list[int]] CNF (DIMACS literal encoding) to a Z3 expression.

    Returns (z3_formula, var_map) where var_map maps positive int → z3.Bool.
    Empty clause list → z3.BoolVal(True).
    Clause containing [] (empty clause) → z3.BoolVal(False).
    """
    import z3

    if not clauses:
        return z3.BoolVal(True), {}

    var_map = {}

    def lit_to_z3(l):
        v = abs(l)
        if v not in var_map:
            var_map[v] = z3.Bool(f"v{v}")
        return var_map[v] if l > 0 else z3.Not(var_map[v])

    z3_clauses = []
    for clause in clauses:
        if not clause:
            # Empty clause = False; the whole conjunction is False.
            return z3.BoolVal(False), {}
        z3_clauses.append(z3.Or([lit_to_z3(l) for l in clause]))

    if len(z3_clauses) == 1:
        return z3_clauses[0], var_map
    return z3.And(z3_clauses), var_map


def negate_and_to_cnf(clauses):
    """
    Given DIMACS clauses, return a CNF token list (list[list[str]]) representing
    the negation of the formula, using Z3 tactics + expand_to_cnf.

    Returns list[list[str]] where each inner list is a clause in "v123"/"Not(v123)"
    string format, ready for _write_dimacs.
    """
    import z3

    _CNF_CACHE.clear()

    formula, _ = _clauses_to_z3(clauses)

    # Trivial constant cases after negation.
    if z3.is_true(formula):
        # Not(True) = False: one empty clause.
        return [[]]
    if z3.is_false(formula):
        # Not(False) = True: no clauses.
        return []

    negated = z3.Not(formula)

    goal = z3.Goal()
    goal.add(negated)
    nnf_result = z3.Tactic("nnf")(goal)
    simplified = z3.Tactic("simplify")(nnf_result[0])

    # Check for constant result: if Z3 reduced to False (e.g. Not(tautology)),
    # return one empty clause; if it reduced to True, return no clauses.
    for assertion in simplified[0]:
        if z3.is_false(assertion):
            return [[]]
    all_clauses = []
    for assertion in simplified[0]:
        if z3.is_true(assertion):
            continue
        all_clauses.extend(expand_to_cnf(assertion, simplify=True))

    deduped = simplify_and_subsume(all_clauses)

    cnf_tokens = []
    for clause in deduped:
        toks = _as_smtcnf_literals(clause)
        if toks:
            cnf_tokens.append(toks)
    return cnf_tokens


def verify_negated_entry(name, K, i):
    """
    Verify that ¬I_i^{rev} (the negated reverse interpolant at position i) is a
    valid Craig interpolant in the left-to-right direction.

    Partition of the original CNF at position i:
      A = all clauses in iterations 0..i
      B = all clauses in iterations i+1..K-1

    Two checks (mirroring verify_interpolant in compute_spd.py):
      1. A → I  :  A ∧ I_i^{rev}   is UNSAT  (¬I = I_i^{rev} is read directly)
      2. I → ¬B :  neg_i ∧ B       is UNSAT

    Returns True iff both checks pass.
    """
    from utils.process_cnf import CNF

    label = f"{name}.{K}.{i}"

    neg_path = os.path.join(get_reverse_spd_cnf_dir(K), f"{name}.{K}.{i}.cnf")
    rev_path = os.path.join(get_interpolant_dir(K, pddef=7), f"{name}.{K}.{i}.interpolant")

    if not os.path.exists(neg_path) or os.path.getsize(neg_path) == 0:
        print(f"[VERIFY] {label}: negated CNF not found or empty, skipping.")
        return False
    if not os.path.exists(rev_path) or os.path.getsize(rev_path) == 0:
        print(f"[VERIFY] {label}: reverse interpolant not found or empty, skipping.")
        return False

    neg_clauses = read_qdimacs_clauses(neg_path)   # ¬I_i^{rev}  (DIMACS output)
    rev_clauses = read_qdimacs_clauses(rev_path)   #  I_i^{rev}  (QDIMACS source)

    cnf_path = os.path.join(get_CNF_dir(K), f"{name}.{K}.cnf")
    cnf = CNF(cnf_path, use_cache=True, skip_parse_literal_map=True)
    iter_map = cnf.get_iter_map()

    a_end   = iter_map.get(i + 1, len(cnf.clauses))
    b_start = iter_map.get(i + 1, len(cnf.clauses))

    a_clauses = cnf.clauses[:a_end]    # iterations 0..i
    b_clauses = cnf.clauses[b_start:]  # iterations i+1..K-1

    # Check 2: ¬I_i^{rev} ∧ B  is UNSAT
    ib_unsat = _run_cadical_unsat(neg_clauses, b_clauses)
    print(f"[VERIFY] [{label}] I → ¬B  (neg_i ∧ B UNSAT): {ib_unsat}")

    # Check 1: A ∧ I_i^{rev}  is UNSAT  (equivalent to A ∧ ¬(¬I_i^{rev}) UNSAT)
    ai_unsat = _run_cadical_unsat(a_clauses, rev_clauses)
    print(f"[VERIFY] [{label}] A → I   (A ∧ I_i^{{rev}} UNSAT): {ai_unsat}")

    ok = ai_unsat and ib_unsat
    if ok:
        print(f"[VERIFY] [{label}] validity check PASSED")
    else:
        print(f"[VERIFY] [{label}] validity check FAILED")
    return ok


def process_entry(name, K, i, force_refresh=False, verify=True):
    interp_path = os.path.join(
        get_interpolant_dir(K, pddef=7), f"{name}.{K}.{i}.interpolant"
    )
    out_dir = get_reverse_spd_cnf_dir(K)
    out_path = os.path.join(out_dir, f"{name}.{K}.{i}.cnf")

    if not force_refresh and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        print(f"[SKIP] {name}.{K}.{i}: output already exists at {out_path}")
        return

    if not os.path.exists(interp_path) or os.path.getsize(interp_path) == 0:
        print(f"[WARN] {name}.{K}.{i}: interpolant not found or empty: {interp_path}")
        return

    print(f"[PROC] {name}.{K}.{i}: reading {interp_path}")
    clauses = read_qdimacs_clauses(interp_path)
    cnf_tokens = negate_and_to_cnf(clauses)
    _write_dimacs(out_path, cnf_tokens)
    print(f"[DONE] {name}.{K}.{i}: wrote {len(cnf_tokens)} clauses to {out_path}")
    if verify:
        ok = verify_negated_entry(name, K, i)
        if not ok:
            print(f"ERROR: validity check FAILED for {name}.{K}.{i}")
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Negate pddef7 reverse interpolants and write CNF (DIMACS). "
            "Reads a success CSV produced by manage_spd_computation.py "
            "--show_success --reverse."
        )
    )
    ap.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to success CSV (default: auto-derived from --K via get_spd7_success_csv)",
    )
    ap.add_argument("--K", type=int, required=True, help="K value")
    ap.add_argument("--name", type=str, default=None, help="Process only this instance name")
    ap.add_argument("--i", type=int, default=None, help="Process only this index")
    ap.add_argument("--force_refresh", action="store_true", default=False)
    ap.add_argument(
        "--verify_only",
        action="store_true",
        default=False,
        help="Skip negation/write; only re-run validity checks on existing outputs",
    )
    args = ap.parse_args()

    # Fast path: all three identifiers given — no CSV needed.
    if args.name is not None and args.i is not None:
        if args.verify_only:
            verify_negated_entry(args.name, args.K, args.i)
        else:
            process_entry(args.name, args.K, args.i, force_refresh=args.force_refresh)
        return

    csv_path = args.csv if args.csv is not None else get_spd7_success_csv(args.K)
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        entries = [(row["name"], int(row["K"]), int(row["i"])) for row in reader]

    if args.name is not None:
        entries = [(n, k, i) for n, k, i in entries if n == args.name]
    if args.i is not None:
        entries = [(n, k, i) for n, k, i in entries if i == args.i]

    print(f"Processing {len(entries)} entries from {csv_path}")
    for name, K, i in entries:
        if args.verify_only:
            verify_negated_entry(name, K, i)
        else:
            process_entry(name, K, i, force_refresh=args.force_refresh)


if __name__ == "__main__":
    main()
