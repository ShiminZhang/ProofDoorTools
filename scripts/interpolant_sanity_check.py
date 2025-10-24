import sys
import os
from utils.paths import get_CNF_dir, get_sanity_dir, get_interpolant_dir
from utils.utils import read_smt2_file, read_interpolant
import argparse
from utils.catagory import get_instance_list
from z3 import Solver, And, Not, unsat,parse_smt2_string


def parse_cnf_file(filepath):
    if not os.path.exists(filepath):
        return [],0
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
        current_interpolant=["(assert"]
        left_expr = block_to_and_expr(left)
        right_expr = block_to_and_expr(right)
        current_interpolant.extend(f"    {line}" for line in left_expr)
        current_interpolant.append(")")
        current_interpolant.append("(assert")
        current_interpolant.extend(f"    {line}" for line in right_expr)
        current_interpolant.append(")")
        output_lines.append(current_interpolant)
    return output_lines


def cnf_to_smt2_sanity(name, K, pddef):
    cnf_path = get_CNF_dir(K) + name + f".{K}.cnf"

    blocks, max_var = parse_cnf_file(cnf_path)
    if len(blocks) < 2:
        raise ValueError("At least two clause blocks are required.")

    declarations = generate_declarations(max_var)
    assertion_pairs = generate_single_compute_interpolant(blocks)

    i=0
    for pair in assertion_pairs:
        output_path = get_sanity_dir(K, pddef) + name + f".{i}.sanity.smt2"        
        smt2_lines = declarations.copy()
        smt2_lines.append("")
        smt2_lines.extend(pair)
        with open(f"{output_path}", 'w') as f:
            f.write("\n".join(smt2_lines))
        i+=1

def read_interpolant_pddef3(interpolant_file, definitions):
    # the interpolant files from pddef3 are actually in cnf form without header
    blocks, max_var = parse_cnf_file(interpolant_file)
    if len(blocks) == 0:
        return None
    expressions = block_to_and_expr(blocks[0])
    result = "(assert "
    for expression in expressions:
        result += expression + " "
    result += ")"
    return result


def check_implication(a, b):
    s = Solver()
    s.add(And(a, Not(b)))
    return s.check() == unsat

def check_implication_not(a, b):
    s = Solver()
    s.add(And(a, b))
    return s.check() == unsat

def check_cnf_A_implication(name, K,i, clause):
    output_path = get_sanity_dir(K, 3) + name + f".{i}.sanity.smt2"
    if not os.path.exists(output_path):
        cnf_to_smt2_sanity(name, K, 3)
    
    assert1, assert2, definitions = read_smt2_file(output_path)
    s = Solver()
    # print(f"Clause: {clause}")
    clause  = [lit for lit in clause if lit != 0]
    block = [clause]
    # print(f"Blocks: {block}")
    expressions = block_to_and_expr(block)
    result = ""
    for definition in definitions:
        result += definition + "\n"
    result += "(assert "
    for expression in expressions:
        result += expression + " "
    result += ")"
    # print(f"Clause SMT: {result}")
    clause_smt = And(parse_smt2_string(result))

    s.add(And(assert1, Not(clause_smt)))
    return s.check() == unsat


def check_interpolant_valid_in_cnfs(name, K, pddef):
    print("-"*100)
    print(f"Checking {name} with K={K} and pddef={pddef}")
    for i in range(K):
        cnf_path = get_CNF_dir(K) + name + f".{K}.cnf"
        if not os.path.exists(cnf_path):
            print(f"CNF file {cnf_path} does not exist")
            continue
        cnf_to_smt2_sanity(name, K, pddef)
        smt2_file = get_sanity_dir(K, pddef) + name + f".{i}.sanity.smt2"
        assert1, assert2, definitions = read_smt2_file(smt2_file)
        interpolant_file = get_interpolant_dir(K, pddef) + name + f".{K}.{i}.interpolant"
        if pddef != 3:
            interpolant = read_interpolant(interpolant_file, definitions)
        else:
            interpolant = read_interpolant_pddef3(interpolant_file, definitions)
            if interpolant is None:
                print(f"Interpolant file {interpolant_file} is empty, skipping")
                break
            smt_expression = ""
            for definition in definitions:
                smt_expression += definition + "\n"
            smt_expression += interpolant
            interpolant = And(parse_smt2_string(smt_expression))
        # print(f"Interpolant: {interpolant}")
        # print(f"Assert 1: {assert1}")
        # print(f"Assert 2: {assert2}")
        # Check implications
        implies1 = check_implication(assert1, interpolant)
        implies2 = check_implication_not(interpolant, assert2)
        
        print(f"{i} A -> I: {implies1}")
        print(f"{i} I -> not B: {implies2}")

        implies3 = check_implication(assert2, interpolant)
        implies4 = check_implication_not(interpolant, assert1)
        
        print(f"{i} B -> I: {implies3}")
        print(f"{i} I -> not A: {implies4}")
        if (not implies1 or not implies2) and (not implies3 or not implies4):
            print(f"Interpolant is not valid in {name} with K={K} and pddef={pddef}")
            break

# Example usage:
# cnf_to_smt2_n_way("input.cnf", "output.smt2")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check interpolant validity in CNFs")
    parser.add_argument("--name", type=str, default=None, help="Name of the interpolant")
    parser.add_argument("--K", type=int, default=10, help="Number of clause blocks")
    parser.add_argument("--pddef", type=int, default=0, help="Proof Door Definition")
    parser.add_argument("--all", action="store_true", help="Check all instances")
    args = parser.parse_args()
    if args.all:
        instance_list = get_instance_list("all")
        for instance in instance_list:
            check_interpolant_valid_in_cnfs(instance, args.K, args.pddef)
    elif args.name:
        check_interpolant_valid_in_cnfs(args.name, args.K, args.pddef)