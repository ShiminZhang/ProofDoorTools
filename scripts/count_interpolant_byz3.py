#!/usr/bin/env python3
import sys
import re
from copy import deepcopy
from z3 import *
from z3 import Context
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.catagory import get_instance_list
from utils.paths import get_PDS_dir, get_interpolant_cnf_dir, get_interpolant_dir, get_cnfs_dir
import signal
import subprocess
import argparse
import json
import os
from tqdm import tqdm
from utils.utils import parse_sexp


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

def count_by_z3(smt2_content,smt_path=None,pddef=0):
    # with open(filename, 'r') as f:
    #     smt2_content = f.read()
    
    # Parse SMT2 content into a Z3 goal
    ctx = Context()
    solver = Solver(ctx=ctx)
    basename = os.path.basename(smt_path)
    k_value = basename.split(".")[1]
    cnf_dir = get_interpolant_cnf_dir(k_value,pddef)
    cnf_path = f"{cnf_dir}/{basename}.cnf"
    if os.path.exists(cnf_path) and os.path.getsize(cnf_path) > 0 and False:
        with open(cnf_path, "r") as cnf_file:
            cnf_lines = cnf_file.readlines()
            count = 0
            for line in cnf_lines:
                if not line.startswith("  "):
                    count += 1
            cnf_clause_count = count
            return cnf_clause_count
        
    try:
        parsed = parse_smt2_string(smt2_content, ctx=ctx)
        solver.add(parsed)
    except Z3Exception as e:
        print("Error parsing SMT2 content:", e, file=sys.stderr)
        sys.exit(1)
    
    # Create a goal and add the assertions
    goal = Goal(ctx=ctx)
    for f in solver.assertions():
        # print(f)
        goal.add(f)
    # Apply the 'tseitin-cnf' tactic to convert to CNF
    cnf_tactic = Tactic('tseitin-cnf', ctx=ctx)
    tactics_to_use = cnf_tactic
    cnf_result = tactics_to_use(goal)
    basename = os.path.basename(smt_path)
    # Write the CNF result to a file
    with open(cnf_path, "w") as cnf_file:
        for subgoal in cnf_result:
            for clause in subgoal:
                newline = " ".join(line.strip() for line in clause.sexpr().splitlines())
                cnf_file.write(newline + "\n")
    print(f"CNF conversion complete: {cnf_path}")
    # Count the number of lines in the CNF file
    with open(cnf_path, "r") as cnf_file:
        cnf_lines = cnf_file.readlines()
        cnf_clause_count = len(cnf_lines)
        
    # print(f"CNF conversion complete: {cnf_clause_count} clauses")
    return cnf_clause_count

def count_lines_byz3(file_path,smt_path=None, timeout=300,pddef=0):
    """
    Count the number of lines in a file using Z3, but with a timeout of 1 minute.
    If the counting takes more than 1 minute, stop and return -1.
    """
    
    def timeout_handler(signum, frame):
        raise TimeoutError("Counting took more than 5 minute")
    
    # Set up the timeout
    if timeout > 0:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
    # Set up keyboard interrupt handler to stop converting when Ctrl+C is pressed
    # (We use Ctrl+C as a proxy for Ctrl+Shift+X since direct detection is not possible)
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    
    def sigint_handler(signum, frame):
        raise TimeoutError("User interrupted")
    
    # Set our custom interrupt handler
    signal.signal(signal.SIGINT, sigint_handler)
    try:
        # Print timestamp before starting the counting process
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"[{current_time}] Starting to count lines for {file_path}")
        with open(file_path, 'r') as f:
            content = f.read()
        
        smt_content,msg = convert_to_smt(content,smt_path)
        if msg == "CNF":
            return smt_content,"UNSAT" #TODO fix, the smt_content here is actually a size of cnf
    except Exception as e:
        print(f"Error converting to SMT {file_path}: {e}")
        return -2,"Unknown"
    if smt_content is None:
        return -1,msg
    return count_by_z3(smt_content,smt_path,pddef=pddef),"UNSAT"
    

def count_resolution_steps(name, K, index, force_refresh=False):
    interpolant_dir = get_interpolant_dir(K,3)
    interpolant_path = f"{interpolant_dir}/{name}.{K}.{index}.interpolant"
    # read proof
    output_dir = f"ProofSizeMap/resolution_steps/{K}/"
    os.makedirs(output_dir,exist_ok=True)
    output_path = f"{output_dir}/{name}.{K}.{index}.json"
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0 and not force_refresh:
        result = json.load(open(output_path, "r"))
        return result

    cnf_path = get_cnfs_dir(K)
    cnf_path = f"{cnf_path}/{name}.{K}.cnf"
    lrat_path = cnf_path.replace(".cnf",".lrat")

    if not os.path.exists(lrat_path):
        solver = "./solvers/cadical"
        os.system(f"{solver} {cnf_path} {lrat_path} --no-binary --plain --lrat")
    
    print(f"checking {interpolant_path}")
    # read interpolants to get clause set
    with open(interpolant_path, "r") as f:
        interpolants = f.read()
    interpolants = interpolants.strip().splitlines()
    clause_set = set()
    for interpolant in interpolants:
        clause_set.add(tuple(int(x) for x in interpolant.split()))
    
    # calculate resolution steps
    result = calculate_clauses_resolution_steps(clause_set, lrat_path, force_refresh)
    with open(output_path, "w") as f:
        json.dump(result, f)

    return result


def calculate_clauses_resolution_steps(clause_set, lrat_file_path, force_refresh=False):
    """
    Calculate the sum of resolution steps for a specific set of clauses.
    
    Args:
        clause_set: A set of clause literals (tuples of integers)
        lrat_file_path: Path to the LRAT proof file
    
    Returns:
        dict: {
            'total_steps': int,
            'found_clauses': int,
            'missing_clauses': int,
            'clause_details': list of (literals, steps, found)
        }
    """
    print(f"Calculating resolution steps for {len(clause_set)} clauses from {lrat_file_path}")
    # remove 0 from clause_set
    # clause_set = set(filter(lambda x: x != (0,), clause_set))
    # Parse LRAT file
    clauses = {}  # clause_id -> literals
    proof_chains = {}  # clause_id -> proof_chain
    deletions = set()
    
    with open(lrat_file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('d '):  # deletion
                parts = line.split()
                if len(parts) >= 2 and parts[-1] == '0':
                    literals = tuple(int(x) for x in parts[1:-1])
                    deletions.add(literals)
            else:  # addition with proof chain
                parts = line.split()
                if len(parts) >= 3:
                    zero_pos = -1
                    for i, part in enumerate(parts):
                        if part == '0':
                            zero_pos = i
                            break
                    
                    if zero_pos != -1 and zero_pos >= 2:
                        try:
                            clause_id = int(parts[0])
                            literals = tuple(int(x) for x in parts[1:zero_pos])
                            proof_chain = [int(x) for x in parts[zero_pos+1:]]
                            
                            clauses[clause_id] = literals
                            proof_chains[clause_id] = proof_chain
                        except ValueError:
                            continue
    
    # Calculate resolution steps for each clause in the set
    total_steps = 0
    found_clauses = 0
    missing_clauses = 0
    clause_details = []
    
    for target_literals in clause_set:
        target_literals = tuple(filter(lambda x: x != 0, target_literals))
        # Find the clause in the parsed data
        found = False
        resolution_steps = 0
        
        for clause_id, literals in clauses.items():
            if literals == target_literals:
                found = True
                found_clauses += 1
                
                # Calculate exact resolution steps from proof chain
                proof_chain = proof_chains.get(clause_id, [])
                if len(proof_chain) <= 1:
                    resolution_steps = 0
                else:
                    resolution_steps = len(proof_chain) - 1
                
                total_steps += resolution_steps
                break
        
        if not found:
            print(f"Clause {target_literals} not found in {lrat_file_path}")
        
        clause_details.append((target_literals, resolution_steps, found))
    
    result = {
        'total_steps': total_steps,
        'found_clauses': found_clauses,
        'missing_clauses': missing_clauses,
        'clause_details': clause_details
    }
    
    return result

def to_smt_cnf(file_path,smt_path=None):
        with open(file_path, 'r') as f:
            content = f.read()
        smt_content,msg = convert_to_smt(content,smt_path)
        
def count_and_save(file_path,smt_path=None,limit=300,pddef=0):
    if pddef == 3:
        interpolant_path = file_path
        size = os.path.getsize(interpolant_path)
        # INSERT_YOUR_CODE
        # For interpolant_def3, just count the number of non-empty lines (each line is a clause)
        with open(interpolant_path, "r") as f:
            lines = f.readlines()
            n_lines = 0
            n_clauses = 0
            for line in lines:
                if line.startswith("c") or line.strip() == "" or line.startswith("p"):
                    continue
                n_lines += 1
                split_line = line.strip().split(" ")
                n_clauses += len(split_line) - 1

        msg = "Unknown"
        k_value = os.path.basename(file_path).split(".")[1]
        basename = os.path.basename(file_path)
        dir = get_PDS_dir(k_value,pddef)
        print(f"Saving to {dir}/{basename}.json")
        result = {}
        result["n_lines"] = n_lines
        result["n_clauses"] = n_clauses
        result["size"] = size
        result["msg"] = msg
        with open(f"{dir}/{basename}.json", "w") as f:
            json.dump(result, f)
    else:
        size, msg = count_lines_byz3(file_path, smt_path, limit,pddef)
        k_value = os.path.basename(file_path).split(".")[1]
        basename = os.path.basename(file_path)
        dir = get_PDS_dir(k_value,pddef)
        print(f"Saving to {dir}/{basename}.json")
        with open(f"{dir}/{basename}.json", "w") as f:
            json.dump({f"{basename}": (size,msg)}, f)
    print(size)
    return size,msg

def test_count_resolution_steps():
    instance_list = get_instance_list("all")
    K = 10
    def run_count_resolution_steps(name, K, index):
        print(f"checking {name}.{K}.{index}————————————————————————————————————————————————————————————————")
        result = count_resolution_steps(name, K, index)
        print(result["total_steps"])
        save_dir = f"ProofSizeMap/resolution_steps/{K}/"
        os.makedirs(save_dir,exist_ok=True)
        with open(f"{save_dir}/{name}.{K}.{index}.json", "w") as f:
            json.dump(result, f)
        return result

    for instance in instance_list:
        name = instance
        # for index in range(K):
            # INSERT_YOUR_CODE
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(run_count_resolution_steps, name, K, index) for index in range(K)]
            for future in as_completed(futures):
                # Optionally, you can process results here if needed
                _ = future.result()
            # print(f"checking {name}.{K}.{index}————————————————————————————————————————————————————————————————")
            # result = count_resolution_steps(name, K, index)
            # print(result["total_steps"])
    # name = "6s0"
    # index = 0
    # print(result)

def main():
    parser = argparse.ArgumentParser(description='Count interpolant lines using Z3')
    parser.add_argument('--file', nargs='?', help='Input file path (default: stdin)')
    parser.add_argument('--save', action='store_true', help='Save results to ProofSizeMap/data/filename.json')
    parser.add_argument('--smt', type=str, help='Path to the SMT file to use for variable declarations')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout in seconds (default: 300)')
    parser.add_argument('--pddef', type=int, default=0, help='PDDef (default: 0)')
    args = parser.parse_args()
    
    # file_path = args.file
    # smt_path = args.smt
    # calculate_clauses_resolution_steps([(3897,0)], "test.lrat")
    test_count_resolution_steps()
    # count_and_save(file_path, smt_path, args.timeout, args.pddef)

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
        print("try read as pure cnf")
        print(sexpr)
        if int(sexpr):
            return None, "CNF"
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