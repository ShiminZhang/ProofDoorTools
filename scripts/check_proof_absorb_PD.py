from utils.absorption_analysis import check_clause_absorption,check_formula_absorp_clause
from utils.process_cnf import CNF
from utils.tosmt import cnf_to_smt2_n_way
from utils.paths import get_cnfs_dir,get_interpolant_cnf_dir,get_interpolant_dir,get_smts_dir,get_interpolant_dimacs_dir,get_absorption_experiments_dir,get_figures_dir
from combine_proofdoor_to_cnf import combine_single_i_interpolant_to_cnf
import os
import json
from count_interpolant_byz3 import count_and_save
from debug.logging import LOG, LOG_TAG, REG_TAG, TOGGLE_SHOWLOG
from tqdm import tqdm
import matplotlib.pyplot as plt
import sys
import argparse

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
    
def check_proof_absorb_PD(cnf_path, k_value, index, use_cache=True):
    original_cnf = CNF.from_file(cnf_path)
    basename = os.path.basename(cnf_path)
    basename = basename.split(".")[0]
    # output_path = f"{get_absorption_experiments_dir()}/{basename}.{index}.check_absorb.json"
    output_path = f"{get_absorption_experiments_dir()}/{basename}.k_{k_value}.i_{index}.check_absorb.json"
    if os.path.exists(output_path) and use_cache:
        return json.load(open(output_path))
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
            literals_absorption = check_formula_absorp_clause(clauses[0:limit], clause, f"{basename}.k_{k_value}.{index}.check_absorb_{hash_value}.cnf")
            clause_absorption_map[j] = literals_absorption
        result[str(clause)] = clause_absorption_map
    with open(output_path, 'w') as outfile:
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
    draw_greyscale_plot(percentage_for_iterations,f'Clause Absorption Pass Percentage Heatmap {basename}_{k_value}')
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

def prepare_datas(names,k_value,force_refresh=False,index=None):
    solver = "./solvers/cadical"
    drat_solver = "./solvers/minisat_pf"
    # prepare proofs
    print(f"Preparing proofs for {names} with k_value {k_value},index {index}")
    for name in names:
        cnf_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cnf"
        if not os.path.exists(cnf_path):
            exit(f"CNF file {cnf_path} does not exist")
        proof_path = cnf_path.replace(".cnf",".drat")
        if not os.path.exists(proof_path):
            os.system(f"{solver} {cnf_path} {proof_path} --restart=0 --reduce=0 --restoreall=2 --flush=0 --no-binary")
        
            
    # prepare interpolants
    for name in names:
        for i in range(k_value):
            if index != None and i != index:
                continue
            cnf_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cnf"
            smt_path = f"{get_smts_dir(k_value)}/{name}.{k_value}.{i}.smt2"
            drat_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.drat"
            if not os.path.exists(drat_path) or os.path.getsize(drat_path) == 0:
                os.system(f"{drat_solver} {cnf_path} | grep 'PDLOG Learnt clause:' | sed 's/PDLOG Learnt clause: //' > {drat_path}")
            
            if not os.path.exists(smt_path):
                cnf_to_smt2_n_way(cnf_path,f"{get_smts_dir(k_value)}/{name}.{k_value}")
                
            interpolant_path = f"{get_interpolant_dir(k_value)}/{name}.{k_value}.{i}.interpolant"
            if not os.path.exists(interpolant_path):
                os.system(f"./z3 {smt_path} > {interpolant_path}")
                # exit(f"Interpolant file {interpolant_path} does not exist")
            interpolant_cnf_path = f"{get_interpolant_cnf_dir()}/{name}.{k_value}.{i}.smt2.cnf"
            
            if not os.path.exists(interpolant_cnf_path):
                print(f"Interpolant CNF file {interpolant_cnf_path} DNE, regenerating")
                count_and_save(interpolant_path,smt_path)
                
            dimacs_path = f"{get_interpolant_dimacs_dir()}/{name}.{k_value}.index_{i}.dimacs"
            if not os.path.exists(dimacs_path):
                print(f"Dimacs file {dimacs_path} DNE, regenerating")
                combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), k_value, i, name)
            elif force_refresh:
                print(f"Dimacs file {dimacs_path} exists, regenerating due to force_refresh")
                combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), k_value, i, name)
    
    if index != None:
        if force_refresh:
            for name in names:
                cnf_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cnf"
                print(f"Force refreshing proofs for {name} with k_value {k_value},index {index}")
                combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), k_value, index, name)
                
                drat_path = f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.drat"
                if not os.path.exists(drat_path) or os.path.getsize(drat_path) == 0:
                    os.system(f"{drat_solver} {cnf_path} | grep 'PDLOG Learnt clause:' | sed 's/PDLOG Learnt clause: //' > {drat_path}")
        return
            
    # for i in range(k_value):
    #     combine_single_i_interpolant_to_cnf(get_interpolant_cnf_dir(), k_value, i)

def check_and_draw_for_index(names,k_value,index):
    for name in names:
        check_proof_absorb_PD(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value,index,True)

def check_and_draw(names,k_value,force_refresh=False,index=None):
    if index != None:
        print(f"Checking absorption of {names[0]}.{k_value} for interpolant index {index}")
        check_and_draw_for_index(names,k_value,index)
        return
    for name in names:
        print(f"Checking absorption of {name}.{k_value}")
        for i in range(k_value):
            check_proof_absorb_PD(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value,i,not force_refresh)
        get_clause_pass_percentage_trend(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value)
        get_literal_pass_percentage_trend(f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cnf",k_value)

def main():
    # prepare_datas(["6s0","139442p0","139464p0","6s275rb318"],10)
    # check_and_draw(["6s0","139442p0","139464p0"],10)
    # (get_literal_pass_percentage_trend('./ProofDoorBenchmark/cnfs/10/6s0.10.cnf',10))
    # (get_clause_pass_percentage_trend('./ProofDoorBenchmark/cnfs/10/6s0.10.cnf',10))
    
    parser = argparse.ArgumentParser(description='Check and draw absorption experiments')
    parser.add_argument('--target_index', type=int, help='Index of the target instance')
    parser.add_argument('--target_name', type=str, help='Name of the target instance')
    parser.add_argument('--K', type=int, help='Name of the target instance', required=True)
    parser.add_argument('--index', type=int, help='check i_th interpolant', required=False)
    parser.add_argument('--force_refresh', action='store_true', help='Force refresh', required=False)
    parser.add_argument('--skip_prepare', action='store_true', help='Skip prepare', required=False)
    args = parser.parse_args()
    target_index = args.target_index
    target_name = args.target_name
    k_value = args.K
    force_refresh = args.force_refresh
    if target_index != None:
        targets=["6s0","6s4","6s273b37", "6s194"]
        if not args.skip_prepare:
            prepare_datas([targets[target_index]],k_value,force_refresh,args.index)
        check_and_draw([targets[target_index]],k_value,force_refresh,args.index)
    elif target_name:
        prepare_datas([target_name],k_value,force_refresh,args.index)
        check_and_draw([target_name],k_value,force_refresh,args.index)
    else:
        print("Please specify either --target_index or --target_name")
        return
    
    # check_and_draw(["6s0","139442p0","6s273b37", "139442p0"],10)
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