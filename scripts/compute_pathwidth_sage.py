#!/usr/bin/env sage -python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sage.all import Graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute pathwidth of a CNF incidence graph with SageMath."
    )
    parser.add_argument("input", nargs="?", default="-", help="DIMACS CNF file or '-' for stdin.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--show-order", action="store_true", help="Print returned order if any.")
    parser.add_argument(
        "--mode",
        choices=("block", "prefix"),
        default="block",
        help="Iteration mode: block=each iter block only, prefix=from start to current iter.",
    )
    parser.add_argument(
        "--no-per-iteration",
        action="store_true",
        help="Disable per-iteration output and compute only once on whole CNF.",
    )
    return parser.parse_args()


def read_text(path_str: str) -> str:
    if path_str == "-":
        return sys.stdin.read()
    return Path(path_str).read_text(encoding="utf-8")


def parse_dimacs_cnf(text: str):
    num_vars = None
    clauses = []
    iter_starts = [0]

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("c"):
            # Keep iteration boundaries from lines like: "c iter 1"
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "iter":
                cur = len(clauses)
                if cur != iter_starts[-1]:
                    iter_starts.append(cur)
            continue
        if line.startswith("p"):
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf":
                raise ValueError(f"Invalid DIMACS header: {raw_line!r}")
            num_vars = int(parts[2])
            continue

        lits = [int(x) for x in line.split()]
        if not lits:
            continue
        if lits[-1] != 0:
            raise ValueError(f"Clause line must end with 0: {raw_line!r}")
        clause = [lit for lit in lits[:-1] if lit != 0]
        clauses.append(clause)

    if num_vars is None:
        raise ValueError("Missing DIMACS header line: p cnf <num_vars> <num_clauses>")

    return num_vars, clauses, iter_starts


def build_incidence_graph(num_vars: int, clauses) -> Graph:
    g = Graph()

    var_vertices = [f"v{i}" for i in range(1, num_vars + 1)]
    clause_vertices = [f"c{i}" for i in range(1, len(clauses) + 1)]
    g.add_vertices(var_vertices)
    g.add_vertices(clause_vertices)

    for clause_idx, clause in enumerate(clauses, start=1):
        c = f"c{clause_idx}"
        seen_vars = set()
        for lit in clause:
            v = abs(lit)
            if not (1 <= v <= num_vars):
                raise ValueError(f"Literal out of range: {lit}")
            if v in seen_vars:
                continue
            seen_vars.add(v)
            g.add_edge(f"v{v}", c)

    return g


def vertex_separation_width(graph: Graph, order) -> int:
    order = list(order)
    pos = {v: i for i, v in enumerate(order)}
    best = 0

    for cut in range(len(order) - 1):
        left = set(order[: cut + 1])
        width = 0
        for u in left:
            if any(pos[w] > cut for w in graph.neighbors(u)):
                width += 1
        best = max(best, width)

    return best


def normalize_order(candidate):
    if candidate is None:
        return None
    if isinstance(candidate, (list, tuple)):
        if candidate and isinstance(candidate[0], (list, tuple)):
            seen = set()
            order = []
            for bag in candidate:
                for v in bag:
                    if v not in seen:
                        seen.add(v)
                        order.append(v)
            return order
        return list(candidate)
    return None


def extract_width_and_order(result):
    if isinstance(result, tuple):
        width = int(result[0])
        order = None
        for item in result[1:]:
            order = normalize_order(item)
            if order is not None:
                break
        return width, order
    return int(result), None


def compute_pathwidth(graph: Graph):
    attempts = (
        ("pathwidth(certificate=True)", lambda: graph.pathwidth(certificate=True)),
        ("pathwidth()", lambda: graph.pathwidth()),
        ("vertex_separation(certificate=True)", lambda: graph.vertex_separation(certificate=True)),
        ("vertex_separation()", lambda: graph.vertex_separation()),
    )

    errors = []
    for method, fn in attempts:
        try:
            width, order = extract_width_and_order(fn())
            return width, order, method
        except Exception as exc:
            errors.append(f"{method}: {exc}")

    raise RuntimeError("No supported Sage API succeeded:\n" + "\n".join(errors))


def iter_clause_ranges(num_clauses: int, iter_starts):
    starts = sorted(set(iter_starts or [0]))
    if not starts or starts[0] != 0:
        starts = [0] + starts
    starts = [s for s in starts if 0 <= s <= num_clauses]
    if not starts:
        starts = [0]

    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else num_clauses
        if start > end:
            continue
        yield idx, start, end


def evaluate_one_graph(graph: Graph):
    width, order, method = compute_pathwidth(graph)
    verified = None
    if order is not None and len(order) == graph.num_verts():
        verified = vertex_separation_width(graph, order)
        width = max(width, verified)
    return int(width), order, method, verified


def main() -> int:
    args = parse_args()
    text = read_text(args.input)
    num_vars, clauses, iter_starts = parse_dimacs_cnf(text)

    per_iteration = []
    if args.no_per_iteration:
        graph = build_incidence_graph(num_vars, clauses)
        width, order, method, verified = evaluate_one_graph(graph)
        per_iteration.append(
            {
                "iter": 0,
                "start_clause_idx": 0,
                "end_clause_idx": len(clauses),
                "num_clauses": len(clauses),
                "num_vertices": int(graph.num_verts()),
                "num_edges": int(graph.num_edges()),
                "pathwidth": int(width),
                "method": method,
                "verified_vertex_separation_width": int(verified) if verified is not None else None,
                "order": list(order) if (args.show_order and order is not None) else None,
            }
        )
    else:
        for iter_idx, start, end in iter_clause_ranges(len(clauses), iter_starts):
            selected_clauses = clauses[start:end] if args.mode == "block" else clauses[:end]
            graph = build_incidence_graph(num_vars, selected_clauses)
            width, order, method, verified = evaluate_one_graph(graph)
            per_iteration.append(
                {
                    "iter": int(iter_idx),
                    "start_clause_idx": int(start),
                    "end_clause_idx": int(end),
                    "num_clauses": int(len(selected_clauses)),
                    "num_vertices": int(graph.num_verts()),
                    "num_edges": int(graph.num_edges()),
                    "pathwidth": int(width),
                    "method": method,
                    "verified_vertex_separation_width": int(verified) if verified is not None else None,
                    "order": list(order) if (args.show_order and order is not None) else None,
                }
            )

    max_pathwidth = max((row["pathwidth"] for row in per_iteration), default=0)

    if args.json:
        payload = {
            "num_vars": num_vars,
            "num_clauses": len(clauses),
            "mode": args.mode,
            "per_iteration": not args.no_per_iteration,
            "num_iterations": len(per_iteration),
            "pathwidth": int(max_pathwidth),
            "per_iteration_results": per_iteration,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    for row in per_iteration:
        print(
            f"iter {row['iter']}: pathwidth={row['pathwidth']}, "
            f"num_clauses={row['num_clauses']}, range=[{row['start_clause_idx']},{row['end_clause_idx']})"
        )
        if args.show_order and row["order"] is not None:
            print("order:", " ".join(map(str, row["order"])))
        print(f"method: {row['method']}", file=sys.stderr)
        if row["verified_vertex_separation_width"] is not None:
            print(
                f"verified_vertex_separation_width: {row['verified_vertex_separation_width']}",
                file=sys.stderr,
            )
    print(f"max_pathwidth: {max_pathwidth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
