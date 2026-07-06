#!/usr/bin/env python3
"""Build proofdoor computation status CSV from regression_summary.csv."""

import argparse
import csv
import os
import sys
from typing import Dict, Iterable, List, Optional

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pipeline_scheduler import classify_interpolants, classify_smt_cnf  # noqa: E402


def normalize_status(status: str) -> str:
    if status == "done":
        return "done"
    if status == "none":
        return "none"
    return "partial"


def parse_pddefs(raw: str) -> List[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(int(item))
    if not values:
        raise ValueError("--pddef must contain at least one integer")
    return values


def build_rows(
    summary_path: str,
    categories: Optional[Iterable[str]],
    pddefs: Iterable[int],
    scaling: bool = False,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
) -> List[Dict[str, str]]:
    summary_df = pd.read_csv(summary_path)
    required_cols = {"instance_name", "local_max_k", "best_model"}
    missing = required_cols - set(summary_df.columns)
    if missing:
        raise ValueError(f"summary CSV missing required columns: {sorted(missing)}")

    if categories is not None:
        category_set = set(categories)
        summary_df = summary_df[summary_df["best_model"].isin(category_set)]

    rows: List[Dict[str, str]] = []
    for _, entry in summary_df.sort_values("instance_name").iterrows():
        name = str(entry["instance_name"]).strip()
        if not name:
            continue
        try:
            local_max_k = int(entry["local_max_k"])
        except Exception:
            continue
        if local_max_k < 0:
            continue

        category = str(entry["best_model"]).strip()
        k_values = range(1, local_max_k) if scaling else [local_max_k]
        for pddef in pddefs:
            for K in k_values:
                interp_status, _ = classify_interpolants(
                    name,
                    K,
                    pddef=pddef,
                    reverse=reverse,
                    permute=permute,
                    permute_index=permute_index,
                )
                smt2cnf_status, _ = classify_smt_cnf(
                    name,
                    K,
                    pddef=pddef,
                    reverse=reverse,
                    permute=permute,
                    permute_index=permute_index,
                )
                rows.append(
                    {
                        "name": name,
                        "K": str(K),
                        "category": category,
                        "pddef": str(pddef),
                        "interpolant_computation_status": normalize_status(interp_status),
                        "smt2cnf_status": normalize_status(smt2cnf_status),
                    }
                )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create proofdoor_computation_summary.csv from regression_summary.csv."
    )
    parser.add_argument("--summary", default="regression_summary.csv")
    parser.add_argument("--output", default="proofdoor_computation_summary.csv")
    parser.add_argument(
        "--category",
        default=None,
        help="Comma-separated best_model labels to include, e.g. linear,exponential. Default: all rows.",
    )
    parser.add_argument(
        "--pddef",
        default="1",
        help="Comma-separated pddef values to summarize, e.g. 1 or 1,5.",
    )
    parser.add_argument(
        "--scaling",
        action="store_true",
        default=False,
        help="Emit K=1..local_max_k-1 rows instead of only local_max_k.",
    )
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--permute", default=None)
    parser.add_argument("--permute_index", type=int, default=0)
    args = parser.parse_args()

    categories = None
    if args.category:
        categories = [x.strip() for x in args.category.split(",") if x.strip()]
    pddefs = parse_pddefs(args.pddef)

    rows = build_rows(
        args.summary,
        categories=categories,
        pddefs=pddefs,
        scaling=args.scaling,
        reverse=args.reverse,
        permute=args.permute,
        permute_index=args.permute_index,
    )

    fieldnames = [
        "name",
        "K",
        "category",
        "pddef",
        "interpolant_computation_status",
        "smt2cnf_status",
    ]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    interp_done = sum(1 for row in rows if row["interpolant_computation_status"] == "done")
    smt_done = sum(1 for row in rows if row["smt2cnf_status"] == "done")
    both_done = sum(
        1
        for row in rows
        if row["interpolant_computation_status"] == "done"
        and row["smt2cnf_status"] == "done"
    )
    print(f"Wrote {total} rows to {args.output}")
    if total:
        print(
            f"Interpolants done: {interp_done}/{total}; "
            f"SMT2CNF done: {smt_done}/{total}; both done: {both_done}/{total}"
        )


if __name__ == "__main__":
    main()
