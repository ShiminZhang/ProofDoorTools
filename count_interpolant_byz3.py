#!/usr/bin/env python3
import sys
import re
from copy import deepcopy
from z3 import *
from z3 import Context
import signal
import subprocess
import argparse
import json
import os


def tokenize(s):
    s = re.sub(r'([\(\)])', r' \1 ', s)
    return s.split()

def parse(tokens):
    if not tokens:
        raise SyntaxError("Unexpected EOF")
    token = tokens.pop(0)
    if token == '(':
        expr = []
        while tokens[0] != ')':
            expr.append(parse(tokens))
            if not tokens:
                raise SyntaxError("Missing ')'")
        tokens.pop(0)
        return expr
    elif token == ')':
        raise SyntaxError("Unexpected ')'")
    else:
        return token

def parse_sexp(s):
    return parse(tokenize(s))

def substitute(expr, env):
    """
    Recursively replaces symbols in the expression using the environment `env`.
    """
    if isinstance(expr, list):
        return [substitute(e, env) for e in expr]
    elif isinstance(expr, str) and expr in env:
        return deepcopy(env[expr])
    else:
        return expr

def inline_let(expr, env=None):
    """
    Recursively inlines let-bound variables in the expression.
    """
    if env is None:
        env = {}

    if not isinstance(expr, list):
        return substitute(expr, env)

    if len(expr) == 0:
        return expr

    if expr[0] == "let":
        bindings = expr[1]
        body = expr[2]

        # Extend current environment with new bindings
        new_env = env.copy()
        for binding in bindings:
            var, value = binding
            inlined_value = inline_let(substitute(value, new_env), new_env)
            new_env[var] = inlined_value

        return inline_let(body, new_env)
    else:
        # For all other forms, just substitute and recurse
        substituted = substitute(expr, env)
        return [inline_let(e, env) for e in substituted]

def flatten_formula(expr):
    """
    Flattens all top-level 'and' expressions into individual clauses.
    """
    if isinstance(expr, list) and expr:
        head = expr[0]
        if head == "and":
            clauses = []
            for sub in expr[1:]:
                clauses.extend(flatten_formula(sub))
            return clauses
        else:
            return [expr]
    else:
        return [expr]

def count_clauses(expr):
    inlined = inline_let(expr)
    flattened = flatten_formula(inlined)
    # print(flattened)
    return len(flattened)

def count_by_z3(smt2_content):
    # with open(filename, 'r') as f:
    #     smt2_content = f.read()
    
    # Parse SMT2 content into a Z3 goal
    ctx = Context()
    solver = Solver(ctx=ctx)
    
    try:
        parsed = parse_smt2_string(smt2_content, ctx=ctx)
        solver.add(parsed)
    except Z3Exception as e:
        print("Error parsing SMT2 content:", e, file=sys.stderr)
        sys.exit(1)
    
    # Create a goal and add the assertions
    goal = Goal(ctx=ctx)
    for f in solver.assertions():
        goal.add(f)
    
    # Apply the 'tseitin-cnf' tactic to convert to CNF
    cnf_tactic = Tactic('tseitin-cnf', ctx=ctx)
    cnf_result = cnf_tactic(goal)
    
    # Write the CNF result to a file
    with open("tmp.cnf", "w") as cnf_file:
        for subgoal in cnf_result:
            cnf_file.write(str(subgoal) + "\n")
    
    # Count the number of lines in the CNF file
    with open("tmp.cnf", "r") as cnf_file:
        cnf_lines = cnf_file.readlines()
        cnf_clause_count = len(cnf_lines)
        
    # print(f"CNF conversion complete: {cnf_clause_count} clauses")
    return cnf_clause_count

def count_lines_byz3(file_path,smt_path=None):
    """
    Count the number of lines in a file using Z3, but with a timeout of 1 minute.
    If the counting takes more than 1 minute, stop and return -1.
    """
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Counting took more than 5 minute")
    
    # Set up the timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(300)  # 60 seconds = 1 minute
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        smt_content,msg = convert_to_smt(content,smt_path)
    except Exception as e:
        print(f"Error converting to SMT {file_path}: {e}")
        return -2,"Unknown"
    if smt_content is None:
        return -1,msg
    return count_by_z3(smt_content),"UNSAT"

def main():
    parser = argparse.ArgumentParser(description='Count interpolant lines using Z3')
    parser.add_argument('file', nargs='?', help='Input file path (default: stdin)')
    parser.add_argument('--save', action='store_true', help='Save results to ProofSizeMap/data/filename.json')
    parser.add_argument('--smt', type=str, help='Path to the SMT file to use for variable declarations')
    args = parser.parse_args()
    
    file_path = args.file
    smt_path = args.smt
    size, msg = count_lines_byz3(file_path, smt_path)
    
    if args.save:
        basename = os.path.basename(args.file)
        print(f"Saving to ProofSizeMap/data/{basename}.json")
        with open(f"ProofSizeMap/data/{basename}.json", "w") as f:
            json.dump({"size": size}, f)
    print(size)

def convert_to_smt(content,smt_path=None):
    """
    Convert interpolants to an SMT formula.
    
    Args:
        content (str): The input content containing interpolants
        
    Returns:
        str: A valid SMT2 formula
    """
    lines = content.strip().splitlines()
    if lines and lines[0].strip().lower() == "unsat":
        content = "\n".join(lines[1:])
    
    try:
        sexpr = parse_sexp(content)
    except SyntaxError as e:
        print("Error parsing S-expression, caution!:", e, file=sys.stderr)
        return None,"Unknown"
    
    if not (isinstance(sexpr, list) and sexpr and sexpr[0] == "interpolants"):
        print("Input does not start with (interpolants ...), maybe formula is SAT", file=sys.stderr)
        return None,"SAT"
    
    interpolants = sexpr[1:]
    
    # Extract all variable names from the interpolants
    variables = set()
    
    # Generate SMT2 formula
    smt2_content = []

    if smt_path is not None:
        with open(smt_path, "r") as f:
            original_smt = f.read()
        original_smt = original_smt.strip().splitlines()
        for line in original_smt:
            if line.startswith("(declare-const"):
                smt2_content.append(line)
            else:
                break
    else:
        def extract_vars(expr):
            if isinstance(expr, list):
                for term in expr:
                    if isinstance(term, str) and term.startswith("v"):
                        variables.add(term)
                # Recursively process all subexpressions
                for subexpr in expr:
                    extract_vars(subexpr)
        for interp in interpolants:
            extract_vars(interp)

        # Declare variables
        for var in sorted(variables):
            smt2_content.append(f"(declare-const {var} Bool)")
    
    smt2_content.append("")
    
    # Assert each interpolant
    for i, interp in enumerate(interpolants):
        smt2_content.append(f"(assert {sexp_to_string(interp)})")
    
    smt2_content.append("")
    smt2_content.append("(check-sat)")
    
    return "\n".join(smt2_content),"UNSAT"

def sexp_to_string(expr):
    """Convert an S-expression to a string representation."""
    if isinstance(expr, list):
        return "(" + " ".join(sexp_to_string(x) for x in expr) + ")"
    else:
        return str(expr)

if __name__ == "__main__":
    main()
# example input:
# unsat
# (interpolants
#  (and (not (= v200 1))
#      (or (not (= v7321 0)) (and (= v7321 0) (= v7321 1)))
#      (or (not (= v8231 0)) (and (= v8231 0) (= v8231 1)))
#      (not (= 0 v9764))
#      (not (= 0 v2008))
#      (not (= 1 v4786))
#      (not (= 1 v4552))
#      (not (= 1 v4900))
#      (not (= 1 v4665)))
#  (and (not (= v200 1))
#      (or (not (= v7321 0)) (and (= v7321 0) (= v7321 1)))
#      (or (not (= v21670 0)) (and (= v21670 0) (= v21670 1)))
#      (or (not (= v23212 0)) (and (= v23212 0) (= v23212 1)))
#      (not (= 1 v23224))
#      (not (= 1 v28682))
#      (or (not (= v15419 0)) (and (= v15419 0) (= v15419 1)))
#      (not (= 1 v18494)))
#  (and (not (= v200 1))
#      (or (not (= v35227 0)) (and (= v35227 0) (= v35227 1)))
#      (or (not (= v36769 0)) (and (= v36769 0) (= v36769 1)))
#      (or (not (= v28976 0)) (and (= v28976 0) (= v28976 1)))
#      (or (not (= v34315 0)) (and (= v34315 0) (= v34315 1))))
#  (and (not (= v200 1))
#      (not (= 1 v50338))
#      (or (not (= v50326 0)) (and (= v50326 0) (= v50326 1)))
#      (not (= 1 v55796))
#      (or (not (= v42533 0)) (and (= v42533 0) (= v42533 1)))
#      (or (not (= v48784 0)) (and (= v48784 0) (= v48784 1)))
#      (or (not (= v34315 0)) (and (= v34315 0) (= v34315 1))))
#  (and (not (= v200 1))
#      (or (not (= v63883 0)) (and (= v63883 0) (= v63883 1)))
#      (or (not (= v56090 0)) (and (= v56090 0) (= v56090 1)))
#      (or (not (= v62341 0)) (and (= v62341 0) (= v62341 1))))
#  (let ((a!1 (or (not (= v77440 0)) (and (= v77440 0) (= v77440 1)))))
# (let ((a!2 (and (= v77452 0)
#                 a!1
#                 (not (= v200 1))
#                 (not (= v82910 1))
#                 (or (not (= v69647 0)) (and (= v69647 0) (= v69647 1))))))
# (let ((a!3 (and (or (not (= v77452 0)) a!2) (= v77452 0))))
# (let ((a!4 (or (not (= v69647 1))
#                (and (not (= v69647 0)) (or a!3 (= v69647 0))))))
# (let ((a!5 (and (= v77452 0)
#                 a!1
#                 (or (not (= v77452 0)) a!2)
#                 (or a!3 (= v69647 0))
#                 a!4
#                 (not (= v200 1))
#                 (= v69647 1)
#                 (not (= v82910 1)))))
#   (and (or (not (= v77452 0)) a!5) (= 0 v77452)))))))
#  (let ((a!1 (or (not (= v83204 0)) (and (= v83204 0) (= v83204 1)))))
# (let ((a!2 (or (not (= v90997 1)) (and (not (= v90997 0)) (not (= v200 1)) a!1))))
# (let ((a!3 (or (not (= v90997 1))
#                (and (not (= v90997 0)) a!2 (= v90997 1) (not (= v200 1)) a!1))))
#   (and a!3 (= 1 v90997)))))
#  (let ((a!1 (or (not (= v96761 0)) (and (= v96761 0) (= v96761 1)))))
# (let ((a!2 (or (not (= v110024 0)) (and (= v110024 0) (not (= v200 1)) a!1))))
# (let ((a!3 (or (not (= v110024 0)) (and (= v110024 0) a!2 (not (= v200 1)) a!1))))
#   (and a!3 (= 0 v110024)))))
#  (let ((a!1 (or (not (= v110318 1)) (and (not (= v110318 0)) (not (= v200 1))))))
# (let ((a!2 (or (not (= v110318 1))
#                (and (not (= v110318 0)) a!1 (= v110318 1) (not (= v200 1))))))
#   (and a!2 (= 1 v110318))))
#  (let ((a!1 (and (or (not (= v123875 1)) (not (= v123875 0)))
#                 (= v123875 1)
#                 (or (not (= v129433 1)) (not (= v129433 0))))))
# (let ((a!2 (and (not (= v123875 0))
#                 (or (not (= v123875 1)) (not (= v123875 0)))
#                 (= v123875 1)
#                 (or (not (= v129433 1)) a!1 (not (= v129433 0))))))
#   (and (or (not (= v123875 1)) a!2) (= 1 v123875)))))

