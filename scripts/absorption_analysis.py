from utils.process_cnf import CNF
import subprocess
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

def check_single_literal(args):
    literal, rest_of_clause, formula = args
    solver_binary = "cadical_propagate"
    appended_formula = formula.append_clause(rest_of_clause)
    result = subprocess.run([solver_binary, appended_formula], capture_output=True, text=True)
    if "PDLOG" in result.stdout:
        propagated_literal = int(result.stdout.split("PDLOG")[1].strip())
        if literal != propagated_literal:
            return False
    return True

def check_clause_absorption(clause, formula: CNF):
    # Create arguments for parallel processing
    args_list = [(literal, [l for l in clause if l != literal], formula) for literal in clause]
    
    # Use number of CPU cores minus 1 to leave some resources for other processes
    num_processes = max(1, cpu_count() - 1)
    
    # Create a pool of workers and map the work
    with Pool(processes=num_processes) as pool:
        results = pool.map(check_single_literal, args_list)
    print(results)
    # Return False if any of the checks failed
    return all(results)

def compute_wire_for_formula(formula: CNF,K):
    A = formula.get_A(K)
    B = formula.get_B(K)
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

def main():
    formula = CNF.from_file("./test/6s4.4.cnf")
    wires= compute_wire_for_formula(formula,2)
    all_possible_clauses = construct_all_possible_clauses(wires)
    for clause in all_possible_clauses:
        print(clause)
    pass

if __name__ == "__main__":
    main()