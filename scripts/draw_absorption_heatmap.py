"""
Standalone script to draw absorption heatmaps from cached JSON results.

Usage:
    python scripts/draw_absorption_heatmap.py --instance <name> --K 10 [--family <label>]
    python scripts/draw_absorption_heatmap.py --instance <name> --K 10 --interpolant_pddef 5 --reverse
"""
import argparse
import json
import os
import sys

import matplotlib.pyplot as plt

from AbsorptionExperiment import (
    get_absorption_result_path,
    include_formula_in_checking_flag_to_suffix,
    interpolant_pddef_to_suffix,
    permute_flag_to_suffix,
    permute_flag_to_title_suffix,
)
from utils.paths import get_absorption_experiments_dir, get_figures_dir


def load_percentage_grid(
    instance: str,
    K: int,
    K_effective: int,
    solver_suffix: str,
    include_formula_suffix: str,
    *,
    reverse: bool = False,
    interpolant_pddef: int = 1,
    permute: str = None,
    permute_index: int = 0,
) -> list[list[float]]:
    grid = []
    for interp_idx in range(K_effective):
        path = get_absorption_result_path(
            instance, K, interp_idx,
            solver_suffix, include_formula_suffix,
            reverse=reverse,
            interpolant_pddef=interpolant_pddef,
            permute=permute,
            permute_index=permute_index,
        )
        if not os.path.exists(path):
            raise FileNotFoundError(f"Absorption result not found: {path}")
        result = json.load(open(path))
        row = []
        for proof_idx in range(K_effective):
            if proof_idx < interp_idx:
                row.append(0.0)
                continue
            pass_count = total_count = 0
            for clause in result:
                for absorbed in result[clause].get(str(proof_idx), []):
                    total_count += 1
                    if absorbed:
                        pass_count += 1
            row.append(1.0 if total_count == 0 else pass_count / total_count)
        grid.append(row)
    return grid


def draw(grid: list[list[float]], title: str, K: int, interpolant_pddef: int) -> None:
    plt.figure(figsize=(10, 6))
    plt.xticks(range(len(grid[0])), [str(i) for i in range(len(grid[0]))])
    plt.imshow(grid, cmap="Blues", aspect="auto")
    plt.colorbar(label="Pass Percentage")
    plt.xlabel("Proof partition index")
    plt.ylabel("Interpolant index")
    plt.title(title)
    out_dir = f"{get_figures_dir()}/absorption_experiments/{K}/pddef_{interpolant_pddef}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{title}.png"
    plt.savefig(out_path)
    plt.close()
    print(f"Saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw absorption heatmap from cached results.")
    parser.add_argument("--instance", required=True, help="Instance name")
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--effective_K", type=int, default=None)
    parser.add_argument("--family", type=str, default=None, help="Family label shown in the title (defaults to instance name)")
    parser.add_argument("--interpolant_pddef", type=int, default=1, choices=[1, 4, 5, 7])
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--use_minisat_proof", action="store_true", default=False)
    parser.add_argument("--use_glucose_proof", action="store_true", default=False)
    parser.add_argument("--include_formula_in_checking", action="store_true", default=True)
    parser.add_argument("--not_include_formula_in_checking", action="store_true", default=False)
    parser.add_argument("--permute", type=str, default=None)
    parser.add_argument("--permute_index", type=int, default=0)
    args = parser.parse_args()

    if args.not_include_formula_in_checking:
        args.include_formula_in_checking = False

    K_effective = args.effective_K if args.effective_K is not None else args.K
    family = args.family if args.family else args.instance
    solver_suffix = (
        "minisat" if args.use_minisat_proof
        else "glucose" if args.use_glucose_proof
        else "cadical"
    )
    include_formula_suffix = include_formula_in_checking_flag_to_suffix(args.include_formula_in_checking)

    grid = load_percentage_grid(
        args.instance, args.K, K_effective,
        solver_suffix, include_formula_suffix,
        reverse=args.reverse,
        interpolant_pddef=args.interpolant_pddef,
        permute=args.permute,
        permute_index=args.permute_index,
    )

    title = f"Absorption Heatmap for family {family}"
    draw(grid, title, args.K, args.interpolant_pddef)


if __name__ == "__main__":
    main()
