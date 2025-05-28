from utils.process_cnf import CNF
from utils.paths import get_absorption_experiments_dir, get_wires_dir
import subprocess
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
import os
import json

def check_single_literal(args):
    literal, rest_of_clause, formula, CNF_output_file = args
    solver_binary = "./propagator"
    # Create a copy of the formula
    formula_copy = CNF()
    formula_copy.init_with_clauses(formula.get_clauses())
    formula_copy.append_clause(rest_of_clause)
    # Write to temporary file
    CNF_output_file = formula_copy.to_dimacs(CNF_output_file)
    result = subprocess.run([solver_binary, CNF_output_file], capture_output=True, text=True)
    # Clean up
    # os.remove(temp_file)
    if "PDLOG" in result.stdout:
        line = result.stdout.split("PDLOG")[1]
        line = line.split("propagated to ")[1]
        line = line.split(" ")[0]
        propagated_literal = int(line)
        if literal != propagated_literal:
            return False
    return True

def check_clause_absorption(clause, formula: CNF, CNF_output_file="temp.cnf"):
    # Create arguments for parallel processing
    absorption_experiments_dir = get_absorption_experiments_dir()
    output_file = os.path.join(absorption_experiments_dir, f"{CNF_output_file}.txt")
    args_list = [(literal, [-l for l in clause if l != literal], formula, output_file) for literal in clause]
    # Use number of CPU cores minus 1 to leave some resources for other processes
    num_processes = max(1, cpu_count() - 1)
    
    # Create a pool of workers and map the work
    with Pool(processes=num_processes) as pool:
        results = pool.map(check_single_literal, args_list)
    print(results)
    # Return False if any of the checks failed
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
    # clause = [1,2]
    # print(check_clause_absorption(clause,formula))
    compute_wire_and_save(CNF.from_file("./test/6s4.4.cnf"))
    # formula = CNF.from_file("./test/6s4.4.cnf")
    # wires= compute_wire_for_formula(formula,2)
    # all_possible_clauses = construct_all_possible_clauses(wires)
    # for clause in all_possible_clauses:
    #     print(clause)
    pass

if __name__ == "__main__":
    main()