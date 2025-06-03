from utils.absorption_analysis import check_clause_absorption,check_formula_absorp_clause
from utils.process_cnf import CNF
from utils.paths import get_interpolant_cnf_dir,get_interpolant_dimacs_dir,get_absorption_experiments_dir
from combine_proofdoor_to_cnf import combine_single_i_interpolant_to_cnf
import os
import json
from debug.logging import LOG, LOG_TAG, REG_TAG, TOGGLE_SHOWLOG
from tqdm import tqdm

def test1():
    cnf_path = "./test/test.cnf"
    assert(check_clause_absorption([3,4],cnf_path) == True)
    assert(check_clause_absorption([-1],cnf_path) == True)
    assert(check_clause_absorption([5,6],cnf_path) == False)
    assert(check_clause_absorption([1,-2],cnf_path) == False)
    assert(check_clause_absorption([2,1],cnf_path) == True)
    
def test2():
    cnf_path = "./test/test2.cnf"
    assert(check_clause_absorption([-1,3],cnf_path) == True)
    assert(check_clause_absorption([1,7],cnf_path) == False)
    assert(check_clause_absorption([6,9],cnf_path) == False)
    assert(check_clause_absorption([3,4],cnf_path) == True)
    assert(check_clause_absorption([-1,4],cnf_path) == True)
    
def test3():
    cnf_path = "./test/test3.cnf"
    assert(check_clause_absorption([2,3,4,5],cnf_path) == True)
    assert(check_clause_absorption([1,2,3,7],cnf_path) == True)
    assert(check_clause_absorption([-1,-2,-3],cnf_path) == False)
    assert(check_clause_absorption([1,2,4],cnf_path) == True)
    assert(check_clause_absorption([1,6,10],cnf_path) == False)
    assert(check_clause_absorption([1,2,-3,5,-10],cnf_path) == True)
    
def check_proof_absorb_PD(cnf_path, k_value, index):
    original_cnf = CNF.from_file(cnf_path)
    proof_path = cnf_path.replace(".cnf",".drat")
    clauses = []
    with open(proof_path, "r") as file:
        lines = file.readlines()
        for line in lines:
            if line.startswith("d "):
                continue
            elif line.startswith("0"):
                continue
            else:
                clauses.append([int(literal) for literal in line.strip().split(" ") if literal != "" and literal != "0"])
    # LOG(f"clauses: {clauses}")
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    interpolant_dir = get_interpolant_dimacs_dir()
    interpolant_cnf_path = f"{interpolant_dir}/{basename}.{k_value}.index_{index}.dimacs"
    interpolant_cnf = CNF.from_file(interpolant_cnf_path)
    result = {}
    for clause in tqdm(interpolant_cnf.clauses):
        clause_absorption_map = {}
        hash_value = hash(tuple(clause))
        LOG(f"clause to check: {clause}")
        for j in range(k_value):
            limit = min(int((j+1) / k_value * len(clauses)),len(clauses))
            literals_absorption = check_formula_absorp_clause(clauses[0:limit], clause, f"{basename}.{index}.check_absorb_{hash_value}.cnf")
            clause_absorption_map[j] = literals_absorption
        result[str(clause)] = clause_absorption_map
    with open(f"{get_absorption_experiments_dir()}/{basename}.{index}.check_absorb.json", 'w') as outfile:
        json.dump(result,outfile, indent=4)
    return result

def check_pass_percent(in_list):
    # print(in_list)
    pass_count = 0
    for item in in_list:
        if item:
            pass_count += 1
    return float(pass_count) / len(in_list)

def main():
    # debug.logging.ToggleShowlog(True)
    # formula = CNF.from_file("./test/test.cnf")
    # formula = CNF.from_file("./test/test.cnf")
    # TOGGLE_SHOWLOG(True)
    # REG_TAG("detailed")
    # test3()
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 0)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 1)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 2)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 3)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 4)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 5)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 6)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 7)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 8)
    # combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), 10, 9)
    print(f"index 0: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,0).values())}")
    print(f"index 1: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,1).values())}")
    print(f"index 2: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,2).values())}")
    print(f"index 3: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,3).values())}")
    print(f"index 4: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,4).values())}")
    print(f"index 5: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,5).values())}")
    print(f"index 6: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,6).values())}")
    print(f"index 7: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,7).values())}")
    print(f"index 8: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,8).values())}")
    print(f"index 9: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,9).values())}")
    # compute_wire_and_save(CNF.from_file("./test/6s4.4.cnf"))
    # formula = CNF.from_file("./test/6s4.4.cnf")
    # wires= compute_wire_for_formula(formula,2)
    # all_possible_clauses = construct_all_possible_clauses(wires)
    # for clause in all_possible_clauses:
    #     print(clause)
    pass

if __name__ == "__main__":
    main()