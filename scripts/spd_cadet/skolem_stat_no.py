#!/usr/bin/env python3

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional


Token = str


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    return text


def normalize_identifier(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        # Escaped Verilog identifier: \123 or \foo
        return name[1:].strip()
    return name


def split_decl_names(s: str) -> List[str]:
    s = s.strip()
    s = re.sub(r"\[[^\]]+\]", "", s)
    parts = []
    for x in s.split(","):
        x = x.strip()
        x = x.rstrip(";")
        if not x:
            continue
        parts.append(normalize_identifier(x))
    return parts


def parse_declarations(text: str, kind: str) -> List[str]:
    """
    Parse input/output/wire declarations.
    Handles forms like:
      input a, b, c;
      output y;
      wire t1, t2;
    """
    names = []
    pattern = rf"\b{kind}\b\s+([^;]+);"
    for m in re.finditer(pattern, text, flags=re.S):
        names.extend(split_decl_names(m.group(1)))
    return names


def parse_assigns(text: str) -> Dict[str, str]:
    assigns = {}
    for m in re.finditer(r"\bassign\b\s+(.+?)\s*=\s*(.+?)\s*;", text, flags=re.S):
        lhs = normalize_identifier(m.group(1))
        rhs = m.group(2).strip()
        assigns[lhs] = rhs
    return assigns


def tokenize_expr(expr: str) -> List[Token]:
    """
    Tokenize a small Verilog expression subset.
    """
    tokens = []
    i = 0
    while i < len(expr):
        c = expr[i]

        if c.isspace():
            i += 1
            continue

        if c in "()~&|^":
            tokens.append(c)
            i += 1
            continue

        # Verilog constants
        m = re.match(r"[01]'b[01]", expr[i:], flags=re.I)
        if m:
            tokens.append(m.group(0).lower())
            i += len(m.group(0))
            continue

        # Plain number as identifier or constant.
        m = re.match(r"[A-Za-z_.$][A-Za-z0-9_.$]*|[0-9]+", expr[i:])
        if m:
            tokens.append(normalize_identifier(m.group(0)))
            i += len(m.group(0))
            continue

        # Escaped identifier: \foo ends at whitespace or operator.
        if c == "\\":
            j = i + 1
            while j < len(expr) and not expr[j].isspace() and expr[j] not in "()~&|^":
                j += 1
            tokens.append(expr[i + 1:j])
            i = j
            continue

        raise ValueError(f"unsupported character in expression: {c!r}, expr={expr!r}")

    return tokens


class ExprParser:
    """
    Recursive-descent parser with precedence:
      ~ highest
      & next
      ^ next
      | lowest
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> Optional[Token]:
        if self.i >= len(self.tokens):
            return None
        return self.tokens[self.i]

    def take(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.parse_or()
        if self.peek() is not None:
            raise ValueError(f"extra token: {self.peek()}")
        return node

    def parse_or(self):
        node = self.parse_xor()
        while self.peek() == "|":
            self.take()
            rhs = self.parse_xor()
            node = ("or", node, rhs)
        return node

    def parse_xor(self):
        node = self.parse_and()
        while self.peek() == "^":
            self.take()
            rhs = self.parse_and()
            node = ("xor", node, rhs)
        return node

    def parse_and(self):
        node = self.parse_unary()
        while self.peek() == "&":
            self.take()
            rhs = self.parse_unary()
            node = ("and", node, rhs)
        return node

    def parse_unary(self):
        tok = self.peek()

        if tok == "~":
            self.take()
            return ("not", self.parse_unary())

        if tok == "(":
            self.take()
            node = self.parse_or()
            if self.peek() != ")":
                raise ValueError("missing closing parenthesis")
            self.take()
            return node

        if tok is None:
            raise ValueError("unexpected end of expression")

        self.take()

        if tok in ("1'b0", "0"):
            return ("const", 0)
        if tok in ("1'b1", "1"):
            return ("const", 1)

        return ("var", normalize_identifier(tok))


class AIGBuilder:
    """
    Build an AIG and assign AIGER literals.

    AIGER literal:
      0 = false
      1 = true
      even 2*v = signal v
      odd  2*v+1 = negated signal v
    """

    def __init__(self):
        self.var_to_lit: Dict[str, int] = {}
        self.inputs: List[str] = []
        self.and_defs: List[Tuple[int, int, int]] = []
        self.and_cache: Dict[Tuple[int, int], int] = {}
        self.next_var = 1

    def add_input(self, name: str) -> int:
        name = normalize_identifier(name)
        if name in self.var_to_lit:
            return self.var_to_lit[name]
        lit = 2 * self.next_var
        self.next_var += 1
        self.var_to_lit[name] = lit
        self.inputs.append(name)
        return lit

    def new_and(self, a: int, b: int) -> int:
        # Canonicalize commutative AND.
        if a > b:
            a, b = b, a

        # Boolean simplifications.
        if a == 0 or b == 0:
            return 0
        if a == 1:
            return b
        if b == 1:
            return a
        if a == b:
            return a
        if a == (b ^ 1):
            return 0

        key = (a, b)
        if key in self.and_cache:
            return self.and_cache[key]

        lhs = 2 * self.next_var
        self.next_var += 1
        self.and_cache[key] = lhs
        self.and_defs.append((lhs, a, b))
        return lhs

    def aig_not(self, a: int) -> int:
        return a ^ 1

    def aig_and(self, a: int, b: int) -> int:
        return self.new_and(a, b)

    def aig_or(self, a: int, b: int) -> int:
        # a | b = ~(~a & ~b)
        return self.aig_not(self.new_and(self.aig_not(a), self.aig_not(b)))

    def aig_xor(self, a: int, b: int) -> int:
        # a ^ b = (a & ~b) | (~a & b)
        t1 = self.new_and(a, self.aig_not(b))
        t2 = self.new_and(self.aig_not(a), b)
        return self.aig_or(t1, t2)

    def compile_expr(self, ast, env: Dict[str, int]) -> int:
        kind = ast[0]

        if kind == "const":
            return 0 if ast[1] == 0 else 1

        if kind == "var":
            name = normalize_identifier(ast[1])
            if name not in env:
                # Treat undeclared symbol as input-like leaf.
                env[name] = self.add_input(name)
            return env[name]

        if kind == "not":
            return self.aig_not(self.compile_expr(ast[1], env))

        if kind == "and":
            return self.aig_and(
                self.compile_expr(ast[1], env),
                self.compile_expr(ast[2], env),
            )

        if kind == "or":
            return self.aig_or(
                self.compile_expr(ast[1], env),
                self.compile_expr(ast[2], env),
            )

        if kind == "xor":
            return self.aig_xor(
                self.compile_expr(ast[1], env),
                self.compile_expr(ast[2], env),
            )

        raise ValueError(f"unknown AST node: {ast}")

    def max_var_index(self) -> int:
        return self.next_var - 1


def parse_expr(expr: str):
    tokens = tokenize_expr(expr)
    return ExprParser(tokens).parse()


def topo_compile_signal(
    name: str,
    assigns: Dict[str, str],
    builder: AIGBuilder,
    env: Dict[str, int],
    visiting: Set[str],
    compiled: Set[str],
) -> int:
    name = normalize_identifier(name)

    if name in compiled:
        return env[name]

    if name in env and name not in assigns:
        compiled.add(name)
        return env[name]

    if name in visiting:
        raise ValueError(f"cyclic assignment involving {name}")

    if name not in assigns:
        if name not in env:
            env[name] = builder.add_input(name)
        compiled.add(name)
        return env[name]

    visiting.add(name)

    # Compile dependencies first by recursively intercepting variables through env.
    ast = parse_expr(assigns[name])

    def compile_ast_with_deps(ast_node) -> int:
        kind = ast_node[0]

        if kind == "const":
            return 0 if ast_node[1] == 0 else 1

        if kind == "var":
            v = normalize_identifier(ast_node[1])
            if v in assigns and v not in compiled:
                return topo_compile_signal(v, assigns, builder, env, visiting, compiled)
            if v not in env:
                env[v] = builder.add_input(v)
            return env[v]

        if kind == "not":
            return builder.aig_not(compile_ast_with_deps(ast_node[1]))

        if kind == "and":
            return builder.aig_and(
                compile_ast_with_deps(ast_node[1]),
                compile_ast_with_deps(ast_node[2]),
            )

        if kind == "or":
            return builder.aig_or(
                compile_ast_with_deps(ast_node[1]),
                compile_ast_with_deps(ast_node[2]),
            )

        if kind == "xor":
            return builder.aig_xor(
                compile_ast_with_deps(ast_node[1]),
                compile_ast_with_deps(ast_node[2]),
            )

        raise ValueError(f"bad AST node: {ast_node}")

    lit = compile_ast_with_deps(ast)
    env[name] = lit
    visiting.remove(name)
    compiled.add(name)
    return lit


def write_aag(
    path: Path,
    builder: AIGBuilder,
    output_names: List[str],
    output_lits: List[int],
) -> None:
    I = len(builder.inputs)
    L = 0
    O = len(output_lits)
    A = len(builder.and_defs)
    M = builder.max_var_index()

    with path.open("w", encoding="utf-8") as f:
        f.write(f"aag {M} {I} {L} {O} {A}\n")

        for name in builder.inputs:
            f.write(f"{builder.var_to_lit[name]}\n")

        for lit in output_lits:
            f.write(f"{lit}\n")

        for lhs, rhs0, rhs1 in builder.and_defs:
            f.write(f"{lhs} {rhs0} {rhs1}\n")

        for i, name in enumerate(builder.inputs):
            f.write(f"i{i} {name}\n")

        for i, name in enumerate(output_names):
            f.write(f"o{i} {name}\n")

        f.write("c\n")
        f.write("Generated from Manthan .skolem.v by skolem_stat_no_yosys.py\n")


def compute_metrics(
    builder: AIGBuilder,
    output_lits: List[int],
) -> Dict[str, object]:
    input_lits = set(builder.var_to_lit[name] for name in builder.inputs)
    and_defs = {lhs: (a, b) for lhs, a, b in builder.and_defs}

    level_cache: Dict[int, int] = {}

    def base(lit: int) -> int:
        return lit & ~1

    def level(lit: int) -> int:
        b = base(lit)
        if b in level_cache:
            return level_cache[b]
        if b == 0 or b in input_lits:
            level_cache[b] = 0
            return 0
        if b not in and_defs:
            level_cache[b] = 0
            return 0
        a, c = and_defs[b]
        val = 1 + max(level(a), level(c))
        level_cache[b] = val
        return val

    def cone_and_support(lit: int) -> Tuple[Set[int], Set[int]]:
        seen_and: Set[int] = set()
        support: Set[int] = set()

        def dfs(x: int):
            b = base(x)
            if b == 0:
                return
            if b in input_lits:
                support.add(b)
                return
            if b not in and_defs:
                return
            if b in seen_and:
                return
            seen_and.add(b)
            a, c = and_defs[b]
            dfs(a)
            dfs(c)

        dfs(lit)
        return seen_and, support

    levels = [level(o) for o in output_lits]
    cones = []
    supports = []

    for o in output_lits:
        cone, supp = cone_and_support(o)
        cones.append(len(cone))
        supports.append(len(supp))

    def avg(xs: List[int]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    return {
        "num_inputs": len(builder.inputs),
        "num_outputs": len(output_lits),
        "num_and_nodes": len(builder.and_defs),
        "aig_levels": max(levels) if levels else 0,
        "max_output_cone_and_nodes": max(cones) if cones else 0,
        "avg_output_cone_and_nodes": avg(cones),
        "sum_output_cone_and_nodes": sum(cones),
        "max_output_support_size": max(supports) if supports else 0,
        "avg_output_support_size": avg(supports),
        "aig_max_var": builder.max_var_index(),
    }


def convert_one(verilog_path: Path, output_dir: Path) -> Dict[str, object]:
    if verilog_path.name.endswith(".skolem.v"):
        base = verilog_path.name[: -len(".skolem.v")]
    else:
        base = verilog_path.stem

    out_aag = output_dir / f"{base}.aag"
    out_aig = output_dir / f"{base}.aig"

    row: Dict[str, object] = {
        "name": base,
        "status": "unknown",
        "input_verilog": str(verilog_path),
        "output_aag": str(out_aag),
        "output_aig": str(out_aig),
        "verilog_bytes": "",
        "aag_bytes": "",
        "aig_bytes": "",
        "error": "",
    }

    try:
        text = verilog_path.read_text(encoding="utf-8", errors="ignore")
        row["verilog_bytes"] = verilog_path.stat().st_size

        text = strip_comments(text)

        inputs = parse_declarations(text, "input")
        outputs = parse_declarations(text, "output")
        wires = parse_declarations(text, "wire")
        assigns = parse_assigns(text)

        builder = AIGBuilder()
        env: Dict[str, int] = {}
        compiled: Set[str] = set()

        for x in inputs:
            env[x] = builder.add_input(x)
            compiled.add(x)

        output_lits = []
        for y in outputs:
            lit = topo_compile_signal(
                y,
                assigns,
                builder,
                env,
                visiting=set(),
                compiled=compiled,
            )
            output_lits.append(lit)

        write_aag(out_aag, builder, outputs, output_lits)

        # Same content, requested .aig extension.
        out_aig.write_text(out_aag.read_text(encoding="utf-8"), encoding="utf-8")

        metrics = compute_metrics(builder, output_lits)
        row.update(metrics)

        row["num_wires_declared"] = len(wires)
        row["num_assigns"] = len(assigns)
        row["aag_bytes"] = out_aag.stat().st_size
        row["aig_bytes"] = out_aig.stat().st_size
        row["status"] = "ok"

    except Exception as e:
        row["status"] = "failed"
        row["error"] = repr(e)

    return row


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Convert Manthan .skolem.v to AIGER without Yosys and collect metrics."
    )
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--csv", type=Path, default=Path("skolem_metrics.csv"))
    ap.add_argument("--recursive", action="store_true")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.recursive:
        files = sorted(args.input_dir.rglob("*.skolem.v"))
    else:
        files = sorted(args.input_dir.glob("*.skolem.v"))

    rows = []

    for f in files:
        print(f"[parse] {f}")
        row = convert_one(f, args.output_dir)
        rows.append(row)
        print(f"  -> {row['status']}")

    fieldnames = [
        "name",
        "status",
        "input_verilog",
        "output_aag",
        "output_aig",
        "verilog_bytes",
        "aag_bytes",
        "aig_bytes",
        "num_inputs",
        "num_outputs",
        "num_wires_declared",
        "num_assigns",
        "num_and_nodes",
        "aig_levels",
        "max_output_cone_and_nodes",
        "avg_output_cone_and_nodes",
        "sum_output_cone_and_nodes",
        "max_output_support_size",
        "avg_output_support_size",
        "aig_max_var",
        "error",
    ]

    with args.csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print()
    print(f"processed: {len(rows)}")
    print(f"csv: {args.csv}")
    print(f"output_dir: {args.output_dir}")


if __name__ == "__main__":
    main()