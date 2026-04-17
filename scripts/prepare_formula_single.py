#!/usr/bin/env python3
"""
Single-instance worker for --prepare_formula pipeline:
  - Generate CNF formulas for K=2..20
  - Run CaDiCaL with --plain, proof to get_DRAT(name, K), timeout 1600s per K
  - On first timeout, stop solving and write info JSON at get_CNF_info(name)

Expects CWD = repo root. Invoked by pipeline_scheduler as:
  python scripts/prepare_formula_single.py --name <instance_name>
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Run from repo root when invoked via sbatch; ensure scripts/ is on path so "utils" resolves
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
os.chdir(REPO_ROOT)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils.paths import get_CNF_dir, get_DRAT, get_CNF_info
from utils.utils import generate_cnf
from utils.bits import get_bits_from_cnf

CADICAL_BINARY = "./solvers/cadical"
SOLVE_TIMEOUT_SEC = 1600
K_MIN, K_MAX = 2, 20  # inclusive


def parse_cnf_header(cnf_path: str) -> tuple:
    """Return (n_vars, n_clauses) from 'p cnf <n> <m>' or (None, None)."""
    if not os.path.exists(cnf_path):
        return None, None
    with open(cnf_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.startswith("p cnf"):
                parts = line.split()
                if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
                    return int(parts[2]), int(parts[3])
    return None, None


def parse_cadical_solve_time(log_path: str):
    """Parse solve time (seconds) from CaDiCaL log. Returns float or None.

    Notes:
    - CaDiCaL typically reports timing as:
        'total process time since initialization:  <t> seconds'
      and exits with code 10 (SAT) or 20 (UNSAT).
    """
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return None
    try:
        # Prefer total process time line (present in CaDiCaL 2.x logs).
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("c total process time since initialization:"):
                    # Example:
                    # c total process time since initialization:         0.01    seconds
                    parts = line.split()
                    # Find the token right before 'seconds'
                    for i in range(len(parts) - 1):
                        if parts[i + 1] == "seconds":
                            return float(parts[i])
                if line.startswith("c total real time since initialization:"):
                    parts = line.split()
                    for i in range(len(parts) - 1):
                        if parts[i + 1] == "seconds":
                            return float(parts[i])
    except Exception:
        pass
    return None


def cadical_log_is_finished(log_path: str) -> bool:
    """Return True if the log indicates SAT/UNSAT was reached."""
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return False
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                # CaDiCaL prints one of these result lines.
                if line == "s SATISFIABLE" or line == "s UNSATISFIABLE":
                    return True
                # Some logs end with 'c exit 10/20'.
                if line.endswith("exit 10") or line.endswith("exit 20"):
                    return True
    except Exception:
        return False
    return False


def count_drat_add_clauses(drat_path: str) -> int:
    """Count ADD (non-deletion) clause lines in DRAT file."""
    if not os.path.exists(drat_path) or os.path.getsize(drat_path) == 0:
        return -1
    count = 0
    with open(drat_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c") or line.startswith("d"):
                continue
            count += 1
    return count


def run_cadical_with_timeout(cnf_path: str, drat_path: str, log_path: str, timeout_sec: int) -> bool:
    """Run CaDiCaL; return True if finished within timeout, False if timeout/kill."""
    cmd = [CADICAL_BINARY, "--plain", "--no-binary", cnf_path, drat_path]
    try:
        with open(log_path, "w") as logf:
            ret = subprocess.run(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                cwd=REPO_ROOT,
                timeout=timeout_sec,
            )
        # CaDiCaL (like many SAT solvers) uses exit codes:
        # - 10: SAT
        # - 20: UNSAT
        # 0 usually indicates "UNKNOWN"/error in this context.
        return ret.returncode in (10, 20)
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Prepare formula and solve for one instance (K=2..20).")
    parser.add_argument("--name", type=str, required=True, help="Instance name (e.g. 6s329rb19).")
    args = parser.parse_args()
    name = args.name.strip()
    if not name:
        sys.exit(1)

    k_list = list(range(K_MIN, K_MAX + 1))
    results = []

    # Solve sequentially; on first timeout stop and mark rest as timeout
    timed_out = False
    for k in k_list:
        cnf_path = os.path.join(get_CNF_dir(k), f"{name}.{k}.cnf")
        drat_path = get_DRAT(name, k)
        log_path = f"{cnf_path}.cadicalplain.log"

        n_vars, n_clauses = parse_cnf_header(cnf_path)
        m = n_clauses if n_clauses is not None else -1
        n = n_vars if n_vars is not None else -1
        formula_bits = -1

        if timed_out:
            results.append({"K": k, "m": m, "n": n, "formula_bits": formula_bits, "proofsize": -1, "time": -1})
            continue

        # 1) Generate CNF only if missing/empty.
        if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
            generate_cnf(f"{name}.{k}.cnf")
            # Refresh header after generation attempt.
            n_vars, n_clauses = parse_cnf_header(cnf_path)
            m = n_clauses if n_clauses is not None else -1
            n = n_vars if n_vars is not None else -1

        if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
            results.append({"K": k, "m": m, "n": n, "formula_bits": formula_bits, "proofsize": -1, "time": -1})
            timed_out = True
            continue

        # Compute formula bits from DIMACS CNF (reused if CNF already exists).
        try:
            formula_bits = int(get_bits_from_cnf(cnf_path))
        except Exception:
            formula_bits = -1

        # 2) If we already have both log and proof for this instance/K, reuse them.
        # This avoids re-solving when the job is re-run or resumed.
        log_finished = cadical_log_is_finished(log_path)
        drat_ok = os.path.exists(drat_path) and os.path.getsize(drat_path) > 0
        if log_finished and drat_ok:
            solve_time = parse_cadical_solve_time(log_path)
            time_val = float(solve_time) if solve_time is not None else -1
            proofsize = count_drat_add_clauses(drat_path)
            results.append({"K": k, "m": m, "n": n, "formula_bits": formula_bits, "proofsize": proofsize, "time": time_val})
            continue

        ok = run_cadical_with_timeout(cnf_path, drat_path, log_path, SOLVE_TIMEOUT_SEC)
        if not ok:
            timed_out = True
            results.append({"K": k, "m": m, "n": n, "formula_bits": formula_bits, "proofsize": -1, "time": -1})
            continue

        solve_time = parse_cadical_solve_time(log_path)
        time_val = float(solve_time) if solve_time is not None else -1
        proofsize = count_drat_add_clauses(drat_path)
        results.append({"K": k, "m": m, "n": n, "formula_bits": formula_bits, "proofsize": proofsize, "time": time_val})

    # 3) Write info JSON
    info_path = get_CNF_info(name)
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump({"name": name, "results": results}, f, indent=2)
    print(f"Wrote {info_path}")


if __name__ == "__main__":
    main()
