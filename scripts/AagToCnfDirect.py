#!/usr/bin/env python3
"""
AagToCnfDirect.py

Convert an AIGER .aag file to DIMACS CNF via direct expansion (no auxiliary variables).
The output CNF is logically EQUIVALENT to the conjunction of all outputs being true
-- not merely equisatisfiable. No Tseitin variables are introduced.

Usage:
    python AagToCnfDirect.py input.aag [output.cnf]
    (output defaults to stdout if omitted)

WARNING: Clause count can grow exponentially with circuit depth due to the
cartesian-product step at each OR (= negated AND) node.

AAG literal encoding:
    variable v  ->  positive literal = 2*v,  negative literal = 2*v+1
    constant false = 0,  constant true = 1
"""

import sys


def parse_aag(path):
    with open(path) as f:
        lines = [ln.rstrip() for ln in f]

    i = 0
    while i < len(lines) and not lines[i].startswith("aag"):
        i += 1

    parts = lines[i].split()
    assert parts[0] == "aag", "Not an AAG file"
    M, I, L, O, A = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
    i += 1

    inputs = [int(lines[i + k]) for k in range(I)]
    i += I

    latches = []
    for k in range(L):
        latches.append(tuple(int(x) for x in lines[i + k].split()))
    i += L

    outputs = [int(lines[i + k]) for k in range(O)]
    i += O

    and_gates = {}
    for k in range(A):
        p = lines[i + k].split()
        lhs, rhs0, rhs1 = int(p[0]), int(p[1]), int(p[2])
        and_gates[lhs] = (rhs0, rhs1)

    return M, I, L, O, A, inputs, latches, outputs, and_gates


def expand(lit, and_gates, memo):
    """
    Return a list of clauses (each clause is a frozenset of DIMACS literals)
    whose conjunction is logically equivalent to `lit` being true.

    Positive AIGER literal 2v  -> DIMACS literal  v
    Negative AIGER literal 2v+1 -> DIMACS literal -v

    AND node, positive polarity  -> union of both children's clause sets
    AND node, negative polarity  -> cartesian product (one clause from each side merged)
    Leaf (input / latch output)  -> single unit clause
    """
    if lit in memo:
        return memo[lit]

    # Constants
    if lit == 0:
        memo[lit] = [frozenset()]   # empty clause = contradiction
        return memo[lit]
    if lit == 1:
        memo[lit] = []              # no clauses = tautology
        return memo[lit]

    var = lit >> 1
    neg = lit & 1
    pos_lit = var << 1  # even literal for this variable

    if pos_lit in and_gates:
        rhs0, rhs1 = and_gates[pos_lit]

        if neg == 0:
            # lit = rhs0 AND rhs1  =>  both sub-formulae must hold
            c0 = expand(rhs0, and_gates, memo)
            c1 = expand(rhs1, and_gates, memo)
            result = c0 + c1

        else:
            # lit = NOT(rhs0 AND rhs1) = NOT(rhs0) OR NOT(rhs1)
            # CNF of a disjunction = cartesian product of the two CNF sets:
            #   each pair (clause_from_left, clause_from_right) merges into one clause
            c0 = expand(rhs0 ^ 1, and_gates, memo)
            c1 = expand(rhs1 ^ 1, and_gates, memo)

            if not c0 or not c1:
                # One side is a tautology => whole disjunction is a tautology
                result = []
            else:
                result = []
                for cl0 in c0:
                    for cl1 in c1:
                        merged = cl0 | cl1
                        # Discard tautological clauses (contain both x and -x)
                        if not any(-x in merged for x in merged):
                            result.append(merged)

    else:
        # Primary input or latch output: leaf node
        dimacs = -var if neg else var
        result = [frozenset([dimacs])]

    memo[lit] = result
    return result


def aag_to_dimacs(input_path, output_path=None):
    M, I, L, O, A, inputs, latches, outputs, and_gates = parse_aag(input_path)

    if L > 0:
        print(
            f"Warning: {L} latch(es) found. Latch outputs are treated as free inputs "
            f"(no time-step unrolling). Sequential semantics are NOT preserved.",
            file=sys.stderr,
        )

    memo = {}
    all_clauses = []
    for out_lit in outputs:
        clauses = expand(out_lit, and_gates, memo)
        all_clauses.extend(clauses)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for c in all_clauses:
        if c not in seen:
            seen.add(c)
            deduped.append(c)

    print(
        f"AAG: M={M} I={I} L={L} O={O} A={A}  =>  DIMACS: vars={M} clauses={len(deduped)}",
        file=sys.stderr,
    )

    lines = [f"p cnf {M} {len(deduped)}"]
    for clause in deduped:
        if not clause:
            lines.append("0")  # empty clause (UNSAT witness)
        else:
            lines.append(" ".join(map(str, sorted(clause, key=abs))) + " 0")
    content = "\n".join(lines) + "\n"

    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
    else:
        sys.stdout.write(content)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <input.aag> [output.cnf]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    aag_to_dimacs(input_path, output_path)


if __name__ == "__main__":
    main()
