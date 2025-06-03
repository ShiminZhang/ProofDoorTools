from utils.absorption_analysis import check_clause_absorption,check_formula_absorp_clause
from utils.process_cnf import CNF
from utils.paths import get_cnfs_dir,get_interpolant_cnf_dir,get_interpolant_dir,get_smts_dir,get_interpolant_dimacs_dir,get_absorption_experiments_dir,get_figures_dir
from combine_proofdoor_to_cnf import combine_single_i_interpolant_to_cnf
import os
import json
from count_interpolant_byz3 import count_and_save
from debug.logging import LOG, LOG_TAG, REG_TAG, TOGGLE_SHOWLOG
from tqdm import tqdm
import matplotlib.pyplot as plt

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

def draw_greyscale_plot(percentage_trend, title, color='Greys'):
    plt.figure(figsize=(10, 6))
    plt.xticks(range(len(percentage_trend[0])), [f"{i*(100/len(percentage_trend))}%" for i in range(len(percentage_trend[0]))])
    plt.imshow(percentage_trend, cmap=color, aspect='auto')
    plt.colorbar(label='Pass Percentage')
    plt.xlabel('Proof progress percentage')
    plt.ylabel('Interpolant index')
    plt.title(title)
    plt.savefig(f"{get_figures_dir()}/{title}.png")

def pretty_print_percentage_trend(percentage_trend):
    for iteration in percentage_trend:
        formatted_percentages = [f"{p:.2f}" for p in iteration]
        print(formatted_percentages)

def get_clause_pass_percentage_trend(cnf_path, k_value):
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    percentage_for_iterations = []
    for index in range(k_value):
        percentage_for_interpolant_per_iteration = []
        result = json.load(open(f"{get_absorption_experiments_dir()}/{basename}.{index}.check_absorb.json"))
        for j in range(k_value):
            pass_count = 0
            total_count = 0
            for clause in result:
                if all(result[clause][str(j)]):
                    pass_count += 1
                total_count += 1
            percentage_for_interpolant_per_iteration.append(float(pass_count) / total_count)
        percentage_for_iterations.append(percentage_for_interpolant_per_iteration)
    draw_greyscale_plot(percentage_for_iterations,f'Clause Absorption Pass Percentage Heatmap {basename}')
    return percentage_for_iterations

def get_literal_pass_percentage_trend(cnf_path, k_value):
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    percentage_for_iterations = []
    for index in range(k_value):
        percentage_for_interpolant_per_iteration = []
        result = json.load(open(f"{get_absorption_experiments_dir()}/{basename}.{index}.check_absorb.json"))
        for j in range(k_value):
            pass_count = 0
            total_count = 0
            for clause in result:
                for literal in result[clause][str(j)]:
                    total_count += 1
                    if literal:
                        pass_count += 1
            percentage_for_interpolant_per_iteration.append(float(pass_count) / total_count)
        percentage_for_iterations.append(percentage_for_interpolant_per_iteration)
    draw_greyscale_plot(percentage_for_iterations,f'Literal Absorption Pass Percentage Heatmap {basename}',color='Blues')
    return percentage_for_iterations

def prepare_datas(names,k_value):
    # prepare proofs
    # solver = "./solvers/wsl_cadical"
    # for name in names:
    #     cnf_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cnf"
    #     proof_path = cnf_path.replace(".cnf",".drat")
    #     if not os.path.exists(proof_path):
    #         os.system(f"{solver} {cnf_path} {proof_path} --restart=0 --reduce=0 --restoreall=2 --flush=0 --no-binary")
            
    # prepare interpolants
    for name in names:
        for i in range(k_value):
            interpolant_path = f"{get_interpolant_dir(k_value)}/{name}.{k_value}.{i}.interpolant"
            smt_path = f"{get_smts_dir(k_value)}/{name}.{k_value}.{i}.smt2"
            count_and_save(interpolant_path,smt_path)

    for i in range(k_value):
        combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), k_value, i)

def check_and_draw(names,k_value):
    for name in names:
        for i in range(k_value):
            check_proof_absorb_PD(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value,i)
        get_clause_pass_percentage_trend(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value)
        get_literal_pass_percentage_trend(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value)

def main():
    # prepare_datas(["6s0","139442p0","6s273b37", "139442p0"],10)
    check_and_draw(["6s0","139442p0","6s273b37", "139442p0"],10)
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
    # print(f"index 0: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,0).values())}")
    # print(f"index 1: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,1).values())}")
    # print(f"index 2: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,2).values())}")
    # print(f"index 3: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,3).values())}")
    # print(f"index 4: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,4).values())}")
    # print(f"index 5: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,5).values())}")
    # print(f"index 6: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,6).values())}")
    # print(f"index 7: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,7).values())}")
    # print(f"index 8: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,8).values())}")
    # print(f"index 9: {check_pass_percent(check_proof_absorb_PD('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10,9).values())}")
    # (get_literal_pass_percentage_trend('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10))
    # (get_clause_pass_percentage_trend('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10))
    # (get_literal_pass_percentage_trend('./ProofDoorBenchmark/cnfs/10/6s4.10.cnf',10))
    # compute_wire_and_save(CNF.from_file("./test/6s4.4.cnf"))
    # formula = CNF.from_file("./test/6s4.4.cnf")
    # wires= compute_wire_for_formula(formula,2)
    # all_possible_clauses = construct_all_possible_clauses(wires)
    # for clause in all_possible_clauses:
    #     print(clause)
    pass

if __name__ == "__main__":
    main()