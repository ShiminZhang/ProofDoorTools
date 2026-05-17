#!/usr/bin/env python3
"""
run_spd_manthan_step.py — SLURM job body for one iteration of the SPD-Manthan chain.

Runs three steps in sequence for a single (name, K, i):
  1. compute_spd_skolem  — build QDIMACS + run Manthan
  2. skolem_to_aig       — substitute Skolem witnesses, produce AAG via ABC
  3. verify_skolem_interpolant — expand AAG→CNF, verify, save interpolant CNF

Skip logic: each step checks whether its output file already exists and skips
if so, allowing interrupted jobs to be safely resubmitted.  Use --force to
override and rerun from scratch.

Exit code 0 = all steps done (or already done).
Exit code 1 = failure — causes SLURM afterok to suppress downstream jobs.

Usage (called by manage_spd_manthan_computation.py):
    python run_spd_manthan_step.py --name cal4 --K 7 --i 0
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SKOLEM_DIR_TEMPLATE     = "./ProofDoorBenchmark/skolem_spd_manthan/{K}/"
AAG_DIR_TEMPLATE        = "./ProofDoorBenchmark/interpolant_aig_manthan/{K}/"
INTERP_CNF_DIR_TEMPLATE = "./ProofDoorBenchmark/interp_cnf_spd_manthan/{K}/"


def _skolem_path(name, K, i):
    return os.path.join(SKOLEM_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.skolem.v")

def _aag_path(name, K, i):
    return os.path.join(AAG_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.aag")

def _interp_cnf_path(name, K, i):
    return os.path.join(INTERP_CNF_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.cnf")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name',  required=True)
    parser.add_argument('--K',     type=int, required=True)
    parser.add_argument('--i',     type=int, required=True)
    parser.add_argument('--force', action='store_true',
                        help='Remove existing outputs and rerun all steps')
    args = parser.parse_args()

    name, K, i = args.name, args.K, args.i

    print(f"{'='*60}")
    print(f"SPD-Manthan  name={name}  K={K}  i={i}" + (" [forced]" if args.force else ""))
    print(f"{'='*60}")

    if args.force:
        for path in [_skolem_path(name, K, i), _aag_path(name, K, i), _interp_cnf_path(name, K, i)]:
            if os.path.exists(path):
                print(f"[FORCE] removing {path}")
                os.remove(path)

    # --- Pre-check: ensure I_prev CNF exists for i > 0 ---
    if i > 0:
        prev_cnf = _interp_cnf_path(name, K, i - 1)
        if not os.path.exists(prev_cnf):
            prev_aag = _aag_path(name, K, i - 1)
            if not os.path.exists(prev_aag):
                print(f"ERROR: I_prev missing and AAG for i={i-1} not found — cannot recover")
                sys.exit(1)
            print(f"[RECOVER] I_prev CNF missing for i={i-1}, re-running verify to regenerate")
            from spd_cadet.verify_skolem_interpolant import verify_interpolant
            valid = verify_interpolant(name, K, i - 1)
            if not valid:
                print(f"ERROR: re-verification of i={i-1} failed — cannot proceed")
                sys.exit(1)

    # --- Step 1: compute_spd_skolem ---
    skolem_out = _skolem_path(name, K, i)
    if os.path.exists(skolem_out):
        print(f"\n[1/3] SKIP compute_spd_skolem — {skolem_out} exists")
    else:
        print(f"\n[1/3] compute_spd_skolem")
        from spd_cadet.compute_spd_skolem import compute_spd_skolem
        compute_spd_skolem(name, K, i, backend='manthan')

    # --- Step 2: skolem_to_aig ---
    aag_out = _aag_path(name, K, i)
    if os.path.exists(aag_out):
        print(f"\n[2/3] SKIP skolem_to_aig — {aag_out} exists")
    else:
        print(f"\n[2/3] skolem_to_aig")
        from spd_cadet.skolem_to_aig import skolem_to_aig
        skolem_to_aig(name, K, i)

    # --- Step 3: verify_skolem_interpolant ---
    interp_out = _interp_cnf_path(name, K, i)
    if os.path.exists(interp_out):
        print(f"\n[3/3] SKIP verify_skolem_interpolant — {interp_out} exists")
    else:
        print(f"\n[3/3] verify_skolem_interpolant")
        from spd_cadet.verify_skolem_interpolant import verify_interpolant
        valid = verify_interpolant(name, K, i)
        if not valid:
            print(f"\nERROR: interpolant at i={i} is invalid — aborting chain")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"i={i} complete")


if __name__ == '__main__':
    main()
