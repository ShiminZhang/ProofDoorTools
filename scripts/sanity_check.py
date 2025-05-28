# import z3
from utils.utils import read_smt2_file, read_interpolant, to_pure_smt2, parse_interpolant_cnf_to_dimacs
from utils.absorption_analysis import CNF
from z3 import *
from utils.catagory import get_instance_list
import os
import json
from tqdm import tqdm

def read_interpolant_cnf(file_path,definitions):
    # read as SMT-LIB format, use z3 to parse
    with open(file_path, "r") as f:
        lines = f.readlines()
    content = ""
    for definition in definitions:
        content += f"{definition}\n"
    non_def_content = "(assert (and\n"
    for line in lines:
        line = line.replace("Not", "not")
        split_line = line.strip().split(" ")
        constructed_line = "(or"
        for chunk in split_line:
            if "not" in chunk:
                chunk = chunk.replace("not", "")
                chunk = chunk.replace("(", "")
                chunk = chunk.replace(")", "")
                chunk = chunk.replace("[", "")
                chunk = chunk.replace("]", "")
                constructed_line += f" (not {chunk}) "
            else:
                constructed_line += f" {chunk} "
        constructed_line+= ")"
        non_def_content += constructed_line + "\n"
    non_def_content += "))  "
    # print(non_def_content)
    content += non_def_content
    # print(content)
    formula = parse_smt2_string(content)
    # print(formula)
    # z3expression = Z3_ast_to_smtlib(formula)
    return formula[0]

def read_interpolant_and_get_smt_lib_format(file_path,definitions):
    interpolant = read_interpolant(file_path, definitions)
    return interpolant

def check_equivalence(interpolant_cnf, interpolant_smt, original_smt):
    # print("checking equivalence of :")
    # print(f"interpolant cnf: {interpolant_cnf}")
    # print(f"interpolant smt: {interpolant_smt}")
    # print(f"original smt: {original_smt}")
    smt_content = to_pure_smt2(original_smt)
    # save the interpolant smt content to a file
    base_name = os.path.basename(original_smt)
    k_value = base_name.split(".")[1]
    # print(f"k value: {k_value}")
    path = os.path.dirname("ProofDoorBenchmark/sanity_smts/")
    os.makedirs(path, exist_ok=True)
    
    pure_smt_file = os.path.join(path,f"{base_name}.sanity")
    if not os.path.exists(pure_smt_file):
        with open(pure_smt_file, "w") as f:
            f.write(smt_content)

    _,_,definitions = read_smt2_file(pure_smt_file)
    # print("reading definitions done")
    # read interpolant cnf
    interpolant_as_cnf = read_interpolant_cnf(interpolant_cnf,definitions)
    # print("reading interpolant cnf done")

    interpolant_as_smt = read_interpolant_and_get_smt_lib_format(interpolant_smt,definitions)
    # print("reading interpolant smt done")
    # check equivalence
    # print(interpolant_as_cnf)
    # print("--------------------------------")
    # print(interpolant_as_smt)
    s = Solver()
    s.add(Not(interpolant_as_cnf == interpolant_as_smt))
    result = s.check()
    if result == z3.unsat:
        # print("The interpolants are equivalent")
        return True
    else:
        # print("The interpolants are not equivalent")
        return False

def check_equivalence_by_basename(basename,K):
    output_log="SanityCheck.log"
    with open(output_log, "a") as f:
        f.write(f"Checking {basename} with K={K}\n")
        for k in range(K):
            if not os.path.exists(f"ProofDoorBenchmark/interpolant_as_cnfs/{basename}.{K}.{k}.smt2.cnf"):
                f.write(f"  file {basename}.{K}.{k}.smt2.cnf does not exist")
                continue
            if not os.path.exists(f"ProofDoorBenchmark/interpolants/{K}/{basename}.{K}.{k}.interpolant"):
                f.write(f"  file {basename}.{K}.{k}.interpolant does not exist")
                continue
            if not os.path.exists(f"ProofDoorBenchmark/smts/{K}/{basename}.{K}.{k}.smt2"):
                f.write(f"  file {basename}.{K}.{k}.smt2 does not exist")
                continue
            
            if check_equivalence(
                f"ProofDoorBenchmark/interpolant_as_cnfs/{basename}.{K}.{k}.smt2.cnf",
                f"ProofDoorBenchmark/interpolants/{K}/{basename}.{K}.{k}.interpolant",
                f"ProofDoorBenchmark/smts/{K}/{basename}.{K}.{k}.smt2"
            ):
                f.write(f"The interpolants are equivalent for {basename}.{K}.{k}\n")
            else:
                f.write(f"The interpolants are not equivalent for {basename}.{K}.{k}\n")

def check_interpolant_in_wires(basename,K,j):
    wire_file = f"ProofDoorBenchmark/wires/{K}/{basename}.{K}.{j+1}.wires.json"
    if not os.path.exists(wire_file):
        return False
    with open(wire_file, "r") as f:
        data = json.load(f)
    wires = data["wires"]
    interpolant_file_cnf = f"ProofDoorBenchmark/interpolant_as_cnfs/{basename}.{K}.{j}.smt2.cnf"
    dimacs_file = f"ProofDoorBenchmark/interpolant_as_cnfs/{basename}.{K}.{j}.dimacs"
    # if not os.path.exists(dimacs_file):
    dimacs = parse_interpolant_cnf_to_dimacs(interpolant_file_cnf,dimacs_file)
    interpolant_cnf = CNF.from_file(dimacs_file)
    
    literals = interpolant_cnf.get_literals()
    # for wire in tqdm(wires):
    for literal in tqdm(literals):
        if abs(literal) not in wires:
            print(f"wire: {wires}, literal: {literal}")
            print(f"literals: {literals}")
            return False
    print("Wire contains interpolant")
    return True

def main():
    check_interpolant_in_wires("6s159",40,20)
    # category_list = get_instance_list("linear")
    # for category in category_list:
    #     check_equivalence_by_basename(category,60)
    # check_equivalence_by_basename("139442p0",60)
    # check_equivalence(
    #     "ProofDoorBenchmark/interpolant_as_cnfs/139442p0.60.1.smt2.cnf",
    #     "ProofDoorBenchmark/interpolants/60/139442p0.60.1.interpolant",
    #     "ProofDoorBenchmark/smts/60/139442p0.60.1.smt2"
    # )
    # check_equivalence(
    #     "test/6s0.4.0.smt2.cnf",
    #     "test/6s0.4.0.interpolant",
    #     "test/6s0.4.0.smt2"
    # )


    pass

if __name__ == "__main__":
    main()