import sys
import os
from utils.utils import parse_sexp, literal_to_expr, clause_to_expr, block_to_and_expr
from utils.paths import get_interpolant_dir, get_wires_dir, get_cnfs_dir
from utils.process_cnf import CNF
from utils.absorption_analysis import compute_wire_and_save
import json
from interpolant_sanity_check import check_cnf_A_implication

def parse_cnf_file(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()

    blocks = []
    current_block = []
    max_var = 0

    for line in lines:
        line = line.strip()
        if line.startswith("p"):
            continue
        elif line.startswith("c iter"):
            blocks.append(current_block)
            current_block = []
        elif line.startswith("c"):
            continue
        else:
            clause = list(map(int, line.split()))
            clause = [lit for lit in clause if lit != 0]
            if clause:
                current_block.append(clause)
                max_var = max(max_var, max(abs(lit) for lit in clause))

    if current_block:
        blocks.append(current_block)

    return blocks, max_var


def generate_declarations(max_var):
    return [f"(declare-const v{i} Bool)" for i in range(1, max_var + 1)]


def generate_single_compute_interpolant(blocks):
    # output_lines = ["(set-logic QF_UF)"]
    output_lines = []
    N_of_blocks = len(blocks)
    extended_blocks=[]
    for i in range(N_of_blocks-1):
        left=[]
        right=[]
        j=0
        for block in blocks:
            if j <= i:
                left.extend(block)
            else:
                right.extend(block)
            j+=1
        extended_blocks.append((left,right))
        
    for block_tuple in extended_blocks:
        # print(block)
        left,right = block_tuple
        current_interpolant=["(compute-interpolant"]
        left_expr = block_to_and_expr(left)
        right_expr = block_to_and_expr(right)
        current_interpolant.extend(f"    {line}" for line in left_expr)
        current_interpolant.extend(f"    {line}" for line in right_expr)
        current_interpolant.append(")")
        output_lines.append(current_interpolant)
    return output_lines

def construct_compute_interpolant_cmd_def1(interpolants,A,B):
    # A and B are lists of clauses
    output_lines = []
    output_lines.append("(compute-interpolant")
    left_cnf = []
    for block in A:
        left_cnf.extend(block)
    right_cnf = []
    for block in B:
        right_cnf.extend(block)
    left_expr = block_to_and_expr(left_cnf)
    right_expr = block_to_and_expr(right_cnf)
    output_lines.append(f"    (and")
    for interpolant in interpolants:
        for line in interpolant:
            output_lines.append(f"      {line.strip()}")
    for line in left_expr[1:-1]:
        output_lines.append(line)
    output_lines.append("    )")

    output_lines.extend(f"    {line}" for line in right_expr)
    output_lines.append(")")
    return output_lines

def construct_compute_interpolant_cmd(A,B):
    # A and B are lists of clauses
    output_lines = []
    output_lines.append("(compute-interpolant")
    left_cnf = []
    right_cnf = []
    for block in A:
        left_cnf.extend(block)
    for block in B:
        right_cnf.extend(block)
    left_expr = block_to_and_expr(left_cnf)
    right_expr = block_to_and_expr(right_cnf)
    output_lines.extend(f"    {line}" for line in left_expr)
    output_lines.extend(f"    {line}" for line in right_expr)
    output_lines.append(")")
    return output_lines

def read_interpolant(interpolant_path):
    with open(interpolant_path, 'r') as f:
        lines = f.readlines()[2:]
    # remove the last bracket
    lines[-1] = lines[-1].strip()[:-1]
    return lines

def cnf_to_smt2_def1(input_path, output_path):
    print(f"Generating {output_path}")
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    index = int(parts[2])
    name = parts[0]
    k_value = int(parts[1])
    blocks, max_var = parse_cnf_file(input_path)
    # interpolants = generate_single_compute_interpolant(blocks)
    declarations = generate_declarations(max_var)
    if index == 0:
        # print(blocks[0:1])
        # print(blocks[1:])
        compute_smt = construct_compute_interpolant_cmd(blocks[0:1],blocks[1:])
    else:
        interpolants = []
        for i in range(index):
            interpolant_path = f"{get_interpolant_dir(k_value,pddef=1)}/{name}.{k_value}.{i}.interpolant"
            print(f"    reading {i}th interpolant: {interpolant_path}")
            interpolants.append(read_interpolant(interpolant_path))
        # print(interpolants)
        compute_smt = construct_compute_interpolant_cmd_def1(interpolants,[blocks[index]],blocks[index+1:])
        
    smt2_lines = declarations.copy()
    smt2_lines.append("")
    smt2_lines.extend(compute_smt)
    with open(f"{output_path}", 'w') as f:
        f.write("\n".join(smt2_lines))

def compute_interpolant_def3(input_path, output_path):
    print(f"Generating {output_path}")
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    index = int(parts[2])
    name = parts[0]
    k_value = int(parts[1])
    blocks, max_var = parse_cnf_file(input_path)
    # interpolants = generate_single_compute_interpolant(blocks)
    # compute_proof() proofs should already be generated
    compute_wire_and_save(CNF.from_file(input_path))
    
    
    wire_path = f"{get_wires_dir(k_value)}/{name}.{k_value}.{index}.wires.json"
    wires = json.load(open(wire_path))["wires"]

    proof_path = f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cadicalplain.drat"
    print(f"Reading proof from {proof_path}")
    with open(proof_path, 'r') as f:
        lines = f.readlines()
    matched_clauses = []
    for line in lines:
        line = line.strip()
        if line.startswith("c") or line.startswith("d"):
            continue
        else:
            literals = [int(literal) for literal in line.split(" ")[:-1]]
            not_matched = False
            for literal in literals:
                if not literal in wires:
                    not_matched = True
                    break
            if not_matched or len(literals) == 0:
                continue

            # check if A -> clause
            if not check_cnf_A_implication(name, k_value, index, literals):
                continue
            matched_clauses.append(literals)
    return matched_clauses

def cnf_to_smt2_def2(input_path, output_path):
    print(f"Generating {output_path}")
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    index = int(parts[2])
    name = parts[0]
    k_value = int(parts[1])
    blocks, max_var = parse_cnf_file(input_path)
    # interpolants = generate_single_compute_interpolant(blocks)
    declarations = generate_declarations(max_var)
    if index == 0:
        # print(blocks[0:1])
        # print(blocks[1:])
        compute_smt = construct_compute_interpolant_cmd(blocks[0:1],blocks[1:2])
    else:
        interpolants = []
        for i in range(index):
            interpolant_path = f"{get_interpolant_dir(k_value,pddef=1)}/{name}.{k_value}.{i}.interpolant"
            print(f"    reading {i}th interpolant: {interpolant_path}")
            interpolants.append(read_interpolant(interpolant_path))
        # print(interpolants)
        compute_smt = construct_compute_interpolant_cmd_def1(interpolants,[],blocks[index:index+1])
        
    smt2_lines = declarations.copy()
    smt2_lines.append("")
    smt2_lines.extend(compute_smt)
    with open(f"{output_path}", 'w') as f:
        f.write("\n".join(smt2_lines))

def cnf_to_smt2_n_way(input_path, output_path):
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    index = int(parts[2])
    name = parts[0]
    k = int(parts[1])
    blocks, max_var = parse_cnf_file(input_path)
    if len(blocks) < 2:
        raise ValueError("At least two clause blocks are required.")

    declarations = generate_declarations(max_var)
    interpolants = generate_single_compute_interpolant(blocks)
    smt2_lines = declarations.copy()
    smt2_lines.append("")
    smt2_lines.extend(interpolants[index])
    # for item in smt2_lines:
        # print(item)
    with open(f"{output_path}", 'w') as f:
        f.write("\n".join(smt2_lines))



if __name__ == "__main__":
    name = "6s4"
    k = 15
    index = 0
    cnf_path = f"ProofDoorBenchmark/cnfs/15/{name}.{k}.cnf"
    smt_path = f"ProofDoorBenchmark/smts/15/{name}.{k}.{index}.smt2"
    cnf_to_smt2_n_way(cnf_path, smt_path)
    print(f"SMT2 file written to: {smt_path}")