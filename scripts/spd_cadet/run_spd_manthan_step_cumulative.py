#!/usr/bin/env python3
"""
run_spd_manthan_step_cumulative.py

SLURM job body for one iteration of the cumulative-partitioned SPD-Manthan chain.

Similar to run_spd_manthan_step.py but uses cumulative partition:
    - For each iteration i, computes interpolant from A_0...A_i to A_{i+1}...A_K
    - No dependency on previous interpolants I_{i-1}
    - Each iteration is independent

Runs two steps in sequence for a single (name, K, i):
    1. compute_spd_skolem_cumulative  — build QDIMACS + run Manthan
    2. skolem_to_aig                  — substitute Skolem witnesses, produce AAG via ABC

Skip logic: each step checks whether its output file already exists and skips
if so, allowing interrupted jobs to be safely resubmitted. Use --force to
override and rerun from scratch.

Exit code 0 = all steps done (or already done).
Exit code 1 = failure — causes SLURM afterok to suppress downstream jobs.

Usage (called by manage_spd_manthan_computation_cumulative.py):
    python run_spd_manthan_step_cumulative.py --name cal4 --K 7 --i 0
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SKOLEM_DIR_TEMPLATE = "./ProofDoorBenchmark/skolem_spd_manthan_cumulative/{K}/"
AAG_DIR_TEMPLATE = "./ProofDoorBenchmark/interpolant_aig_manthan_cumulative/{K}/"


def _skolem_path(name, K, i):
    return os.path.join(SKOLEM_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.skolem.v")

def _aag_path(name, K, i):
    return os.path.join(AAG_DIR_TEMPLATE.format(K=K), f"{name}.{K}.{i}.aag")


def main():
    parser = argparse.ArgumentParser(
        description="SLURM job for one iteration of cumulative-partitioned SPD-Manthan"
    )
    parser.add_argument('--name', required=True)
    parser.add_argument('--K', type=int, required=True)
    parser.add_argument('--i', type=int, required=True)
    parser.add_argument('--force', action='store_true',
                        help='Remove existing outputs and rerun all steps')
    args = parser.parse_args()

    name, K, i = args.name, args.K, args.i

    print(f"{'='*60}")
    print(f"SPD-Manthan (CUMULATIVE)  name={name}  K={K}  i={i}" + (" [forced]" if args.force else ""))
    print(f"{'='*60}")

    if args.force:
        for path in [_skolem_path(name, K, i), _aag_path(name, K, i)]:
            if os.path.exists(path):
                print(f"[FORCE] removing {path}")
                os.remove(path)

    # --- Step 1: compute_spd_skolem_cumulative ---
    skolem_out = _skolem_path(name, K, i)
    if os.path.exists(skolem_out):
        print(f"\n[1/3] SKIP compute_spd_skolem_cumulative — {skolem_out} exists")
    else:
        print(f"\n[1/3] compute_spd_skolem_cumulative")
        from spd_cadet.compute_spd_skolem_cumulative import compute_spd_skolem_cumulative
        compute_spd_skolem_cumulative(name, K, i, backend='manthan')

    # --- Step 2: skolem_to_aig ---
    aag_out = _aag_path(name, K, i)
    if os.path.exists(aag_out):
        print(f"\n[2/3] SKIP skolem_to_aig — {aag_out} exists")
    else:
        print(f"\n[2/3] skolem_to_aig")
        from spd_cadet.skolem_to_aig import skolem_to_aig
        _skolem_to_aig_cumulative(name, K, i)

    print(f"\n{'='*60}")
    print(f"i={i} complete (AAG only)")


def _skolem_to_aig_cumulative(name, K, i):
    """
    Wrapper around skolem_to_aig that uses cumulative directory paths.
    """
    from spd_cadet.skolem_to_aig import skolem_to_aig

    new_skolem_dir = "./ProofDoorBenchmark/skolem_spd_manthan_cumulative/{K}/"
    new_aag_dir = "./ProofDoorBenchmark/interpolant_aig_manthan_cumulative/{K}/"

    import spd_cadet.skolem_to_aig as sa_module

    orig_sa_skolem_template = getattr(sa_module, 'SKOLEM_DIR_TEMPLATE', None)
    orig_sa_aag_template = getattr(sa_module, 'AAG_DIR_TEMPLATE', None)

    sa_module.SKOLEM_DIR_TEMPLATE = new_skolem_dir
    sa_module.AAG_DIR_TEMPLATE = new_aag_dir

    try:
        skolem_to_aig(name, K, i)
    finally:
        if orig_sa_skolem_template:
            sa_module.SKOLEM_DIR_TEMPLATE = orig_sa_skolem_template
        if orig_sa_aag_template:
            sa_module.AAG_DIR_TEMPLATE = orig_sa_aag_template


if __name__ == '__main__':
    main()
