import os
import sys
import subprocess
import tempfile
import argparse
import csv
import json
import re
import shutil

# Allow imports from the scripts/ directory (parent of this file's directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.paths import (
    get_CNF_dir,
    get_interpolant_cnf_dir,
    get_interpolant_dir,
    get_progressive_qdimacs_dir,
)

PREPROCESS_BIN = "./External/kissat_bve/build/preprocess"
CADICAL_BIN    = "./solvers/cadical"
CNF_CONVERSION_LOG_DIR = "./SlurmLogs/minimum_smt_to_cnf"
REGRESSION_SUMMARY_PATH = "./regression_summary.csv"


def get_python_activate_command():
    return "source ../../general/bin/activate"


def get_instances_by_category(category):
    instances = []
    with open(REGRESSION_SUMMARY_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['best_model'] == category:
                instances.append(row['instance_name'])
    return instances


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


def _extract_v_ids(sexpr):
    return sorted({int(m.group(1)) for m in re.finditer(r"\bv(\d+)\b", sexpr)})


def _wrap_with_declarations_and_assert(content):
    content = content.strip()
    if content.startswith("(declare-") or content.startswith("(assert"):
        return content
    variables = _extract_v_ids(content)
    declarations = "\n".join(f"(declare-const v{var} Bool)" for var in variables)
    return f"{declarations}\n(assert {content})\n"


def _parse_z3_formula_sexpr(sexpr):
    from z3 import parse_smt2_string  # type: ignore

    vec = parse_smt2_string(_wrap_with_declarations_and_assert(sexpr))
    if len(vec) != 1:
        raise ValueError("Expected exactly one Boolean formula in interpolant sexpr")
    return vec[0]


def _read_formula_interpolant(path):
    with open(path, "r") as f:
        obj = json.load(f)
    if not isinstance(obj, dict) or "IS" not in obj:
        raise ValueError(f"Interpolant JSON missing 'IS': {path}")
    sexpr = str(obj["IS"]).strip()
    if not sexpr:
        raise ValueError(f"Interpolant 'IS' is empty: {path}")
    return sexpr, _parse_z3_formula_sexpr(sexpr)


def _write_formula_interpolant(path, sexpr):
    with open(path, "w") as f:
        json.dump({"IS": sexpr}, f)


def _load_interpolant_for_z3(path):
    """
    Load a previous interpolant as a Z3 formula.

    Supports both the new JSON/sexpr format and the older QDIMACS-clause format
    so that existing artifacts remain usable during migration.
    """
    with open(path, "r") as f:
        first_non_ws = None
        while True:
            ch = f.read(1)
            if not ch:
                break
            if not ch.isspace():
                first_non_ws = ch
                break

    if first_non_ws == "{":
        return _read_formula_interpolant(path)

    clauses = read_qdimacs_clauses(path)
    expr = _z3_cnf_expr(clauses, {})
    return expr.sexpr(), expr


def _z3_clause_expr(clause, bool_vars):
    from z3 import Bool, BoolVal, Not, Or  # type: ignore

    if not clause:
        return BoolVal(False)
    literals = []
    for lit in clause:
        var = bool_vars.setdefault(abs(lit), Bool(f"v{abs(lit)}"))
        literals.append(var if lit > 0 else Not(var))
    return Or(literals) if len(literals) > 1 else literals[0]


def _z3_cnf_expr(clauses, bool_vars):
    from z3 import And, BoolVal  # type: ignore

    if _cnf_is_false(clauses):
        return BoolVal(False)
    if _cnf_is_true(clauses):
        return BoolVal(True)
    clause_exprs = [_z3_clause_expr(clause, bool_vars) for clause in clauses]
    return And(clause_exprs) if len(clause_exprs) > 1 else clause_exprs[0]


def _z3_is_literal(expr):
    from z3 import Z3_BOOL_SORT, is_const, is_not  # type: ignore

    if is_const(expr) and expr.sort().kind() == Z3_BOOL_SORT:
        return True
    if is_not(expr):
        child = expr.children()[0]
        return is_const(child) and child.sort().kind() == Z3_BOOL_SORT
    return False


def _z3_literal_to_int(expr):
    from z3 import is_not  # type: ignore

    if is_not(expr):
        child = expr.children()[0]
        return -int(child.decl().name().lstrip("v"))
    return int(expr.decl().name().lstrip("v"))


def _z3_exact_cnf(expr):
    from z3 import is_and, is_false, is_or, is_true  # type: ignore

    if is_true(expr):
        return []
    if is_false(expr):
        return [[]]
    if _z3_is_literal(expr):
        return [[_z3_literal_to_int(expr)]]
    if is_and(expr):
        clauses = []
        for child in expr.children():
            child_cnf = _z3_exact_cnf(child)
            if _cnf_is_false(child_cnf):
                return [[]]
            clauses.extend(child_cnf)
        return _dedupe_clauses(clauses)
    if is_or(expr):
        combined = [[]]
        for child in expr.children():
            child_cnf = _z3_exact_cnf(child)
            if _cnf_is_true(child_cnf):
                return []
            if _cnf_is_false(child_cnf):
                continue
            merged = []
            for base_clause in combined:
                for child_clause in child_cnf:
                    normalized = _normalize_clause(base_clause + child_clause)
                    if normalized is None:
                        continue
                    merged.append(list(normalized))
            combined = _dedupe_clauses(merged)
            if _cnf_is_true(combined):
                return []
        return combined
    raise ValueError(f"Unsupported non-CNF Z3 node after NNF: {expr.sexpr()}")


def eliminate_not_b_with_z3(b_clauses, shared_vars):
    """
    Compute a quantifier-free formula for ¬∃ local(B). B over the shared vocabulary.

    This is equivalent to ∀ local(B). ¬B.
    """
    try:
        from z3 import Exists, Goal, Not, Tactic  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Z3 backend requested, but the Python 'z3-solver' package is not available."
        ) from exc

    bool_vars = {}
    b_expr = _z3_cnf_expr(b_clauses, bool_vars)
    local_vars = sorted(set(bool_vars) - set(shared_vars))
    if local_vars:
        qe_goal = Goal()
        quantified = [bool_vars[var] for var in local_vars]
        qe_goal.add(Not(Exists(quantified, b_expr)))
        projection = Tactic("qe")(qe_goal)[0].as_expr()
    else:
        projection = Not(b_expr)
    simplify_goal = Goal()
    simplify_goal.add(projection)
    simplified = Tactic("simplify")(simplify_goal)[0].as_expr()
    return simplified


def _z3_unsat(*exprs):
    from z3 import Solver, unsat  # type: ignore

    solver = Solver()
    solver.add(*exprs)
    return solver.check() == unsat


def verify_interpolant_formula(ia_expr, m_expr, b_expr, label=""):
    from z3 import Not  # type: ignore

    tag = f"[{label}] " if label else ""
    mb_unsat = _z3_unsat(m_expr, b_expr)
    print(f"{tag}M → ¬B (M ∧ B UNSAT): {mb_unsat}")
    am_valid = _z3_unsat(ia_expr, Not(m_expr))
    print(f"{tag}A → M  (A ∧ ¬M UNSAT): {am_valid}")
    return am_valid and mb_unsat


def _submit_minimum_to_cnf_job(name, K, i, force_refresh=False):
    if shutil.which("sbatch") is None:
        print("[WARN] sbatch not found; skipping async CNF conversion job submission")
        return None

    log_dir = os.path.join(CNF_CONVERSION_LOG_DIR, f"k_{K}")
    os.makedirs(log_dir, exist_ok=True)
    force_flag = " --force_refresh" if force_refresh else ""
    inner = (
        f"python scripts/MinimumInterpolantToCNF.py"
        f" --instance {name} --K {K} --index {i}{force_flag}"
    )
    wrapped = f"{get_python_activate_command()} && source ./.env && {inner}"
    output = os.path.join(log_dir, f"{name}.{K}.%A_{i}.log")
    job_name = f"min2cnf_{name}.{K}.{i}"
    result = subprocess.run(
        [
            "sbatch",
            f"--job-name={job_name}",
            f"--output={output}",
            "--mem=32g",
            "--time=20:00:00",
            f"--wrap={wrapped}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    tokens = result.stdout.strip().split()
    job_id = tokens[-1] if tokens else ""
    print(f"Submitted CNF conversion job {job_id} for {name}.{K}.{i}")
    return job_id


def _run_minimum_to_cnf_local(name, K, i, force_refresh=False):
    from MinimumInterpolantToCNF import minimum_to_cnf

    print(f"Running local CNF conversion for {name}.{K}.{i}")
    out_path = minimum_to_cnf(name, K, i, force_refresh=force_refresh)
    print(f"Local CNF conversion written to: {out_path}")
    return out_path


def _read_smtcnf_clauses_for_verification(path):
    from utils.process_cnf import CNF

    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if os.path.getsize(path) == 0:
        return []
    return CNF.from_file(path, skip_parse_literal_map=True).clauses


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
    Verify that M is a valid interpolant between A and B:
      1. A → M  :  A ∧ ¬M is UNSAT
      2. M → ¬B :  M ∧ B  is UNSAT

    A is represented by ia_clauses (M_{i-1} ∧ A_i, the A side).
    M is i_out_clauses (BVE output).
    B is b_clauses (all clauses after iteration i).

    ¬M is encoded via Tseitin: introduce one selector variable s_j per clause
    c_j in M.  The encoding adds:
      - (s_1 ∨ … ∨ s_k)            — at least one clause is violated
      - (¬s_j ∨ ¬l) for each l∈c_j — if s_j is set, every literal of c_j is false

    Returns True if both checks pass, False otherwise.
    Prints the outcome for each check.
    """
    tag = f"[{label}] " if label else ""

    # --- Check 2: M ∧ B = UNSAT ---
    mb_unsat = _run_cadical_unsat(i_out_clauses, b_clauses)
    print(f"{tag}M → ¬B (M ∧ B UNSAT): {mb_unsat}")

    # --- Check 1: A → M (A ∧ ¬M UNSAT) ---
    # Build Tseitin encoding of ¬M
    if _cnf_is_true(i_out_clauses):
        # Empty M is True; A → True always holds.
        am_valid = True
    elif _cnf_is_false(i_out_clauses):
        # M is False; A → False iff A itself is UNSAT.
        am_valid = _run_cadical_unsat(ia_clauses)
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
        am_unsat = _run_cadical_unsat(ia_clauses, selector_clauses)
        am_valid = am_unsat
    print(f"{tag}A → M  (A ∧ ¬M UNSAT): {am_valid}")

    return am_valid and mb_unsat


def compute_mpd(name, K, i, export_qdimacs_only=False,
                backend="preprocess",
                conversion_mode="slurm",
                initialbound=None,
                eliminatebound=None, eliminaterounds=None,
                eliminateclslim=None, eliminateocclim=None,
                eliminateeffort=None):
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

    # M_prev: previous interpolant used to define the shared vocabulary.
    interp_dir = get_interpolant_dir(K, pddef=6)
    interp_cnf_dir = get_interpolant_cnf_dir(K, pddef=6)
    if i == 0:
        m_clauses = []
    else:
        if backend in ("not_b", "z3_not_b"):
            prev_path = os.path.join(interp_cnf_dir, f"{name}.{K}.{i-1}.smtcnf")
            if not os.path.exists(prev_path):
                raise FileNotFoundError(
                    f"Previous converted interpolant not found: {prev_path}"
                )
            m_clauses = _read_smtcnf_clauses_for_verification(prev_path)
        else:
            prev_path = os.path.join(interp_dir, f"{name}.{K}.{i-1}.interpolant")
            if not os.path.exists(prev_path):
                raise FileNotFoundError(f"Previous interpolant not found: {prev_path}")
            m_clauses = read_qdimacs_clauses(prev_path)

    ia_clauses = m_clauses + a_clauses
    vars_in_ia = {abs(lit) for clause in ia_clauses for lit in clause}

    # BVE input: B_i  — the side we project in the preprocess backend.
    vars_in_b  = {abs(lit) for clause in b_clauses  for lit in clause}
    elim_vars  = vars_in_b - vars_in_ia
    max_var    = max(vars_in_b) if vars_in_b else 0

    # Write the preprocess backend input QDIMACS.
    qdimacs_dir  = get_progressive_qdimacs_dir(K, tag="mpd")
    qdimacs_path = os.path.join(qdimacs_dir, f"{name}.{K}.{i}.qdimacs")
    write_qdimacs(qdimacs_path, max_var, b_clauses, elim_vars)
    print(f"QDIMACS written to: {qdimacs_path}")

    if export_qdimacs_only:
        if backend != "preprocess":
            print("[WARN] export_qdimacs_only exports the preprocess-backend input CNF of B.")
        return qdimacs_path

    output_path = os.path.join(interp_dir, f"{name}.{K}.{i}.interpolant")
    if backend == "preprocess":
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
    elif backend in ("not_b", "z3_not_b"):
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

        print(f"Running preprocess QE for ∃local(B).B on {name}.{K}.{i}")
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
        if conversion_mode == "slurm":
            _submit_minimum_to_cnf_job(name, K, i, force_refresh=True)
        elif conversion_mode == "local":
            _run_minimum_to_cnf_local(name, K, i, force_refresh=True)
        else:
            raise ValueError(f"Unsupported conversion mode: {conversion_mode}")
    else:
        raise ValueError(f"Unsupported backend: {backend}")
    print(f"Minimum interpolant written to: {output_path}")

    label = f"{name}.{K}.{i}"
    if backend in ("not_b", "z3_not_b"):
        if conversion_mode == "slurm":
            print(
                f"[{label}] Deferred final '(not (exists local(B) B))' conversion "
                f"and verification to the CNF conversion job."
            )
            return output_path
        converted_path = os.path.join(interp_cnf_dir, f"{name}.{K}.{i}.smtcnf")
        m_out_clauses = _read_smtcnf_clauses_for_verification(converted_path)
    else:
        m_out_clauses = read_qdimacs_clauses(output_path)
    ok = verify_interpolant(ia_clauses, m_out_clauses, b_clauses, label=label)
    if not ok:
        print(f"ERROR: interpolant validity check FAILED for {label}")
        sys.exit(1)

    print(f"Interpolant validity check passed for {label}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description='Compute one step of the minimum PD interpolant via BVE preprocessing'
    )
    parser.add_argument('--name', help='Instance name')
    parser.add_argument('--category', choices=('linear', 'exponential'),
                        help='Run over all instances in this regression_summary category')
    parser.add_argument('--K',    type=int, required=True, help='K value')
    parser.add_argument('--i',    type=int, help='Iteration index; if omitted, run all indices 0..K-1')
    parser.add_argument('--export_qdimacs_only', action='store_true',
                        help='Only write the input QDIMACS; skip the preprocess step')
    parser.add_argument('--backend', choices=('preprocess', 'not_b', 'z3_not_b'),
                        default='preprocess',
                        help='Interpolant backend: preprocess projects B; not_b runs preprocess+force QE for exists local(B).B and then converts to not exists local(B).B; z3_not_b is a deprecated alias for not_b')
    parser.add_argument('--conversion_mode', choices=('slurm', 'local'),
                        default='slurm',
                        help='For backend not_b only: run final conversion via Slurm job or directly in the current process')
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

    if args.name is None and args.category is None:
        parser.error("either --name or --category is required")
    if args.conversion_mode != 'slurm' and args.backend == 'preprocess':
        args.backend = 'not_b'
    if args.backend == 'z3_not_b':
        args.backend = 'not_b'
    if args.backend == 'not_b' and args.conversion_mode == 'slurm' and args.i is None:
        parser.error(
            "--backend not_b with --conversion_mode slurm requires --i; "
            "for all indices use --conversion_mode local"
        )

    names = [args.name] if args.name is not None else get_instances_by_category(args.category)
    if not names:
        parser.error(f"no instances found for category '{args.category}'")
    indices = [args.i] if args.i is not None else list(range(args.K))

    failures = []
    for name in names:
        for i in indices:
            if len(names) > 1 or len(indices) > 1:
                print(f"=== Running {name}.{args.K}.{i} ===")
            try:
                compute_mpd(
                    name,
                    args.K,
                    i,
                    export_qdimacs_only=args.export_qdimacs_only,
                    backend=args.backend,
                    conversion_mode=args.conversion_mode,
                    initialbound=args.initialbound,
                    eliminatebound=args.eliminatebound,
                    eliminaterounds=args.eliminaterounds,
                    eliminateclslim=args.eliminateclslim,
                    eliminateocclim=args.eliminateocclim,
                    eliminateeffort=args.eliminateeffort,
                )
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
                if code != 0:
                    failures.append(f"{name}.{args.K}.{i}")
            except Exception:
                failures.append(f"{name}.{args.K}.{i}")
                raise

    if failures:
        print("Failed tasks:")
        for task in failures:
            print(f"  {task}")
        sys.exit(1)


if __name__ == '__main__':
    main()
