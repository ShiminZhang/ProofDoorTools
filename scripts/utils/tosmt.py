import sys
import os
from utils.utils import parse_sexp
from utils.paths import get_interpolant_dir

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


def literal_to_expr(literal):
    var = abs(literal)
    if literal > 0:
        return f"v{var}"
    else:
        return f"(not v{var})"


def clause_to_expr(clause):
    return "(or " + " ".join(literal_to_expr(lit) for lit in clause) + ")"


def block_to_and_expr(block):
    lines = ["(and"]
    for clause in block:
        lines.append(f"    {clause_to_expr(clause)}")
    lines.append(")")
    return lines


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

def construct_compute_interpolant_cmd_from_interpolant(interpolants,B):
    # A and B are lists of clauses
    output_lines = []
    output_lines.append("(compute-interpolant")
    right_cnf = []
    for block in B:
        right_cnf.extend(block)
    right_expr = block_to_and_expr(right_cnf)
    output_lines.extend(f"    (and\n")
    for interpolant in interpolants:
        for line in interpolant:
            output_lines.append(f"      {line.strip()}")
    output_lines.append("    )\n")
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
    print(lines[-1])
    lines[-1] = lines[-1].strip()[:-1]
    print(lines[-1])
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
        print(interpolants)
        compute_smt = construct_compute_interpolant_cmd_from_interpolant(interpolants,blocks[index:])
        
    smt2_lines = declarations.copy()
    smt2_lines.append("")
    smt2_lines.extend(compute_smt)
    with open(f"{output_path}", 'w') as f:
        f.write("\n".join(smt2_lines))

def cnf_to_smt2_def2(input_path, output_path):
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    index = int(parts[2])
    name = parts[0]
    k = int(parts[1])
    blocks, max_var = parse_cnf_file(input_path)
    declarations = generate_declarations(max_var)
    compute_smt = construct_compute_interpolant_cmd(blocks[0],blocks[1])
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


# Example usage:
# cnf_to_smt2_n_way("input.cnf", "output.smt2")

if __name__ == "__main__":
    # if len(sys.argv) != 2:
    #     print("Usage: python CNFtoQFBV.py <input_file.cnf>")
    #     sys.exit(1)

    # input_file = sys.argv[1]
    # if not os.path.isfile(input_file):
    #     print(f"Error: File '{input_file}' not found.")
    #     sys.exit(1)


    # output_file = os.path.splitext(input_file)[0]
    name = "6s4"
    k = 15
    index = 0
    cnf_path = f"ProofDoorBenchmark/cnfs/15/{name}.{k}.cnf"
    smt_path = f"ProofDoorBenchmark/smts/15/{name}.{k}.{index}.smt2"
    cnf_to_smt2_n_way(cnf_path, smt_path)
    print(f"SMT2 file written to: {smt_path}")