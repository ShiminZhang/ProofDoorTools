from utils.process_cnf import CNF
from utils.paths import get_absorption_experiments_dir, get_wires_dir
from debug.logging import LOG, LOG_TAG
import subprocess
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
import os
import json

def check_single_literal(args):
    absorption_dir = get_absorption_experiments_dir()
    
    literal, rest_of_clause, formula, CNF_output_file = args
    # solver_binary = "./propagator"
    solver_binary = "./minisat_propagator"
    # Create a copy of the formula
    formula_copy = CNF()
    formula_copy.init_with_clauses(formula.get_clauses())
    for neg_literal in rest_of_clause:
        formula_copy.append_clause([neg_literal])
    # if len(rest_of_clause) > 0:
    #     formula_copy.append_clause(rest_of_clause)
    # Write to temporary file
    if not os.path.exists(f"{absorption_dir}/caches/"):
        os.makedirs(f"{absorption_dir}/caches/")
    CNF_output_file = f"{absorption_dir}/caches/{CNF_output_file}"
    stdout_save_file = f"{CNF_output_file}.stdout"
    formula_copy.to_dimacs(CNF_output_file)
    LOG(f"CNF_output_file: {CNF_output_file}")
    LOG(f"stdout_output_file: {stdout_save_file}")
    result = subprocess.run([solver_binary, CNF_output_file], capture_output=True, text=True)
    # Clean up
    # os.remove(temp_file)
    LOG_TAG("--------------------------------", "detailed")
    LOG_TAG(f"literal: {literal}", "detailed")
    LOG_TAG(f"rest_of_clause: {rest_of_clause}", "detailed")
    LOG_TAG(f"result.stdout: {result.stdout}", "detailed")
    with open(stdout_save_file, 'w') as f:
        f.write(result.stdout)
    lines = result.stdout.split('\n')
    
    if "UNSATISFIABLE" in result.stdout:
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

def check_clause_absorption(clause, cnf_path):
    LOG(f"{clause} {cnf_path}")
    # Create arguments for parallel processing
    formula = CNF.from_file(cnf_path)
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    hash_value = hashing(clause)
    args_list = [(literal, [-l for l in clause if l != literal], formula, f"{basename}.check_absorb_{hash_value}_{literal}.cnf") for literal in clause]
    # Use number of CPU cores minus 1 to leave some resources for other processes
    num_processes = max(1, cpu_count() - 1)
    LOG_TAG(f"formed args_list: {args_list}", "detailed")
    # Create a pool of workers and map the work
    with Pool(processes=num_processes) as pool:
        results = pool.map(check_single_literal, args_list)
    # Return False if any of the checks failed
    LOG(f"results: {results}")
    return all(results)

def compute_wire_for_formula(formula: CNF,i):
    if i <= 0:
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
    shared_literals =set([l for l in B.literal_set if l in A.literal_set])
    shared_literals = sorted(list(shared_literals))
    return shared_literals

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

def compute_wire_and_save(formula: CNF,K=-1):
    print(f"compute_wire_and_save: {formula.cnf_path}")
    if K == -1:
        K = formula.K
    if K <= 0:
        print("K is less than 0")
        return
    for i in range(1,K):
        wires = compute_wire_for_formula(formula,i)
        basename = os.path.basename(formula.cnf_path)
        basename = basename.split(".")[0]
        output_file = os.path.join(get_wires_dir(K), f"{basename}.{K}.{i}.wires.json")
        res = {}        
        res["wire_size"] = len(wires)
        res["wires"] = wires
        with open(output_file, 'w') as f:
            json.dump(
                res,
                f,
                indent=4
            )
        
            
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