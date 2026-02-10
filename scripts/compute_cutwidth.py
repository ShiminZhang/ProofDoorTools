#!/usr/bin/env python3
import argparse
import sys
from typing import Iterable, List, Tuple


def _parse_dimacs_lines(lines: Iterable[str]) -> Tuple[int, List[List[int]]]:
    num_vars = None
    clauses: List[List[int]] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("c"):
            continue
        if line.startswith("p "):
            parts = line.split()
            if len(parts) >= 4 and parts[1] == "cnf":
                try:
                    num_vars = int(parts[2])
                except Exception:
                    num_vars = None
            continue
        # Clause line
        lits = []
        for tok in line.split():
            if tok == "0":
                break
            try:
                lits.append(int(tok))
            except Exception:
                raise ValueError(f"Invalid literal token: {tok}")
        if lits:
            clauses.append(lits)
    if num_vars is None:
        max_var = 0
        for clause in clauses:
            for lit in clause:
                max_var = max(max_var, abs(lit))
        num_vars = max_var
    return num_vars, clauses


def _build_edges(clauses: List[List[int]]) -> List[Tuple[int, int]]:
    edges = set()
    for clause in clauses:
        vars_in_clause = sorted({abs(lit) for lit in clause if lit != 0})
        m = len(vars_in_clause)
        if m <= 1:
            continue
        for i in range(m - 1):
            u = vars_in_clause[i]
            for j in range(i + 1, m):
                v = vars_in_clause[j]
                if u != v:
                    if u < v:
                        edges.add((u, v))
                    else:
                        edges.add((v, u))
    return list(edges)


def compute_cutwidth(num_vars: int, clauses: List[List[int]]) -> Tuple[int, int, List[int]]:
    edges = _build_edges(clauses)
    if num_vars <= 1 or not edges:
        return 0, 0, [0] * max(num_vars - 1, 0)

    # diff[i] affects cuts between i and i+1 (1-indexed variables)
    diff = [0] * (num_vars + 2)
    for u, v in edges:
        if u == v:
            continue
        if u > v:
            u, v = v, u
        # edge crosses all cuts i in [u, v-1]
        diff[u] += 1
        diff[v] -= 1

    cuts = [0] * (num_vars - 1)
    cur = 0
    max_val = -1
    max_idx = -1
    for i in range(1, num_vars):
        cur += diff[i]
        cuts[i - 1] = cur
        if cur > max_val:
            max_val = cur
            max_idx = i
    return max_val, max_idx, cuts


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute CNF cutwidth under index order (variable 1..n).")
    ap.add_argument("cnf", nargs="?", help="Path to DIMACS CNF file. If omitted, read from stdin.")
    ap.add_argument("--show-cuts", action="store_true", help="Print cut values for each cut i|i+1.")
    args = ap.parse_args()

    if args.cnf:
        with open(args.cnf, "r") as f:
            num_vars, clauses = _parse_dimacs_lines(f)
    else:
        num_vars, clauses = _parse_dimacs_lines(sys.stdin)

    cutwidth, max_cut_idx, cuts = compute_cutwidth(num_vars, clauses)
    print(f"cutwidth: {cutwidth}")
    if num_vars > 1:
        print(f"max_cut_index: {max_cut_idx} (between {max_cut_idx} and {max_cut_idx + 1})")
    else:
        print("max_cut_index: 0")

    if args.show_cuts:
        for i, val in enumerate(cuts, start=1):
            print(f"cut[{i}|{i+1}]: {val}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
