#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from pipeline_scheduler import classify_interpolants, classify_smt_cnf, schedule_for_instance  # noqa: E402
from PDSScalingExperiment import compute_proofdoor_size_from_smtcnfs  # noqa: E402
from utils.formula_variants import SCRANFILIZE_PROFILES, get_formula_cnf_path, make_formula_variant  # noqa: E402
from utils.paths import get_CNF_dir, get_interpolant_cnf_dir  # noqa: E402
from utils.utils import GetDataFromLog  # noqa: E402


def parse_csv_list(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_int_list(raw: str) -> List[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def iter_targets(
    summary_path: str,
    category: str,
    limit: int,
    k_limit: Optional[int],
) -> Iterable[tuple[str, int, str]]:
    summary_df = pd.read_csv(summary_path)
    required = {"instance_name", "local_max_k", "best_model"}
    missing = required - set(summary_df.columns)
    if missing:
        raise ValueError(f"summary CSV missing required columns: {sorted(missing)}")
    summary_df = summary_df[summary_df["best_model"] == category].sort_values("instance_name")
    if limit > 0:
        summary_df = summary_df.head(limit)
    for _, row in summary_df.iterrows():
        name = str(row["instance_name"]).strip()
        if not name:
            continue
        try:
            local_max_k = int(row["local_max_k"])
        except Exception:
            continue
        max_k = min(local_max_k, k_limit) if k_limit else local_max_k
        for K in range(1, max_k + 1):
            yield name, K, category


def proofdoor_size(instance: str, K: int, pddef: int, suffix: str, reverse: bool) -> int:
    base = get_interpolant_cnf_dir(K, pddef)
    ext = ".reverse.smtcnf" if reverse else ".smtcnf"
    paths = []
    for index in range(K):
        path = f"{base}/{instance}.{K}.{index}{suffix}{ext}"
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return 0
        paths.append(path)
    return compute_proofdoor_size_from_smtcnfs(paths)


def solve_time_for_cnf(cnf_path: str) -> Optional[float]:
    log_path = f"{cnf_path}.cadicalplain.log"
    if not os.path.exists(log_path):
        return None
    return GetDataFromLog(log_path)


def collect_rows(
    *,
    summary_path: str,
    category: str,
    profiles: List[str],
    seeds: List[int],
    pddef: int,
    reverse: bool,
    limit: int,
    k_limit: Optional[int],
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    targets = list(iter_targets(summary_path, category, limit, k_limit))
    for instance, K, row_category in targets:
        orig_interp, _ = classify_interpolants(instance, K, pddef=pddef, reverse=reverse)
        orig_smt, _ = classify_smt_cnf(instance, K, pddef=pddef, reverse=reverse)
        orig_pd = proofdoor_size(instance, K, pddef, "", reverse)
        orig_cnf = f"{get_CNF_dir(K)}/{instance}.{K}.cnf"
        orig_time = solve_time_for_cnf(orig_cnf)

        rows.append(
            {
                "instance_name": instance,
                "K": str(K),
                "category": row_category,
                "profile": "orig",
                "seed": "",
                "boundary_mode": "",
                "interpolant_status": orig_interp,
                "smt2cnf_status": orig_smt,
                "proofdoor_size": str(orig_pd),
                "orig_proofdoor_size": str(orig_pd),
                "proofdoor_over_orig": "1.0" if orig_pd else "",
                "solve_time_s": "" if orig_time is None else str(orig_time),
                "orig_solve_time_s": "" if orig_time is None else str(orig_time),
                "solve_over_orig": "1.0" if orig_time else "",
            }
        )

        for profile in profiles:
            for seed in seeds:
                variant = make_formula_variant(scranfilize_profile=profile, scranfilize_seed=seed)
                suffix = variant.suffix()
                interp, _ = classify_interpolants(
                    instance,
                    K,
                    pddef=pddef,
                    reverse=reverse,
                    scranfilize_profile=profile,
                    scranfilize_seed=seed,
                )
                smt, _ = classify_smt_cnf(
                    instance,
                    K,
                    pddef=pddef,
                    reverse=reverse,
                    scranfilize_profile=profile,
                    scranfilize_seed=seed,
                )
                pd_size = proofdoor_size(instance, K, pddef, suffix, reverse)
                cnf_path = get_formula_cnf_path(instance, K, variant)
                solve_time = solve_time_for_cnf(cnf_path)
                rows.append(
                    {
                        "instance_name": instance,
                        "K": str(K),
                        "category": row_category,
                        "profile": profile,
                        "seed": str(seed),
                        "boundary_mode": "physical",
                        "interpolant_status": interp,
                        "smt2cnf_status": smt,
                        "proofdoor_size": str(pd_size),
                        "orig_proofdoor_size": str(orig_pd),
                        "proofdoor_over_orig": str(pd_size / orig_pd) if orig_pd else "",
                        "solve_time_s": "" if solve_time is None else str(solve_time),
                        "orig_solve_time_s": "" if orig_time is None else str(orig_time),
                        "solve_over_orig": str(solve_time / orig_time) if solve_time and orig_time else "",
                    }
                )
    return rows


def schedule_targets(
    *,
    summary_path: str,
    category: str,
    profiles: List[str],
    seeds: List[int],
    pddef: int,
    reverse: bool,
    limit: int,
    k_limit: Optional[int],
    interpolation: bool,
    do_absorption: bool,
    force_refresh: bool,
) -> None:
    for instance, K, _ in iter_targets(summary_path, category, limit, k_limit):
        for profile in profiles:
            for seed in seeds:
                schedule_for_instance(
                    instance,
                    K,
                    pddef=pddef,
                    category=category,
                    reverse=reverse,
                    interpolation=interpolation,
                    scranfilize_profile=profile,
                    scranfilize_seed=seed,
                    boundary_mode="physical",
                    do_absorption=do_absorption,
                    force_refresh=force_refresh,
                )


def write_csv(rows: List[Dict[str, str]], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fieldnames = [
        "instance_name",
        "K",
        "category",
        "profile",
        "seed",
        "boundary_mode",
        "interpolant_status",
        "smt2cnf_status",
        "proofdoor_size",
        "orig_proofdoor_size",
        "proofdoor_over_orig",
        "solve_time_s",
        "orig_solve_time_s",
        "solve_over_orig",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scranfilize scaling scheduler/collector.")
    parser.add_argument("--summary", default="regression_summary.csv")
    parser.add_argument("--category", default="linear")
    parser.add_argument("--profiles", default="clause_light,clause_mid,clause_full,var_light,var_full")
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--pddef", type=int, default=1)
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--k_limit", type=int, default=None)
    parser.add_argument("--schedule", action="store_true", default=False)
    parser.add_argument("--interpolation", action="store_true", default=False)
    parser.add_argument("--do_absorption", action="store_true", default=False)
    parser.add_argument("--force_refresh", action="store_true", default=False)
    parser.add_argument("--output", default="results/scranfilize_scaling.csv")
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent.parent)
    profiles = parse_csv_list(args.profiles)
    unknown = set(profiles) - set(SCRANFILIZE_PROFILES)
    if unknown:
        raise ValueError(f"Unknown profiles: {sorted(unknown)}")
    seeds = parse_int_list(args.seeds)

    if args.schedule:
        schedule_targets(
            summary_path=args.summary,
            category=args.category,
            profiles=profiles,
            seeds=seeds,
            pddef=args.pddef,
            reverse=args.reverse,
            limit=args.limit,
            k_limit=args.k_limit,
            interpolation=args.interpolation,
            do_absorption=args.do_absorption,
            force_refresh=args.force_refresh,
        )

    rows = collect_rows(
        summary_path=args.summary,
        category=args.category,
        profiles=profiles,
        seeds=seeds,
        pddef=args.pddef,
        reverse=args.reverse,
        limit=args.limit,
        k_limit=args.k_limit,
    )
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
