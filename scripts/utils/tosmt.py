import sys
import os

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


def cnf_to_smt2_n_way(input_path, output_path):
    blocks, max_var = parse_cnf_file(input_path)
    if len(blocks) < 2:
        raise ValueError("At least two clause blocks are required.")

    declarations = generate_declarations(max_var)
    interpolants = generate_single_compute_interpolant(blocks)
    i=0
    for interpolant in interpolants:
        smt2_lines = declarations.copy()
        smt2_lines.append("")
        smt2_lines.extend(interpolant)
        # for item in smt2_lines:
            # print(item)
        with open(f"{output_path}.{i}.smt2", 'w') as f:
            f.write("\n".join(smt2_lines))
        i+=1


# Example usage:
# cnf_to_smt2_n_way("input.cnf", "output.smt2")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python CNFtoQFBV.py <input_file.cnf>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)

    output_file = os.path.splitext(input_file)[0]
    cnf_to_smt2_n_way(input_file, output_file)
    print(f"SMT2 file written to: {output_file}")