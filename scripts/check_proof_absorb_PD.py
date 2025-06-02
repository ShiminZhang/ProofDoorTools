from utils.absorption_analysis import check_clause_absorption
from utils.process_cnf import CNF
from utils.paths import get_interpolant_dir
import os
from debug.logging import LOG, LOG_TAG, REG_TAG

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
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    interpolant_dir = get_interpolant_dir()
    interpolant_cnf_path = f"{interpolant_dir}/{basename}.{k_value}.{index}.smt2.cnf"
    interpolant_cnf = CNF.from_file(interpolant_cnf_path)
    result = {}
    for clause in interpolant_cnf.clauses:
        result[clause] = check_clause_absorption(clause, cnf_path)
    return result

def main():
    # debug.logging.ToggleShowlog(True)
    # formula = CNF.from_file("./test/test.cnf")
    # formula = CNF.from_file("./test/test.cnf")
    # REG_TAG("detailed")
    test3()
    
    # compute_wire_and_save(CNF.from_file("./test/6s4.4.cnf"))
    # formula = CNF.from_file("./test/6s4.4.cnf")
    # wires= compute_wire_for_formula(formula,2)
    # all_possible_clauses = construct_all_possible_clauses(wires)
    # for clause in all_possible_clauses:
    #     print(clause)
    pass

if __name__ == "__main__":
    main()