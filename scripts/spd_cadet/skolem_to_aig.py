"""
Given a completed Manthan Skolem function (.skolem.v) and the corresponding
QDIMACS input, substitute the Skolem witnesses into the formula and produce
an AIG via ABC.

Pipeline:
  1. Parse QDIMACS  → remaining_vars (∀), elim_vars (∃), clauses
  2. Generate a wrapper Verilog that instantiates SkolemFormula and encodes
     the CNF formula with elim_vars replaced by Skolem outputs
  3. Run ABC: read_verilog → strash → dc2 → write_aiger
"""

import os
import sys
import argparse
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ABC_BIN = os.path.abspath(
    "./External/manthan/dependencies/abc/abc"
)

SKOLEM_DIR_TEMPLATE  = "./ProofDoorBenchmark/skolem_spd_manthan/{K}/"
QDIMACS_DIR_TEMPLATE = "./ProofDoorBenchmark/qdimacs_spd_skolem/{K}/"
AAG_DIR_TEMPLATE     = "./ProofDoorBenchmark/interpolant_aig_manthan/{K}/"


def get_skolem_path(name, K, i):
    return os.path.join(SKOLEM_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.skolem.v")

def get_qdimacs_path(name, K, i):
    return os.path.join(QDIMACS_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.qdimacs")

def get_aag_path(name, K, i):
    d = AAG_DIR_TEMPLATE.format(K=K)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.{K}.{i}.aag")

def get_wrapper_path(name, K, i):
    d = AAG_DIR_TEMPLATE.format(K=K)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.{K}.{i}.wrapper.v")


def parse_qdimacs(path):
    remaining_vars = []
    elim_vars      = []
    clauses        = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] == 'c':
                continue
            if line[0] == 'p':
                continue
            if line[0] == 'a':
                remaining_vars = [int(x) for x in line.split()[1:] if x != '0']
            elif line[0] == 'e':
                elim_vars = [int(x) for x in line.split()[1:] if x != '0']
            else:
                lits = [int(x) for x in line.split()]
                if lits and lits[-1] == 0:
                    lits = lits[:-1]
                if lits:
                    clauses.append(lits)
    return remaining_vars, elim_vars, clauses


def generate_wrapper_verilog(skolem_path, remaining_vars, elim_vars, clauses):
    elim_set      = set(elim_vars)
    remaining_set = set(remaining_vars)

    lines = []

    # Inline the SkolemFormula module
    with open(skolem_path) as f:
        lines.append(f.read())
    lines.append("\n")

    # ---- Interpolant module ------------------------------------------------
    input_ports = [f"i{v}" for v in remaining_vars]
    port_list   = ", ".join(input_ports + ["result"])
    lines.append(f"module Interpolant ({port_list});\n")

    for v in remaining_vars:
        lines.append(f"  input i{v};\n")
    lines.append("  output result;\n\n")

    # Wires for elim_vars (driven by Skolem outputs)
    for v in elim_vars:
        lines.append(f"  wire e{v};\n")
    lines.append("\n")

    # Instantiate SkolemFormula
    conns = []
    for v in remaining_vars:
        conns.append(f".i{v}(i{v})")
    for v in elim_vars:
        conns.append(f".o{v}(e{v})")
    lines.append(f"  SkolemFormula skolem ({', '.join(conns)});\n\n")

    # One wire per clause: OR of its literals
    for j, clause in enumerate(clauses):
        lits_expr = []
        for lit in clause:
            var = abs(lit)
            if var in elim_set:
                wire = f"e{var}"
            elif var in remaining_set:
                wire = f"i{var}"
            else:
                # variable not quantified — treat as free input (should not happen)
                wire = f"i{var}"
            lits_expr.append(f"~{wire}" if lit < 0 else wire)
        expr = " | ".join(lits_expr) if lits_expr else "1'b0"
        lines.append(f"  wire c{j}; assign c{j} = {expr};\n")

    lines.append("\n")

    # AND-reduce all clause wires
    n = len(clauses)
    if n == 0:
        lines.append("  assign result = 1'b1;\n")
    elif n == 1:
        lines.append("  assign result = c0;\n")
    else:
        lines.append(f"  wire r0; assign r0 = c0 & c1;\n")
        for j in range(2, n):
            lines.append(f"  wire r{j-1}; assign r{j-1} = r{j-2} & c{j};\n")
        lines.append(f"  assign result = r{n-2};\n")

    lines.append("endmodule\n")
    return "".join(lines)


def run_abc(wrapper_path, aag_path):
    abs_wrapper = os.path.abspath(wrapper_path)
    abs_aag     = os.path.abspath(aag_path)
    script = f"read_verilog {abs_wrapper}; strash; dc2; write_aiger -s {abs_aag}"
    cmd    = [ABC_BIN, "-c", script]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout)
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"ABC failed with exit code {result.returncode}")


def skolem_to_aig(name, K, i, keep_wrapper=False):
    skolem_path  = get_skolem_path(name, K, i)
    qdimacs_path = get_qdimacs_path(name, K, i)
    aag_path     = get_aag_path(name, K, i)
    wrapper_path = get_wrapper_path(name, K, i)

    if not os.path.exists(skolem_path):
        raise FileNotFoundError(f"Skolem file not found: {skolem_path}")
    if not os.path.exists(qdimacs_path):
        raise FileNotFoundError(f"QDIMACS file not found: {qdimacs_path}")

    print(f"Parsing QDIMACS: {qdimacs_path}")
    remaining_vars, elim_vars, clauses = parse_qdimacs(qdimacs_path)
    print(f"  remaining={len(remaining_vars)}  elim={len(elim_vars)}  clauses={len(clauses)}")

    print("Generating wrapper Verilog...")
    wrapper = generate_wrapper_verilog(skolem_path, remaining_vars, elim_vars, clauses)
    with open(wrapper_path, "w") as f:
        f.write(wrapper)
    print(f"  Written: {wrapper_path}")

    run_abc(wrapper_path, aag_path)
    print(f"AAG written: {aag_path}")
    print(f"  Symbol table in AAG maps each AIG input index → original CNF variable name (i<N>)")

    if not keep_wrapper:
        os.remove(wrapper_path)

    return aag_path


def main():
    parser = argparse.ArgumentParser(
        description="Substitute Manthan Skolem function into QDIMACS and produce AIG via ABC"
    )
    parser.add_argument("--name",         required=True, help="Instance name")
    parser.add_argument("--K",            type=int, required=True, help="K value")
    parser.add_argument("--i",            type=int, required=True, help="Iteration index")
    parser.add_argument("--keep-wrapper", action="store_true",
                        help="Keep the intermediate wrapper Verilog file")
    args = parser.parse_args()

    skolem_to_aig(args.name, args.K, args.i, keep_wrapper=args.keep_wrapper)



if __name__ == "__main__":
    main()
