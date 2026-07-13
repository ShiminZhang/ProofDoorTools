#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

from utils.formula_variants import (
    BOUNDARY_MODE_PHYSICAL,
    SCRANFILIZE_PROFILES,
    generate_scranfilized_cnf,
    make_formula_variant,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a scranfilize CNF variant and restore physical c iter boundaries."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--profile", choices=sorted(SCRANFILIZE_PROFILES), required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--boundary_mode", choices=[BOUNDARY_MODE_PHYSICAL], default=BOUNDARY_MODE_PHYSICAL)
    parser.add_argument("--scranfilize_binary", default=None)
    parser.add_argument("--force", action="store_true", default=False)
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent.parent)
    variant = make_formula_variant(
        scranfilize_profile=args.profile,
        scranfilize_seed=args.seed,
        boundary_mode=args.boundary_mode,
    )
    out = generate_scranfilized_cnf(
        args.name,
        args.K,
        variant,
        scranfilize_binary=args.scranfilize_binary,
    )
    print(out)


if __name__ == "__main__":
    main()
