#!/usr/bin/env python3
"""
Convert minimum interpolants (pddef=6) from QDIMACS CNF into negated `.smtcnf`.

The `.interpolant` file is treated as the QE result `exists local(B). B`.
This script performs the conversion stage for the final object:

  not (exists local(B). B)

and writes the result as `.smtcnf`.
"""

from __future__ import annotations

import argparse
import os
import shutil
from typing import List, Optional

from utils.paths import get_interpolant_cnf_dir, get_interpolant_dir
from StrongestInterpolantToCNF import (
    _CNF_CACHE,
    _as_smtcnf_literals,
    _extract_v_ids,
    _write_dimacs,
    _write_smtcnf,
    expand_to_cnf,
)


def get_python_activate_command():
    return "source ../../general/bin/activate"


def read_qdimacs_clauses(path: str) -> List[List[int]]:
    clauses: List[List[int]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ("c", "p", "a", "e"):
                continue
            clauses.append([int(tok) for tok in line.split() if tok != "0"])
    return clauses


def _cnf_is_true(clauses: List[List[int]]) -> bool:
    return len(clauses) == 0


def _cnf_is_false(clauses: List[List[int]]) -> bool:
    return any(len(clause) == 0 for clause in clauses)


def _z3_clause_expr(clause, bool_vars):
    from z3 import Bool, BoolVal, Not, Or  # type: ignore

    if not clause:
        return BoolVal(False)
    literals = []
    for lit in clause:
        var = bool_vars.setdefault(abs(lit), Bool(f"v{abs(lit)}"))
        literals.append(var if lit > 0 else Not(var))
    return Or(literals) if len(literals) > 1 else literals[0]


def _z3_cnf_expr(clauses):
    from z3 import And, BoolVal  # type: ignore

    bool_vars = {}
    if _cnf_is_false(clauses):
        return BoolVal(False)
    if _cnf_is_true(clauses):
        return BoolVal(True)
    clause_exprs = [_z3_clause_expr(clause, bool_vars) for clause in clauses]
    return And(clause_exprs) if len(clause_exprs) > 1 else clause_exprs[0]


def minimum_to_cnf(
    instance: str,
    K: int,
    index: int,
    *,
    simplify: bool = True,
    force_refresh: bool = False,
    dimacs_out: Optional[str] = None,
) -> str:
    from z3 import Goal, Not, Tactic, is_false, is_true  # type: ignore

    _CNF_CACHE.clear()

    interp_file = f"{get_interpolant_dir(K, 6)}/{instance}.{K}.{index}.interpolant"
    out_smtcnf = f"{get_interpolant_cnf_dir(K, 6)}/{instance}.{K}.{index}.smtcnf"

    if (not force_refresh) and os.path.exists(out_smtcnf) and os.path.getsize(out_smtcnf) > 0:
        return out_smtcnf
    if not os.path.exists(interp_file) or os.path.getsize(interp_file) == 0:
        raise FileNotFoundError(f"Minimum interpolant file not found/empty: {interp_file}")

    clauses = read_qdimacs_clauses(interp_file)
    expr = Not(_z3_cnf_expr(clauses))

    goal = Goal()
    goal.add(expr)
    simplified_expr = Tactic("simplify")(goal)[0].as_expr()

    if is_false(simplified_expr):
        ids = _extract_v_ids(simplified_expr.sexpr())
        fresh = (max(ids) + 1) if ids else 1
        cnf_tokens = [[f"v{fresh}"], [f"Not(v{fresh})"]]
        _write_smtcnf(out_smtcnf, cnf_tokens)
        if dimacs_out:
            _write_dimacs(dimacs_out, cnf_tokens)
        return out_smtcnf
    if is_true(simplified_expr):
        os.makedirs(os.path.dirname(out_smtcnf), exist_ok=True)
        with open(out_smtcnf, "w") as f:
            pass
        if dimacs_out:
            _write_dimacs(dimacs_out, [])
        return out_smtcnf

    nnf_goal = Goal()
    nnf_goal.add(simplified_expr)
    nnf_goal = Tactic("nnf")(nnf_goal)
    nnf_goal = Tactic("simplify")(nnf_goal[0])

    cnf_list = []
    for nnf in nnf_goal[0]:
        cnf_list.extend(expand_to_cnf(nnf, simplify=simplify))

    cnf_tokens: List[List[str]] = []
    for clause in cnf_list:
        toks = _as_smtcnf_literals(clause)
        if toks:
            cnf_tokens.append(toks)

    _write_smtcnf(out_smtcnf, cnf_tokens)
    if dimacs_out:
        _write_dimacs(dimacs_out, cnf_tokens)
    return out_smtcnf


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert minimum interpolant (def6) QDIMACS to negated CNF (.smtcnf, optional DIMACS).")
    ap.add_argument("--instance", required=False, type=str, default=None)
    ap.add_argument("--K", required=True, type=int)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--force_refresh", action="store_true", default=False)
    ap.add_argument("--simplify", action="store_true", default=True)
    ap.add_argument("--manage", action="store_true", default=False, help="Submit K Slurm jobs (one per index).")
    ap.add_argument("--mem", type=str, default="32g")
    ap.add_argument("--time", type=str, default="20:00:00")
    ap.add_argument(
        "--activate",
        type=str,
        default=get_python_activate_command(),
        help="Shell snippet to activate Python env for Slurm jobs.",
    )
    ap.add_argument("--dimacs_out", type=str, default=None)
    args = ap.parse_args()

    if args.manage:
        if shutil.which("sbatch") is None:
            raise RuntimeError("sbatch not found in PATH; cannot run --manage")
        if not args.instance:
            raise ValueError("--instance is required with --manage")
        logs_dir = f"./SlurmLogs/minimum_smt_to_cnf/k_{args.K}/"
        os.makedirs(logs_dir, exist_ok=True)
        force_flag = "--force_refresh" if args.force_refresh else ""
        simplify_flag = "--simplify" if args.simplify else ""
        dimacs_flag = f"--dimacs_out {args.dimacs_out}" if args.dimacs_out else ""
        job_ids = []
        for i in range(args.K):
            inner = (
                f"python scripts/MinimumInterpolantToCNF.py "
                f"--instance {args.instance} --K {args.K} --index {i} "
                f"{force_flag} {simplify_flag} {dimacs_flag}"
            ).strip()
            wrapped = f"{args.activate} && source .env && {inner}"
            output = f"{logs_dir}/{args.instance}.{args.K}.%A_{i}.log"
            job_name = f"min2cnf_{args.instance}.{args.K}.{i}"
            cmd = (
                f"sbatch --job-name={job_name} --output={output} "
                f"--mem={args.mem} --time={args.time} --wrap=\"{wrapped}\""
            )
            job_ids.append(os.popen(cmd).read().split()[-1])
        print(" ".join(job_ids))
        return

    if args.index is None:
        raise ValueError("--index is required unless you use --manage")
    if not args.instance:
        raise ValueError("--instance is required unless you use --manage")

    print(
        minimum_to_cnf(
            args.instance,
            args.K,
            args.index,
            simplify=args.simplify,
            force_refresh=args.force_refresh,
            dimacs_out=args.dimacs_out,
        )
    )


if __name__ == "__main__":
    main()
