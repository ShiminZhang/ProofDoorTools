#!/usr/bin/env python3
"""
Convert strongest interpolant (pddef=4) to CNF.

Background:
  - def1 interpolants are Z3 outputs in the form:
      unsat
      (interpolants ...)
    and are handled by `scripts/SMTTranslationToCNFExperiment.py`.
  - strongest interpolants (def4) in this repo are stored as JSON:
      {"IS": "<z3-sexpr>"}
    where <z3-sexpr> is a quantifier-free Boolean formula over variables `v<id>`.

This script reads the JSON, parses the sexpr via Z3, converts it to CNF, and writes:
  - a ".smtcnf" file (one clause per line, literals are "v123" or "Not(v123)")
  - optionally also a DIMACS ".cnf" file.

Notes on constants:
  - If IS is "false", we output an UNSAT CNF using a fresh variable (max_v+1):
      vFresh
      Not(vFresh)
    (satisfiability-equivalent to false).
  - If IS is "true", the CNF is empty (no clauses), so the output file is empty.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from typing import List, Optional, Sequence, Tuple

from utils.paths import get_interpolant_cnf_dir, get_interpolant_dir


def wrap_with_declarations_and_assert(content: str) -> str:
    """
    Like `utils.parsing.wrap_with_declarations_and_assert`, but kept local so that
    `--manage` can run even if z3 isn't importable in the current environment.
    """
    content = content.strip()
    if content.startswith("(declare-") or content.startswith("(assert"):
        return content
    variables = set(re.findall(r"\bv\d+\b", content))
    declarations = "\n".join(f"(declare-const {var} Bool)" for var in sorted(variables))
    return f"{declarations}\n(assert {content})\n"


def _extract_v_ids(sexpr: str) -> List[int]:
    # Match whole tokens v123 (avoid matching "inv1" etc.)
    ids = [int(m.group(1)) for m in re.finditer(r"\bv(\d+)\b", sexpr)]
    ids.sort()
    return ids


def parse_strongest_interpolant(file_path: str):
    """
    Returns (ast_vector, raw_IS_sexpr).
    """
    from z3 import parse_smt2_string  # type: ignore

    with open(file_path, "r") as f:
        obj = json.load(f)
    if not isinstance(obj, dict) or "IS" not in obj:
        raise ValueError(f"Strongest interpolant JSON missing 'IS': {file_path}")
    sexpr = str(obj["IS"]).strip()
    if sexpr == "":
        raise ValueError(f"Strongest interpolant 'IS' is empty: {file_path}")
    wrapped = wrap_with_declarations_and_assert(sexpr)
    return parse_smt2_string(wrapped), sexpr


def is_literal(expr) -> bool:
    from z3 import Z3_BOOL_SORT, Z3_OP_NOT, is_const  # type: ignore

    # Boolean variable
    if is_const(expr) and expr.sort().kind() == Z3_BOOL_SORT:
        return True
    # (not p) where p is Boolean variable
    if expr.decl().kind() == Z3_OP_NOT:
        child = expr.children()[0]
        return is_const(child) and child.sort().kind() == Z3_BOOL_SORT
    return False


_CNF_CACHE = {}


def _is_tautological_clause(literals) -> bool:
    from z3 import Not, is_not  # type: ignore

    for lit in literals:
        if is_not(lit):
            if lit.children()[0] in literals:
                return True
        elif Not(lit) in literals:
            return True
    return False


def _clause_sort_key(clause) -> Tuple[int, Tuple[str, ...]]:
    return (len(clause), tuple(sorted(map(str, clause))))


def simplify_and_subsume(clauses):
    normalized = []
    for clause in clauses:
        clause_frozen = clause if isinstance(clause, frozenset) else frozenset(clause)
        if _is_tautological_clause(clause_frozen):
            continue
        normalized.append(clause_frozen)

    normalized.sort(key=_clause_sort_key)

    result = []
    for c in normalized:
        if any(d.issubset(c) for d in result):
            continue
        result.append(c)
    return tuple(result)


def expand_to_cnf(expr, simplify: bool = True):
    """
    Convert a Z3 Boolean expression (NNF) into a *logically equivalent* CNF clause list.
    Output: tuple[frozenset[z3.ExprRef], ...]
    """
    if not simplify:
        raise ValueError("expand_to_cnf expects simplify=True (kept for compatibility).")

    cache_key = (expr.get_id(), simplify)
    if cache_key in _CNF_CACHE:
        return _CNF_CACHE[cache_key]

    if is_literal(expr):
        result = (frozenset((expr,)),)
        _CNF_CACHE[cache_key] = result
        return result

    from z3 import is_and, is_or  # type: ignore

    if is_and(expr):
        clauses = []
        for sub in expr.children():
            clauses.extend(expand_to_cnf(sub, True))
        result = simplify_and_subsume(clauses)
        _CNF_CACHE[cache_key] = result
        return result

    if is_or(expr):
        sub_cnf_list = [expand_to_cnf(sub, True) for sub in expr.children()]
        combined = (frozenset(),)
        for sub_cnf in sub_cnf_list:
            sub_clause_sets = [c if isinstance(c, frozenset) else frozenset(c) for c in sub_cnf]
            new_clauses = []
            seen = set()
            for base_clause in combined:
                for clause_set in sub_clause_sets:
                    merged = base_clause | clause_set
                    if _is_tautological_clause(merged):
                        continue
                    if merged in seen:
                        continue
                    new_clauses.append(merged)
                    seen.add(merged)
            combined = simplify_and_subsume(new_clauses)
        _CNF_CACHE[cache_key] = combined
        return combined

    # Fallback: treat as literal-ish atom (keeps script robust).
    result = (frozenset((expr,)),)
    _CNF_CACHE[cache_key] = result
    return result


def _as_smtcnf_literals(clause) -> List[str]:
    """
    Convert a CNF clause (set of z3 literals) to a list[str] like ["v1", "Not(v2)"].
    """
    lits: List[str] = []
    for lit in sorted(clause, key=str):
        # bool constants should not appear in normal runs; handle conservatively
        if str(lit) in ("True", "False"):
            continue
        s = str(lit)
        # expect "v123" or "Not(v123)"
        lits.append(s)
    return lits


def _write_smtcnf(out_path: str, cnf_clauses: Sequence[Sequence[str]]) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        for clause in cnf_clauses:
            f.write(" ".join(clause))
            f.write("\n")


def _write_dimacs(out_path: str, cnf_clauses: Sequence[Sequence[str]]) -> None:
    # literals are "v123" or "Not(v123)"
    max_var = 0
    dimacs_lines: List[str] = []
    for clause in cnf_clauses:
        if not clause:
            dimacs_lines.append("0")
            continue
        ints: List[int] = []
        for lit in clause:
            lit = lit.strip()
            if lit.startswith("Not(") and lit.endswith(")"):
                v = int(lit[4:-1].lstrip("v"))
                ints.append(-v)
                max_var = max(max_var, v)
            else:
                v = int(lit.lstrip("v"))
                ints.append(v)
                max_var = max(max_var, v)
        dimacs_lines.append(" ".join(map(str, ints)) + " 0")
    header = f"p cnf {max_var} {len(dimacs_lines)}"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(header + "\n")
        for line in dimacs_lines:
            f.write(line + "\n")


def strongest_to_cnf(
    instance: str,
    K: int,
    index: int,
    *,
    simplify: bool = True,
    force_refresh: bool = False,
    dimacs_out: Optional[str] = None,
) -> str:
    from z3 import Goal, Tactic  # type: ignore

    _CNF_CACHE.clear()

    strongest_file = f"{get_interpolant_dir(K, 4)}/{instance}.{K}.{index}.interpolant"
    out_smtcnf = f"{get_interpolant_cnf_dir(K, 4)}/{instance}.{K}.{index}.smtcnf"

    if (not force_refresh) and os.path.exists(out_smtcnf) and os.path.getsize(out_smtcnf) > 0:
        return out_smtcnf

    if not os.path.exists(strongest_file) or os.path.getsize(strongest_file) == 0:
        raise FileNotFoundError(f"Strongest interpolant file not found/empty: {strongest_file}")

    vec, raw_sexpr = parse_strongest_interpolant(strongest_file)
    # The file is a single formula; parse_smt2_string returns assertions in an AstVector
    if len(vec) == 0:
        raise ValueError(f"Parsed strongest interpolant is empty: {strongest_file}")

    # Special-case constants early (they otherwise become "True"/"False" literals).
    raw_lower = raw_sexpr.strip().lower()
    if raw_lower == "false":
        ids = _extract_v_ids(raw_sexpr)
        fresh = (max(ids) + 1) if ids else 1
        cnf_tokens = [[f"v{fresh}"], [f"Not(v{fresh})"]]
        _write_smtcnf(out_smtcnf, cnf_tokens)
        if dimacs_out:
            _write_dimacs(dimacs_out, cnf_tokens)
        return out_smtcnf
    if raw_lower == "true":
        # CNF is empty (no clauses).
        os.makedirs(os.path.dirname(out_smtcnf), exist_ok=True)
        with open(out_smtcnf, "w") as f:
            pass
        if dimacs_out:
            _write_dimacs(dimacs_out, [])
        return out_smtcnf

    # Convert to NNF then to CNF (equivalent, no auxiliaries).
    goal = Goal()
    for fml in vec:
        goal.add(fml)
    nnf_goal = Tactic("nnf")(goal)
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


def _find_complete_instances(K: int) -> List[str]:
    interpolant_dir = get_interpolant_dir(K, 4)
    if not os.path.exists(interpolant_dir):
        return []
    index_map = {}
    for fname in os.listdir(interpolant_dir):
        if not fname.endswith(".interpolant"):
            continue
        parts = fname.rsplit(".", 3)
        if len(parts) != 4:
            continue
        instance, k_str, index_str, suffix = parts
        if suffix != "interpolant" or k_str != str(K):
            continue
        try:
            index = int(index_str)
        except ValueError:
            continue
        if index < 0 or index >= K:
            continue
        full_path = os.path.join(interpolant_dir, fname)
        if os.path.getsize(full_path) == 0:
            continue
        index_map.setdefault(instance, set()).add(index)
    return sorted([inst for inst, idxs in index_map.items() if len(idxs) == K])


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert strongest interpolant (def4) JSON to CNF (.smtcnf, optional DIMACS).")
    ap.add_argument("--instance", required=False, type=str, default=None)
    ap.add_argument("--K", required=True, type=int)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument(
        "--auto_complete",
        action="store_true",
        default=False,
        help="Auto-find instances with all K interpolants computed and convert them to CNF.",
    )
    ap.add_argument(
        "--manage",
        action="store_true",
        default=False,
        help="Submit K Slurm jobs (one per index).",
    )
    ap.add_argument("--force_refresh", action="store_true", default=False)
    ap.add_argument("--simplify", action="store_true", default=True)
    ap.add_argument("--mem", type=str, default="32g", help="Slurm mem for --manage")
    ap.add_argument("--time", type=str, default="20:00:00", help="Slurm time for --manage")
    ap.add_argument(
        "--activate",
        type=str,
        default="source .env; source $PYENVPATH",
        help="Shell snippet to activate Python env for Slurm jobs.",
    )
    ap.add_argument(
        "--dimacs_out",
        type=str,
        default=None,
        help="Optional DIMACS CNF output path (e.g. ./tmp/foo.cnf).",
    )
    args = ap.parse_args()

    if args.auto_complete and args.dimacs_out:
        raise ValueError("--dimacs_out is not supported with --auto_complete")

    if args.manage:
        if shutil.which("sbatch") is None:
            raise RuntimeError("sbatch not found in PATH; cannot run --manage")

        logs_dir = f"./SlurmLogs/strongest_smt_to_cnf/k_{args.K}/"
        os.makedirs(logs_dir, exist_ok=True)
        force_refresh_flag = "--force_refresh" if args.force_refresh else ""
        simplify_flag = "--simplify" if args.simplify else ""
        dimacs_flag = f"--dimacs_out {args.dimacs_out}" if args.dimacs_out else ""

        job_ids: List[str] = []
        if args.auto_complete:
            instances = _find_complete_instances(args.K)
            if not instances:
                print("No instances with complete strongest interpolants found.")
                return
        else:
            if not args.instance:
                raise ValueError("--instance is required unless you use --auto_complete")
            instances = [args.instance]

        for instance in instances:
            for i in range(args.K):
                inner = (
                    f"python scripts/StrongestInterpolantToCNF.py "
                    f"--instance {instance} --K {args.K} --index {i} "
                    f"{force_refresh_flag} {simplify_flag} {dimacs_flag}"
                ).strip()
                wrapped = f"{args.activate} && {inner}"
                output = f"{logs_dir}/{instance}.{args.K}.%A_{i}.log"
                job_name = f"strong2cnf_{instance}.{args.K}.{i}"
                cmd = (
                    f"sbatch --job-name={job_name} --output={output} "
                    f"--mem={args.mem} --time={args.time} --wrap=\"{wrapped}\""
                )
                job_id = os.popen(cmd).read().split()[-1]
                job_ids.append(job_id)

        print(" ".join(job_ids))
        return

    if args.auto_complete:
        instances = _find_complete_instances(args.K)
        if not instances:
            print("No instances with complete strongest interpolants found.")
            return
        for instance in instances:
            for i in range(args.K):
                strongest_to_cnf(
                    instance,
                    args.K,
                    i,
                    simplify=args.simplify,
                    force_refresh=args.force_refresh,
                    dimacs_out=args.dimacs_out,
                )
        print(f"Converted strongest interpolants to CNF for {len(instances)} instance(s).")
        return

    if args.index is None:
        raise ValueError("--index is required unless you use --manage/--auto_complete")
    if not args.instance:
        raise ValueError("--instance is required unless you use --auto_complete")

    out = strongest_to_cnf(
        args.instance,
        args.K,
        args.index,
        simplify=args.simplify,
        force_refresh=args.force_refresh,
        dimacs_out=args.dimacs_out,
    )
    print(out)


if __name__ == "__main__":
    main()

