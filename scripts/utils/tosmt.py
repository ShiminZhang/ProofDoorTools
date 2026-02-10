import sys
import os
from utils.paths import get_interpolant_dir, get_wires_dir, get_cnfs_dir
import json
from utils.process_cnf import CNF
from utils.absorption_analysis import compute_wire_and_save
from utils.interpolant_sanity_check import check_cnf_A_implication
from utils.paths import get_CNF_dir


def literal_to_expr(literal: int) -> str:
    var = abs(literal)
    if literal > 0:
        return f"v{var}"
    return f"(not v{var})"

def clause_to_expr(clause) -> str:
    # A clause is a disjunction of literals.
    return "(or " + " ".join(literal_to_expr(lit) for lit in clause) + ")"

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
            # CNF produced by our pipeline typically starts with "c iter 0".
            # The previous implementation appended an empty `current_block` here,
            # which shifted block indices by 1 and could generate empty SMT terms
            # like `(and)` in the interpolant query. Skip empty blocks.
            if current_block:
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

def _emit_conjunction(output_lines, terms, indent: str = "    "):
    """
    Emit a conjunction term with robust empty handling.

    - If `terms` is empty (or only contains empty terms), emit `true`
    - If exactly one term, emit that term directly
    - Else emit `(and <term1> <term2> ...)`

    `terms` is a list of "term lines" (each term is a list[str]) so we can
    embed multi-line interpolants safely.
    """
    normalized = []
    for term in terms:
        if not term:
            continue
        stripped = [ln.strip() for ln in term if ln.strip()]
        if stripped:
            normalized.append(stripped)

    if not normalized:
        output_lines.append(f"{indent}true")
        return

    if len(normalized) == 1:
        for ln in normalized[0]:
            output_lines.append(f"{indent}{ln}")
        return

    output_lines.append(f"{indent}(and")
    for term in normalized:
        for ln in term:
            output_lines.append(f"{indent}  {ln}")
    output_lines.append(f"{indent})")

def _clauses_to_terms(clauses):
    """Represent a CNF (list of clauses) as a list of single-line terms."""
    return [[clause_to_expr(clause)] for clause in clauses]

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
        # Avoid emitting `(and)` with 0 args; use `true` for empty conjunction.
        _emit_conjunction(current_interpolant, _clauses_to_terms(left), indent="    ")
        _emit_conjunction(current_interpolant, _clauses_to_terms(right), indent="    ")
        current_interpolant.append(")")
        output_lines.append(current_interpolant)
    return output_lines

def construct_compute_interpolant_cmd_def1(interpolants,A,B,reverse=False):
    # A and B are lists of clauses
    output_lines = []
    output_lines.append("(compute-interpolant")
    left_cnf = []
    for block in A:
        left_cnf.extend(block)
    right_cnf = []
    for block in B:
        right_cnf.extend(block)
    left_terms = []
    right_terms = []
    # CNF clauses are single-line terms. Interpolants can be multi-line terms.
    left_terms.extend(_clauses_to_terms(left_cnf))
    right_terms.extend(_clauses_to_terms(right_cnf))
    if reverse:
        # Reverse mode: compute J as interpolant for (B_tail, (and I_prev A_i))
        # Do NOT negate here; we will negate the RESULT after Z3 returns.
        # Swap roles so left side becomes B_tail, right side becomes A_i
        # First argument: B_tail
        _emit_conjunction(output_lines, right_terms, indent="    ")
        # Second argument: (and I_prev A_i)
        i_terms = []
        i_terms.extend([interp for interp in interpolants])
        i_terms.extend(left_terms)
        _emit_conjunction(output_lines, i_terms, indent="    ")
    else:
        # Forward mode: (and I_prev A_i) as left, B_tail as right
        i_terms = []
        i_terms.extend([interp for interp in interpolants])
        i_terms.extend(left_terms)
        _emit_conjunction(output_lines, i_terms, indent="    ")
        _emit_conjunction(output_lines, right_terms, indent="    ")
    output_lines.append(")")
    return output_lines

def construct_compute_interpolant_cmd(A,B,reverse=False):
    # A and B are lists of clauses
    output_lines = []
    output_lines.append("(compute-interpolant")
    left_cnf = []
    right_cnf = []
    for block in A:
        left_cnf.extend(block)
    for block in B:
        right_cnf.extend(block)
    left_terms = _clauses_to_terms(left_cnf)
    right_terms = _clauses_to_terms(right_cnf)
    if reverse:
        left_terms, right_terms = right_terms, left_terms
    _emit_conjunction(output_lines, left_terms, indent="    ")
    _emit_conjunction(output_lines, right_terms, indent="    ")
    output_lines.append(")")
    return output_lines

def read_interpolant(interpolant_path):
    with open(interpolant_path, 'r') as f:
        raw_lines = [ln.rstrip("\n") for ln in f.readlines()]
    if not raw_lines:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! error reading interpolant file {interpolant_path}: empty file")
        exit()
    header = raw_lines[0].strip().lower()
    if header.startswith("sat") or "error" in header or header.startswith("unknown"):
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! error reading interpolant file {interpolant_path}: {raw_lines[0]}")
        exit()
    # Expect standard z3 output:
    #   unsat
    #   (interpolants
    #     <body>
    #   )
    lines = raw_lines[2:]
    if not lines:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! error reading interpolant file {interpolant_path}: missing interpolant body")
        exit()
    # remove the last bracket on the last body line to ease embedding
    try:
        lines[-1] = lines[-1].strip()[:-1]
    except Exception as e:
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! error reading interpolant file {interpolant_path}: {e}")
        exit()
    return lines
# def cnf_to_smt2_def1_reverse(input_path, output_path):
#     # the interpolants must be computed in reverse order, so actually if index of output is 0 we need to compute the last
#     basefilename = output_path.split("/")[-1]
#     parts = basefilename.split(".")
#     k_value = int(parts[1])
#     index = k_value - 1 - int(parts[2])
#     name = parts[0]
#     blocks, max_var = parse_cnf_file(input_path)
#     # interpolants = generate_single_compute_interpolant(blocks)
#     declarations = generate_declarations(max_var)
#     if index == k_value - 1:
#         # print(blocks[0:1])
#         # print(blocks[1:])
#         compute_smt = construct_compute_interpolant_cmd(blocks[-1:],blocks[:-1])
#     else:
#         interpolants = []
#         for i in range(index):
#             interpolant_path = f"{get_interpolant_dir(k_value,pddef=1)}/{name}.{k_value}.{i}.interpolant"
#             print(f"    reading {i}th interpolant: {interpolant_path}")
#             interpolants.append(read_interpolant(interpolant_path))
#         # print(interpolants)
#         compute_smt = construct_compute_interpolant_cmd_def1(interpolants,[blocks[index]],blocks[index+1:])
        
#     smt2_lines = declarations.copy()
#     smt2_lines.append("")
#     smt2_lines.extend(compute_smt)
#     with open(f"{output_path}", 'w') as f:
#         f.write("\n".join(smt2_lines))


def cnf_to_smt2_def1(input_path, output_path, reverse=False):
    print(f"Generating {output_path}, reverse={reverse}")
    basefilename = output_path.split("/")[-1]
    parts = basefilename.split(".")
    file_index = int(parts[2])
    name = parts[0]
    k_value = int(parts[1])
    # output filename may include a permutation token:
    #   <name>.<K>.<idx>.perm_<type>_<perm_idx>[.reverse].smt2
    # We need to carry that token when referencing previous interpolants,
    # otherwise we mix permuted A/B with non-permuted I_prev and Z3 may return "sat".
    perm_token = None
    if len(parts) >= 5 and parts[3].startswith("perm_"):
        perm_token = parts[3]  # e.g. "perm_iteration_0"
    perm_suffix = f".{perm_token}" if perm_token else ""
    blocks, max_var = parse_cnf_file(input_path)
    # Reverse mode computes from the last external index (k-1) down to 0.
    # We keep external filenames using the real index, but map to an internal
    # "forward-like" index on the reversed blocks list so the recurrence is
    # identical to forward mode.
    #
    # Mapping:
    #   internal_index = (k-1 - file_index)
    #   prev external index (already computed) = file_index + 1
    internal_index = file_index
    if reverse:
        internal_index = (k_value - 1 - file_index)
        blocks = blocks[::-1]
    # interpolants = generate_single_compute_interpolant(blocks)
    declarations = generate_declarations(max_var)
    if internal_index == 0:
        # print(blocks[0:1])
        # print(blocks[1:])
        compute_smt = construct_compute_interpolant_cmd(blocks[0:1],blocks[1:], reverse=False)
    else:
        interpolants = []
        prev_file_index = file_index - 1
        suffix = ".reverse" if reverse else ""
        if reverse:
            # external order is descending, so previous computed interpolant is (file_index + 1)
            prev_file_index = file_index + 1
        interpolant_path = f"{get_interpolant_dir(k_value,pddef=1)}/{name}.{k_value}.{prev_file_index}{perm_suffix}{suffix}.interpolant"
        print(f"    reading {prev_file_index}th interpolant: {interpolant_path}")
        interpolants.append(read_interpolant(interpolant_path))
        # print(interpolants)
        compute_smt = construct_compute_interpolant_cmd_def1(
            interpolants,
            [blocks[internal_index]],
            blocks[internal_index + 1 :],
            reverse=False,
        )
        
    smt2_lines = declarations.copy()
    smt2_lines.append("")
    smt2_lines.extend(compute_smt)
    with open(f"{output_path}", 'w') as f:
        f.write("\n".join(smt2_lines))

def compute_interpolant_def3(name, k_value, force_refresh: bool = False):
    # Heavy deps are imported lazily so SMT2 generation does not require numpy/scipy/sklearn.
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    # Def3 relies on per-index wires; respect force_refresh so caches can be regenerated.
    compute_wire_and_save(CNF.from_file(cnf_path), force_refresh=force_refresh)
    wires_map = {}
    for index in range(k_value):
        wire_path = f"{get_wires_dir(k_value)}/{name}.{k_value}.{index}.wires.json"
        wires = json.load(open(wire_path))["wires"]
        # Wires are shared *variables*; normalize with abs() for backwards compat
        # in case old cache files contain signed literals.
        wires_map[index] = {abs(int(w)) for w in wires}
    proof_path = f"{get_cnfs_dir(k_value)}/{name}.{k_value}.cadicalplain.drat"
    print(f"Reading proof from {proof_path}")
    with open(proof_path, 'r') as f:
        lines = f.readlines()
    clause_wire_map = {}
    for index in range(k_value):
        clause_wire_map[index] = []
    for line in lines:
        line = line.strip()
        if line.startswith("c") or line.startswith("d"):
            continue
        else:
            literals = [int(literal) for literal in line.split(" ")[:-1]]
            if len(literals) == 0:
                continue
            # Only keep clauses whose *every* literal is in this index's wire set.
            # (Previous implementation appended unconditionally, causing all indices
            # to get identical interpolant clause lists.)
            for index in range(k_value):
                wires = wires_map[index]
                if all(abs(lit) in wires for lit in literals):
                    clause_wire_map[index].append(literals)

            # # check if A -> clause
            # if not check_cnf_A_implication(name, k_value, index, literals):
            #     continue
            # matched_clauses.append(literals)
    return clause_wire_map

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