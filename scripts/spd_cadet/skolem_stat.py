#!/usr/bin/env python3

import argparse
import csv
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


def run_cmd(cmd: List[str], timeout: Optional[int] = None) -> Tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


def lit_base(lit: int) -> int:
    """
    AIGER literal encoding:
      even literal: positive signal
      odd literal: negated signal
    The underlying node literal is lit with the low bit cleared.
    """
    return lit & ~1


def parse_aag_metrics(aag_path: Path) -> Dict[str, object]:
    """
    Parse ASCII AIGER .aag and compute:
      - inputs
      - outputs
      - AND nodes
      - AIG levels
      - per-output cone size
      - per-output support size
    """
    with aag_path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError("empty AAG file")

    header = lines[0].split()
    if len(header) < 6 or header[0] != "aag":
        raise ValueError(f"not an ASCII AIGER file: header={lines[0]!r}")

    _, M, I, L, O, A = header[:6]
    M, I, L, O, A = map(int, (M, I, L, O, A))

    idx = 1

    input_lits = []
    for _ in range(I):
        input_lits.append(int(lines[idx].split()[0]))
        idx += 1

    input_set = set(input_lits)

    # Latches are rare for Skolem functions, but skip them if present.
    latch_lines = []
    for _ in range(L):
        latch_lines.append(lines[idx])
        idx += 1

    output_lits = []
    for _ in range(O):
        output_lits.append(int(lines[idx].split()[0]))
        idx += 1

    and_defs: Dict[int, Tuple[int, int]] = {}
    for _ in range(A):
        parts = lines[idx].split()
        if len(parts) < 3:
            raise ValueError(f"bad AND line: {lines[idx]!r}")
        lhs, rhs0, rhs1 = map(int, parts[:3])
        and_defs[lhs] = (rhs0, rhs1)
        idx += 1

    level_cache: Dict[int, int] = {}

    def level(lit: int) -> int:
        b = lit_base(lit)
        if b in level_cache:
            return level_cache[b]

        # Constants and primary inputs have level 0.
        if b == 0 or b in input_set:
            level_cache[b] = 0
            return 0

        if b not in and_defs:
            # Could be latch or an unusual node. Treat as leaf.
            level_cache[b] = 0
            return 0

        r0, r1 = and_defs[b]
        val = 1 + max(level(r0), level(r1))
        level_cache[b] = val
        return val

    def collect_cone_and_support(lit: int) -> Tuple[Set[int], Set[int]]:
        visited_and: Set[int] = set()
        support: Set[int] = set()

        def dfs(x: int) -> None:
            b = lit_base(x)

            if b == 0:
                return

            if b in input_set:
                support.add(b)
                return

            if b not in and_defs:
                return

            if b in visited_and:
                return

            visited_and.add(b)
            r0, r1 = and_defs[b]
            dfs(r0)
            dfs(r1)

        dfs(lit)
        return visited_and, support

    output_levels = []
    output_cone_sizes = []
    output_support_sizes = []

    for out_lit in output_lits:
        cone, supp = collect_cone_and_support(out_lit)
        output_levels.append(level(out_lit))
        output_cone_sizes.append(len(cone))
        output_support_sizes.append(len(supp))

    def avg(xs: List[int]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    return {
        "aig_max_var": M,
        "num_inputs": I,
        "num_latches": L,
        "num_outputs": O,
        "num_and_nodes": A,
        "aig_levels": max(output_levels) if output_levels else 0,
        "max_output_cone_and_nodes": max(output_cone_sizes) if output_cone_sizes else 0,
        "avg_output_cone_and_nodes": avg(output_cone_sizes),
        "sum_output_cone_and_nodes": sum(output_cone_sizes),
        "max_output_support_size": max(output_support_sizes) if output_support_sizes else 0,
        "avg_output_support_size": avg(output_support_sizes),
    }


def convert_one(
    verilog_path: Path,
    out_dir: Path,
    timeout: Optional[int],
) -> Dict[str, object]:
    stem = verilog_path.name
    if stem.endswith(".skolem.v"):
        base_name = stem[: -len(".skolem.v")]
    else:
        base_name = verilog_path.stem

    aig_path = out_dir / f"{base_name}.aig"

    row: Dict[str, object] = {
        "name": base_name,
        "input_verilog": str(verilog_path),
        "output_aig": str(aig_path),
        "status": "unknown",
        "yosys_seconds": "",
        "verilog_bytes": "",
        "aig_bytes": "",
        "error": "",
    }

    try:
        row["verilog_bytes"] = verilog_path.stat().st_size

        with tempfile.TemporaryDirectory() as td:
            tmp_aag = Path(td) / f"{base_name}.aag"

            yosys_script = f"""
read_verilog {str(verilog_path)}
hierarchy -auto-top
proc
opt
flatten
opt
techmap
opt
aigmap
opt
write_aiger {str(aig_path)}
write_aiger -ascii {str(tmp_aag)}
"""

            t0 = time.time()
            code, stdout, stderr = run_cmd(
                ["yosys", "-q", "-p", yosys_script],
                timeout=timeout,
            )
            t1 = time.time()
            row["yosys_seconds"] = round(t1 - t0, 4)

            if code != 0:
                row["status"] = "yosys_failed"
                row["error"] = stderr[-2000:] if stderr else stdout[-2000:]
                return row

            if not aig_path.exists():
                row["status"] = "aig_missing"
                row["error"] = "Yosys finished but did not create .aig"
                return row

            if not tmp_aag.exists():
                row["status"] = "aag_missing"
                row["error"] = "Yosys finished but did not create temporary .aag"
                return row

            metrics = parse_aag_metrics(tmp_aag)
            row.update(metrics)
            row["aig_bytes"] = aig_path.stat().st_size
            row["status"] = "ok"

    except subprocess.TimeoutExpired:
        row["status"] = "timeout"
        row["error"] = f"timeout after {timeout} seconds"
    except Exception as e:
        row["status"] = "failed"
        row["error"] = repr(e)

    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-convert Manthan .skolem.v files to .aig and collect AIG metrics."
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing .skolem.v files")
    parser.add_argument("output_dir", type=Path, help="Directory to write .aig files")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("skolem_metrics.csv"),
        help="CSV output path. Default: ./skolem_metrics.csv",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout per file in seconds. Default: 300",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search input_dir recursively",
    )
    args = parser.parse_args()

    if shutil.which("yosys") is None:
        raise SystemExit("Error: yosys not found in PATH")

    input_dir = args.input_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.recursive:
        files = sorted(input_dir.rglob("*.skolem.v"))
    else:
        files = sorted(input_dir.glob("*.skolem.v"))

    rows = []
    for path in files:
        print(f"[convert] {path}")
        row = convert_one(path, output_dir, timeout=args.timeout)
        rows.append(row)
        print(f"  -> {row['status']}")

    fieldnames = [
        "name",
        "status",
        "input_verilog",
        "output_aig",
        "verilog_bytes",
        "aig_bytes",
        "yosys_seconds",
        "num_inputs",
        "num_latches",
        "num_outputs",
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

    with args.csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\nDone.")
    print(f"AIG output dir: {output_dir}")
    print(f"CSV metrics: {args.csv}")


if __name__ == "__main__":
    main()