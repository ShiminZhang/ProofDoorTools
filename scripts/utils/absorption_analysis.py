from utils.process_cnf import CNF
from utils.paths import get_absorption_experiments_dir, get_wires_dir
from debug.logging import LOG, LOG_TAG
import subprocess
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
import logging
import os
import json

def check_negclause_conflict(args):
    clause, formula, CNF_output_file, K = args
    absorption_dir = get_absorption_experiments_dir(K)
    solver_binary = "./propagator"
    formula_copy = CNF()
    formula_copy.init_with_clauses(formula)
    for neg_literal in clause:
        formula_copy.append_clause([neg_literal])
    # if len(rest_of_clause) > 0:
    #     formula_copy.append_clause(rest_of_clause)
    # Write to temporary file
    cache_dir = os.path.join(absorption_dir, "caches")
    os.makedirs(cache_dir, exist_ok=True)
    CNF_output_file = os.path.join(cache_dir, CNF_output_file)
    # stdout_save_file = f"{CNF_output_file}.stdout"
    formula_copy.to_dimacs(CNF_output_file)
    # print(f"CNF_output_file: {CNF_output_file}")
    # LOG(f"stdout_output_file: {stdout_save_file}")
    checker_stdout = ""
    # if os.path.exists(stdout_save_file):
    #     checker_stdout = open(stdout_save_file, 'r').read()
    # else:
    result = subprocess.run([solver_binary, "-no-pre", CNF_output_file], capture_output=True)
    try:
        checker_stdout = result.stdout.decode('utf-8')
    except UnicodeDecodeError:
        checker_stdout = result.stdout.decode('gbk', errors="replace")
    # Clean up
    if os.path.exists(CNF_output_file):
        os.remove(CNF_output_file)
    # with open(CNF_output_file, 'w') as f:
    #     f.write(checker_stdout)
    # print(f"checker_stdout: {CNF_output_file}")
    lines = checker_stdout.split('\n')
    if "UNSATISFIABLE" in checker_stdout:
        LOG("True because unsat")
        return True
    
    for line in lines:
        if "PDLOG propagated to" in line:
            
            # return False
            continue
        if "PDLOG decision" in line:
            return False
        if "PDLOG conflict" in line:
            return True
        if "UNSATISFIABLE" in line:
            return True
    return False
    


def check_single_literal(args):
    literal, rest_of_clause, formula, CNF_output_file, K = args
    absorption_dir = get_absorption_experiments_dir(K)
    # print(f"CNF_output_file: {CNF_output_file} for literal: {literal}")
    # solver_binary = "./propagator"
    solver_binary = "./propagator"
    # Create a copy of the formula
    formula_copy = CNF()
    formula_copy.init_with_clauses(formula)
    for neg_literal in rest_of_clause:
        formula_copy.append_clause([neg_literal])
    # if len(rest_of_clause) > 0:
    #     formula_copy.append_clause(rest_of_clause)
    # Write to temporary file
    cache_dir = os.path.join(absorption_dir, "caches")
    os.makedirs(cache_dir, exist_ok=True)
    CNF_output_file = os.path.join(cache_dir, CNF_output_file)
    # stdout_save_file = f"{CNF_output_file}.stdout"
    formula_copy.to_dimacs(CNF_output_file)
    LOG(f"CNF_output_file: {CNF_output_file}")
    # LOG(f"stdout_output_file: {stdout_save_file}")
    checker_stdout = ""
    # if os.path.exists(stdout_save_file):
    #     checker_stdout = open(stdout_save_file, 'r').read()
    # else:
    result = subprocess.run([solver_binary, "-no-pre", CNF_output_file], capture_output=True)
    try:
        checker_stdout = result.stdout.decode('utf-8')
    except UnicodeDecodeError:
        checker_stdout = result.stdout.decode('gbk', errors="replace")
    # Clean up
    if os.path.exists(CNF_output_file):
        os.remove(CNF_output_file)
    # with open(CNF_output_file, 'w') as f:
    #     f.write(checker_stdout)
    # print(f"checker_stdout: {CNF_output_file}")
    # os.remove(temp_file)
    LOG_TAG("--------------------------------", "detailed")
    LOG_TAG(f"literal: {literal}", "detailed")
    LOG_TAG(f"rest_of_clause: {rest_of_clause}", "detailed")
    LOG_TAG(f"checker_stdout: {checker_stdout}", "detailed")
    # with open(stdout_save_file, 'w') as f:
    #     f.write(checker_stdout)
    lines = checker_stdout.split('\n')
    
    if "UNSATISFIABLE" in checker_stdout:
        LOG("True because unsat")
        return True
    
    for line in lines:
        if "PDLOG propagated to" in line:
            line = line.split("PDLOG")[1]
            line = line.split("propagated to ")[1]
            line = line.split(" ")[0]
            propagated_literal = int(line)
            if abs(literal) == abs(propagated_literal):
                if literal * propagated_literal > 0:
                    return True
                else:
                    LOG(f"{literal} false because assigned reversely")
                    return False
        elif "PDLOG decision" in line:
            LOG(f"{literal} false because not implied")
            return False
        elif "PDLOG conflict" in line:
            LOG(f"{literal} true because conflict")
            return True
        elif "UNSATISFIABLE" in line:
            LOG(f"{literal} true because unsat")
            return True
    return False

def hashing(clause):
    return hash(tuple(clause))

def check_formula_absorp_clause(formula, clause, cachename, K):
    args_list = [(literal, [-l for l in clause if l != literal], formula, f"{cachename}_{literal}.cnf", K) for literal in clause]
    # Use number of CPU cores minus 1 to leave some resources for other processes
    num_processes = min(max(1, cpu_count() - 1), 8)
    # print(f"num_processes: {num_processes}")
    LOG_TAG(f"formed args_list: {args_list}", "detailed")
    # Create a pool of workers and map the work
    with Pool(processes=num_processes) as pool:
        results = pool.map(check_single_literal, args_list)
    # Return False if any of the checks failed
    LOG(f"results: {results}")
    return results

def check_formula_absorp_clause_accelerated(formula, clause, cachename, K):
    hash_value = hashing(clause)
    args_list = ([-l for l in clause], formula, f"{cachename}_{hash_value}.cnf", K)
    results = check_negclause_conflict(args_list)
    results_literal_level = []
    for literal in clause:
        results_literal_level.append(results)
    return results_literal_level

def check_clause_absorption(clause, cnf_path, K):
    LOG(f"{clause} {cnf_path}")
    # Create arguments for parallel processing
    formula = CNF.from_file(cnf_path)
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    hash_value = hashing(clause)
    return check_formula_absorp_clause(formula, clause, f"{basename}.check_absorb_{hash_value}", K)
    # args_list = [(literal, [-l for l in clause if l != literal], formula, f"{basename}.check_absorb_{hash_value}_{literal}.cnf") for literal in clause]
    # # Use number of CPU cores minus 1 to leave some resources for other processes
    # num_processes = max(1, cpu_count() - 1)
    # LOG_TAG(f"formed args_list: {args_list}", "detailed")
    # # Create a pool of workers and map the work
    # with Pool(processes=num_processes) as pool:
    #     results = pool.map(check_single_literal, args_list)
    # # Return False if any of the checks failed
    # LOG(f"results: {results}")
    # return all(results)

def compute_wire_for_formula(formula: CNF,i):
    if i < 0:
        print("compute_wire_for_formula: i is less than 0")
        return
    A = formula.get_A(i)
    B = formula.get_B(i)
    # print(A.dump_stats())
    # print(B.dump_stats())
    # print("--------------------------------")
    return compute_wire(A,B)

def compute_wire(A,B):
    # A and B are two cnf formulas 
    # Wires should be shared *variables* (by id), not signed literals.
    # `A.literal_set` / `B.literal_set` may contain signed literals depending on how
    # the CNF object was constructed, so normalize via abs().
    A_vars = {abs(l) for l in A.literal_set}
    B_vars = {abs(l) for l in B.literal_set}
    shared_vars = sorted(A_vars & B_vars)
    return shared_vars

def construct_all_possible_clauses(literals):
    clauses = []
    n = len(literals)
    
    # Generate all possible combinations of literals
    for i in tqdm(range(1, 2**n)):
        # Convert number to binary and pad with zeros
        binary = format(i, f'0{n}b')
        
        # Create clause using literals where binary digit is 1
        clause = [literals[j] for j in range(n) if binary[j] == '1']
        clauses.append(clause)
    return clauses

def compute_wire_and_save(formula: CNF, K: int = -1, force_refresh: bool = False):
    logger = logging.getLogger("proofdoor.worker")
    logger.info("compute_wire_and_save: %s", formula.cnf_path)
    if K == -1:
        K = formula.K
    if K <= 0:
        logger.error("K is less than 0")
        return
    wire_size_map = {}
    for i in range(0,K):
        basename = os.path.basename(formula.cnf_path)
        basename = basename.split(".")[0]
        output_file = os.path.join(get_wires_dir(K), f"{basename}.{K}.{i}.wires.json")
        if (not force_refresh) and os.path.exists(output_file):
            logger.info("wires: %s already exists", output_file)
            res = json.load(open(output_file, 'r'))
            wire_size_map[i] = res["wire_size"]
            continue
        wires = compute_wire_for_formula(formula,i)
        res = {}        
        res["wire_size"] = len(wires)
        res["wires"] = wires
        with open(output_file, 'w') as f:
            json.dump(
                res,
                f,
                indent=4
            )
        wire_size_map[i] = res["wire_size"]
    return wire_size_map

def main():
    # formula = CNF.from_file("./test/test.cnf")
    # clause = [-1,2]
    # print([3,4])
    # print(clause)
    # formula = CNF.from_file("./test/test.cnf")
    # print(check_clause_absorption(clause,formula))
    pass

if __name__ == "__main__":
    main()