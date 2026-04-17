import argparse
import csv
import glob
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

SLURM_LOG_DIR = "./SlurmLogs/compute_spd_cadet"
REGRESSION_SUMMARY_PATH = "./regression_summary.csv"
# TODO: update when CADET result directory is finalized
RESULT_DIR_TEMPLATE = "./ProofDoorBenchmark/spd_cadet_results/{K}"


def load_instance_categories() -> Dict[str, str]:
    categories: Dict[str, str] = {}
    with open(REGRESSION_SUMMARY_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            categories[row["instance_name"]] = row["best_model"]
    return categories


def get_target_names(
    categories: Dict[str, str],
    name: Optional[str] = None,
    category: Optional[str] = None,
) -> List[str]:
    if name is not None:
        return [name]

    names = sorted(categories)
    if category is not None:
        names = [inst for inst in names if categories.get(inst) == category]
    return names


def get_log_paths(name: str, K: int, index: int) -> List[str]:
    pattern = os.path.join(SLURM_LOG_DIR, f"k_{K}", f"{name}.{K}.*_{index}.log")
    return sorted(glob.glob(pattern))


def log_indicates_success(log_path: str, name: str, K: int, index: int) -> bool:
    # TODO: update success string when CADET result format is decided
    success_str = f"CADET result written for {name}.{K}.{index}"
    with open(log_path) as f:
        return success_str in f.read()


def compute_success(name: str, K: int, index: int, result_path: str) -> bool:
    log_paths = get_log_paths(name, K, index)
    if log_paths:
        return any(log_indicates_success(p, name, K, index) for p in log_paths)
    return os.path.exists(result_path)


def build_rows(
    names: Iterable[str],
    categories: Dict[str, str],
    K_values: Iterable[int],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for name in names:
        inst_category = categories.get(name, "unknown")
        for K in K_values:
            result_dir = RESULT_DIR_TEMPLATE.format(K=K)
            for index in range(K):
                log_paths = get_log_paths(name, K, index)
                if not log_paths:
                    continue
                result_path = os.path.join(result_dir, f"{name}.{K}.{index}.result")
                ok = compute_success(name, K, index, result_path)
                rows.append(
                    {
                        "name": name,
                        "K": K,
                        "index": index,
                        "category": inst_category,
                        "compute_success": ok,
                    }
                )
    return rows


def write_rows(rows: List[Dict[str, object]], output_path: str) -> None:
    fieldnames = ["name", "K", "index", "category", "compute_success"]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect SPD-CADET computation status into a CSV file."
        )
    )
    parser.add_argument("--K", type=int, required=True, help="K value")
    parser.add_argument(
        "--K_max",
        type=int,
        default=None,
        help="When set, export all K in [--K, --K_max]",
    )
    parser.add_argument("--name", help="Only export rows for one instance")
    parser.add_argument(
        "--category",
        help="Only export rows for instances in this regression_summary category",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output path (default: ./spd_cadet_stats_k_<K>.csv)",
    )
    args = parser.parse_args()

    if args.K_max is not None and args.K_max < args.K:
        raise ValueError("--K_max must be >= --K")

    K_values = list(range(args.K, args.K_max + 1)) if args.K_max is not None else [args.K]
    if args.output is not None:
        output_path = args.output
    elif len(K_values) == 1:
        output_path = f"./spd_cadet_stats_k_{args.K}.csv"
    else:
        output_path = f"./spd_cadet_stats_k_{K_values[0]}_to_{K_values[-1]}.csv"

    categories = load_instance_categories()
    names = get_target_names(categories, name=args.name, category=args.category)
    rows = build_rows(names, categories, K_values)
    write_rows(rows, output_path)
    print(f"Wrote {len(rows)} rows to: {output_path}")


if __name__ == "__main__":
    main()
