# import z3
from utils.utils import read_smt2_file, read_interpolant, to_pure_smt2, parse_interpolant_cnf_to_dimacs
from utils.absorption_analysis import CNF
from utils.paths import *
from z3 import *
import argparse
from utils.catagory import get_instance_list
from interpolant_sanity_check import check_interpolant_valid_in_cnfs
import os
import json
from tqdm import tqdm
import time

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
                constructed_line += f" (not {chunk} "
            else:
                constructed_line += f" {chunk} "
        constructed_line+= ")"
        non_def_content += constructed_line + "\n"
    non_def_content += "))  "
    # for line in lines:
    #     print(line)
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

# def check_interpolant_valid_in_cnfs(basename,K):



def check_equivalence_by_basename(basename,K,pddef):

    if pddef == 3:
        return check_interpolant_valid_in_cnfs(basename,K,pddef)

    output_log=f"SanityCheck_{basename}_K={K}_pddef={pddef}.log"
    with open(output_log, "a") as f:
        f.write(f"Checking {basename} with K={K}\n")
        for k in range(K):
            print(f"Checking {basename}.{K}.{k}")
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

def get_queue_size():
    return int(os.popen("squeue -u $USER -h -r -t RUNNING,PENDING | wc -l").read())

def summarize_sanity_check(K, pddef):
    slurm_out_dir = "./SlurmLogs/sanity_check/"
    files = os.listdir(slurm_out_dir)
    for file in files:
        if file.endswith(f".{K}.sanity_check.log"):
            with open(os.path.join(slurm_out_dir, file), "r") as f:
                content = f.read()
                if "Interpolant is not valid" in content:
                    print(f"Interpolant is NOT valid: {file}")
                else:
                    print(f"Interpolant is valid: {file}")
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--basename", type=str, default="139442p0")
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--pddef", type=int, default=0)
    parser.add_argument("--summarize", action="store_true", default=False)
    parser.add_argument("--manage", action="store_true", default=False)

    args = parser.parse_args()
    if args.summarize:
        summarize_sanity_check(args.K, args.pddef)
        return
    if args.all:
        instance_list = get_instance_list("all")
        if args.manage:
            batch_size = args.K
            limit = 1000
            index = 0
            while index < batch_size * len(instance_list):
                queue_size = get_queue_size()
                print(f"Queue size: {queue_size}, Index: {index}")
                while get_queue_size() < limit - batch_size and index < batch_size * len(instance_list):
                    name = instance_list[index // batch_size]

                    activate_python = "source .env; source $PYENVPATH"
                    slurm_out_dir = "./SlurmLogs/sanity_check/"
                    os.makedirs(slurm_out_dir,exist_ok=True)
                    wrapped = f"{activate_python} && python ./scripts/sanity_check.py --basename {name} --K {args.K} --pddef {args.pddef} "
                    os.system(f"sbatch --job-name=sc_{name}.{args.K} --output={slurm_out_dir}/{name}.{args.K}.sanity_check.log --mem=16g --time=5:00:00 --wrap=\"{wrapped}\"")

                    # check_equivalence_by_basename(name,args.K,args.pddef)
                    index += batch_size
                print(f"Updated Index: {index}, Queue size: {get_queue_size()}")
                time.sleep(180)
        else:
            for instance in instance_list:
                check_equivalence_by_basename(instance,args.K,args.pddef)
    else:
        check_equivalence_by_basename(args.basename,args.K,args.pddef)

    # check_interpolant_valid_in_cnfs(args.basename, args.K, args.pddef)
    # check_interpolant_in_wires("6s159",40,20)
    # category_list = get_instance_list("linear")
    # for category in category_list:
    #     check_equivalence_by_basename(category,60)
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