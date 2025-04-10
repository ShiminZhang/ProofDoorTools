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
    val = '1' if literal > 0 else '0'
    return f"(= v{var} {val})"


def clause_to_expr(clause):
    return "(or " + " ".join(literal_to_expr(lit) for lit in clause) + ")"


def block_to_and_expr(block):
    lines = ["(and"]
    for clause in block:
        lines.append(f"    {clause_to_expr(clause)}")
    lines.append(")")
    return lines


def generate_declarations(max_var):
    return [f"(declare-const v{i} Int)" for i in range(1, max_var + 1)]


def generate_single_compute_interpolant(blocks):
    output_lines = ["(compute-interpolant"]
    for block in blocks:
        block_expr = block_to_and_expr(block)
        output_lines.extend(f"    {line}" for line in block_expr)
    output_lines.append(")")
    return output_lines


def cnf_to_smt2_n_way(input_path, output_path):
    blocks, max_var = parse_cnf_file(input_path)
    if len(blocks) < 2:
        raise ValueError("At least two clause blocks are required.")

    smt2_lines = generate_declarations(max_var)
    smt2_lines.append("")
    smt2_lines += generate_single_compute_interpolant(blocks)

    with open(output_path, 'w') as f:
        f.write("\n".join(smt2_lines))


# Example usage:
# cnf_to_smt2_n_way("input.cnf", "output.smt2")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cnf_to_smt2.py <input_file.cnf>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.isfile(input_file):
        print(f"Error: File '{input_file}' not found.")
        sys.exit(1)

    output_file = os.path.splitext(input_file)[0] + ".smt2"
    cnf_to_smt2_n_way(input_file, output_file)
    print(f"SMT2 file written to: {output_file}")