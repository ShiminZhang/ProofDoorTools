#!/usr/bin/env python3
"""Compare best_model column between two regression_summary-style CSVs.

Usage:
    python scripts/compare_regression_models.py [old.csv] [new.csv]

Defaults to regression_summary.csv (old) and new_regression.csv (new)
in the repo root. Both files are expected to have a header followed by
rows of "instance_name,best_model,...".
"""
import csv
import sys
from collections import defaultdict


def load_models(path):
    models = {}
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row:
                continue
            models[row[0]] = row[1]
    return models


def main():
    old_path = sys.argv[1] if len(sys.argv) > 1 else "regression_summary.csv"
    new_path = sys.argv[2] if len(sys.argv) > 2 else "new_regression.csv"

    old = load_models(old_path)
    new = load_models(new_path)

    transitions = defaultdict(list)
    missing_in_new = []
    for name, old_model in old.items():
        if name not in new:
            missing_in_new.append(name)
            continue
        new_model = new[name]
        transitions[(old_model, new_model)].append(name)

    print(f"old: {old_path} ({len(old)} instances)")
    print(f"new: {new_path} ({len(new)} instances)")
    print(f"shared instances: {len(old) - len(missing_in_new)}")
    if missing_in_new:
        print(f"missing from new file: {len(missing_in_new)} -> {missing_in_new}")
    print()

    for (old_model, new_model), names in sorted(
        transitions.items(), key=lambda kv: -len(kv[1])
    ):
        arrow = "==" if old_model == new_model else "->"
        print(f"{old_model} {arrow} {new_model}: {len(names)}")
        print(f"  {names}")


if __name__ == "__main__":
    main()
