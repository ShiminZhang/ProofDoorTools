import argparse
import csv
import os
from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd

from utils.paths import get_CNF_dir, get_interpolant_cnf_dir, get_scrambled_CNF
from utils.scramble import PERMUTE_LIMIT, SCRAMBLE_TYPES, ScrambleType, scramble_cnf
from utils.utils import GetDataFromLog, get_python_activate_command
CADICAL_BINARY = "./solvers/cadical"
SLURM_LOG_DIR = "./SlurmLogs/solve_permutation/"


@dataclass(frozen=True)
class Target:
    instance: str
    K: int


@dataclass(frozen=True)
class SmtCnfStats:
    ok: bool
    size_bytes: int
    n_clauses: int
    path: str


def _overall_status(ok_count: int, required_n: int) -> str:
    """
    Success rule:
    - ok_count == required_n  -> "done"
    - 0 < ok_count < required_n -> "partial"
    - ok_count == 0 -> "fail"
    """
    if required_n <= 0:
        return "fail"
    if ok_count >= required_n:
        return "done"
    if ok_count > 0:
        return "partial"
    return "fail"


def permute_formula(name: str, K: int, permute_type: ScrambleType, permute_index: int) -> None:
    print(f"Permuting {name}.{K}.{permute_type}.{permute_index}")
    cnf_path = f"{get_CNF_dir(K)}/{name}.{K}.cnf"
    scrambled_cnf_path = get_scrambled_CNF(name, K, permute_type, permute_index)
    scramble_cnf(cnf_path, scrambled_cnf_path, permute_type)


def _cadical_paths(cnf_path: str) -> tuple[str, str]:
    return (f"{cnf_path}.cadicalplain.log", f"{cnf_path}.cadicalplain.drat")


def _run_cadical_local(cnf_path: str) -> None:
    log_path, drat_path = _cadical_paths(cnf_path)
    extra_flags = "--plain --no-binary"
    cmd = f"{CADICAL_BINARY} {extra_flags} {cnf_path} {drat_path} > {log_path} 2>&1"
    os.system(cmd)


def _run_cadical_slurm(cnf_path: str, job_name: str) -> None:
    os.makedirs(SLURM_LOG_DIR, exist_ok=True)
    log_path, drat_path = _cadical_paths(cnf_path)
    extra_flags = "--plain --no-binary"
    activate_python = get_python_activate_command()
    cadical_cmd = f"{activate_python} && {CADICAL_BINARY} {extra_flags} {cnf_path} {drat_path} > {log_path} 2>&1"
    slurm_out = f"{SLURM_LOG_DIR}/{job_name}.%j.log"
    os.system(
        f"sbatch --job-name={job_name} --time=00:00:5000 --mem=16g --output={slurm_out} --wrap=\"{cadical_cmd}\""
    )


def _collect_targets_from_csv(
    *,
    csv_path: str,
    category: str,
    name: Optional[str],
    limit: int,
) -> list[Target]:
    summary_df = pd.read_csv(csv_path)
    if "category" in summary_df.columns:
        summary_df = summary_df[summary_df["category"] == category]
    if name:
        summary_df = summary_df[summary_df["instance_name"] == name]

    summary_df["interpolant_status"] = (
        summary_df["interpolant_status"].fillna("").astype(str).str.strip().str.lower()
    )
    summary_df["smt2cnf_status"] = (
        summary_df["smt2cnf_status"].fillna("").astype(str).str.strip().str.lower()
    )
    success_df = summary_df[
        (summary_df["interpolant_status"] == "done")
        & (summary_df["smt2cnf_status"] == "done")
    ]

    targets: list[Target] = []
    for idx, row in success_df.iterrows():
        if len(targets) >= limit:
            break
        instance = str(row["instance_name"])
        try:
            K = int(row["K"])
        except Exception:
            continue
        targets.append(Target(instance=instance, K=K))
    return targets


def _iter_permuted_cnfs(targets: Iterable[Target], permute_type: str, permute_n: int) -> Iterable[tuple[Target, int, str]]:
    for t in targets:
        for perm_idx in range(permute_n):
            cnf_path = get_scrambled_CNF(t.instance, t.K, permute_type, perm_idx)
            yield (t, perm_idx, cnf_path)


def _perm_suffix(permute_type: Optional[str], permute_index: int) -> str:
    if not permute_type:
        return ""
    return f".perm_{permute_type}_{permute_index}"


def _get_smtcnf_path(
    *,
    instance: str,
    K: int,
    index: int,
    permute_type: Optional[str],
    permute_index: int,
    reverse: bool,
    pddef: int,
) -> str:
    base = get_interpolant_cnf_dir(K, pddef)
    perm = _perm_suffix(permute_type, permute_index)
    suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    return f"{base}/{instance}.{K}.{index}{perm}{suffix}"


def _read_smtcnf_stats(path: str) -> SmtCnfStats:
    if not os.path.exists(path):
        return SmtCnfStats(ok=False, size_bytes=0, n_clauses=0, path=path)
    size = os.path.getsize(path)
    if size <= 0:
        return SmtCnfStats(ok=False, size_bytes=size, n_clauses=0, path=path)
    n_clauses = 0
    try:
        with open(path, "r") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                # smtcnf files are typically one clause per line, no DIMACS header.
                # Keep it robust if someone accidentally wrote comments.
                if line.startswith("c") or line.startswith("p"):
                    continue
                n_clauses += 1
    except Exception:
        # If we can't read/parse it, treat as not-ok.
        return SmtCnfStats(ok=False, size_bytes=size, n_clauses=0, path=path)
    return SmtCnfStats(ok=True, size_bytes=size, n_clauses=n_clauses, path=path)


def _compare_smtcnf(
    *,
    targets: list[Target],
    permute_type: str,
    permute_n: int,
    pddef: int,
    reverse: bool,
    index_limit: Optional[int],
    require_n: int,
    out_csv: Optional[str],
    out_summary_csv: Optional[str],
) -> None:
    if permute_n <= 0:
        print(
            f"[SMTCNF] permute_n={permute_n} means no permuted versions to compare. "
            f"Use --permute_n 1 to compare only permute_index=0, or a larger value."
        )
        return
    rows: list[dict] = []
    summary_rows: list[dict] = []
    total_pairs = 0
    ok_pairs = 0
    missing_pairs = 0
    orig_ok = 0
    perm_ok = 0
    sum_orig_bytes = 0
    sum_perm_bytes = 0
    sum_orig_clauses = 0
    sum_perm_clauses = 0

    # Overall success accounting (instance-level):
    # original: key=(instance,K) -> ok_count over required indices
    # permuted: key=(instance,K,perm_idx) -> ok_count over required indices
    orig_ok_count: dict[tuple[str, int], int] = {}
    perm_ok_count: dict[tuple[str, int, int], int] = {}

    for t in targets:
        # "required" indices are what define done/partial/fail.
        # Default: require_n=10 (user rule). If K is smaller, we require min(K, require_n).
        required_n = min(t.K, require_n)
        if index_limit is not None:
            required_n = min(required_n, index_limit)

        n_idx = t.K if index_limit is None else min(t.K, index_limit)
        for idx in range(n_idx):
            orig_path = _get_smtcnf_path(
                instance=t.instance,
                K=t.K,
                index=idx,
                permute_type=None,
                permute_index=0,
                reverse=reverse,
                pddef=pddef,
            )
            orig = _read_smtcnf_stats(orig_path)
            if orig.ok:
                orig_ok += 1
                if idx < required_n:
                    orig_ok_count[(t.instance, t.K)] = orig_ok_count.get((t.instance, t.K), 0) + 1

            for perm_idx in range(permute_n):
                perm_path = _get_smtcnf_path(
                    instance=t.instance,
                    K=t.K,
                    index=idx,
                    permute_type=permute_type,
                    permute_index=perm_idx,
                    reverse=reverse,
                    pddef=pddef,
                )
                perm = _read_smtcnf_stats(perm_path)
                if perm.ok:
                    perm_ok += 1
                    if idx < required_n:
                        key = (t.instance, t.K, perm_idx)
                        perm_ok_count[key] = perm_ok_count.get(key, 0) + 1

                total_pairs += 1
                if not (orig.ok and perm.ok):
                    missing_pairs += 1
                    continue

                ok_pairs += 1
                sum_orig_bytes += orig.size_bytes
                sum_perm_bytes += perm.size_bytes
                sum_orig_clauses += orig.n_clauses
                sum_perm_clauses += perm.n_clauses

                rows.append(
                    {
                        "instance_name": t.instance,
                        "K": t.K,
                        "index": idx,
                        "reverse": reverse,
                        "pddef": pddef,
                        "permute_type": permute_type,
                        "permute_index": perm_idx,
                        "orig_ok": orig.ok,
                        "perm_ok": perm.ok,
                        "orig_size_bytes": orig.size_bytes,
                        "perm_size_bytes": perm.size_bytes,
                        "orig_n_clauses": orig.n_clauses,
                        "perm_n_clauses": perm.n_clauses,
                        "perm_over_orig_bytes": (perm.size_bytes / orig.size_bytes) if orig.size_bytes > 0 else None,
                        "perm_over_orig_clauses": (perm.n_clauses / orig.n_clauses) if orig.n_clauses > 0 else None,
                        "orig_path": orig.path,
                        "perm_path": perm.path,
                    }
                )

        # Ensure keys exist even if 0 ok in required range
        orig_ok_count.setdefault((t.instance, t.K), 0)
        for perm_idx in range(permute_n):
            perm_ok_count.setdefault((t.instance, t.K, perm_idx), 0)

    # Build per-instance/permutation summary with done/partial/fail rule.
    orig_status_counts = {"done": 0, "partial": 0, "fail": 0}
    perm_status_counts = {"done": 0, "partial": 0, "fail": 0}
    pair_status_counts = {"both_done": 0, "both_fail": 0, "mixed": 0}

    for t in targets:
        required_n = min(t.K, require_n)
        if index_limit is not None:
            required_n = min(required_n, index_limit)

        o_ok = orig_ok_count.get((t.instance, t.K), 0)
        o_status = _overall_status(o_ok, required_n)
        orig_status_counts[o_status] += 1

        for perm_idx in range(permute_n):
            p_ok = perm_ok_count.get((t.instance, t.K, perm_idx), 0)
            p_status = _overall_status(p_ok, required_n)
            perm_status_counts[p_status] += 1

            if o_status == "done" and p_status == "done":
                pair_status = "both_done"
            elif o_status == "fail" and p_status == "fail":
                pair_status = "both_fail"
            else:
                pair_status = "mixed"
            pair_status_counts[pair_status] += 1

            summary_rows.append(
                {
                    "instance_name": t.instance,
                    "K": t.K,
                    "required_n": required_n,
                    "reverse": reverse,
                    "pddef": pddef,
                    "permute_type": permute_type,
                    "permute_index": perm_idx,
                    "orig_ok_count": o_ok,
                    "perm_ok_count": p_ok,
                    "orig_status": o_status,
                    "perm_status": p_status,
                    "pair_status": pair_status,
                }
            )

    print(f"[SMTCNF] Total pairs (orig x perm): {total_pairs}")
    print(f"[SMTCNF] Valid pairs (both ok): {ok_pairs}, missing/invalid: {missing_pairs}")
    print(f"[SMTCNF] Orig ok files: {orig_ok}, Perm ok files: {perm_ok} (note: perm counts across permute_n)")
    print(
        f"[SMTCNF] Overall status (orig, per instance; require_n={require_n}): "
        f"done={orig_status_counts['done']}, partial={orig_status_counts['partial']}, fail={orig_status_counts['fail']}"
    )
    print(
        f"[SMTCNF] Overall status (perm, per instance×permute_index; require_n={require_n}): "
        f"done={perm_status_counts['done']}, partial={perm_status_counts['partial']}, fail={perm_status_counts['fail']}"
    )
    print(
        f"[SMTCNF] Pair status (orig vs perm): "
        f"both_done={pair_status_counts['both_done']}, mixed={pair_status_counts['mixed']}, both_fail={pair_status_counts['both_fail']}"
    )
    if ok_pairs > 0:
        avg_orig_bytes = sum_orig_bytes / ok_pairs
        avg_perm_bytes = sum_perm_bytes / ok_pairs
        avg_orig_clauses = sum_orig_clauses / ok_pairs
        avg_perm_clauses = sum_perm_clauses / ok_pairs
        print(
            f"[SMTCNF] Avg bytes: orig={avg_orig_bytes:.1f}, perm={avg_perm_bytes:.1f}, ratio={avg_perm_bytes/avg_orig_bytes:.3f}"
            if avg_orig_bytes > 0
            else f"[SMTCNF] Avg bytes: orig={avg_orig_bytes:.1f}, perm={avg_perm_bytes:.1f}"
        )
        print(
            f"[SMTCNF] Avg clauses: orig={avg_orig_clauses:.1f}, perm={avg_perm_clauses:.1f}, ratio={avg_perm_clauses/avg_orig_clauses:.3f}"
            if avg_orig_clauses > 0
            else f"[SMTCNF] Avg clauses: orig={avg_orig_clauses:.1f}, perm={avg_perm_clauses:.1f}"
        )

    if out_csv:
        os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "instance_name",
                    "K",
                    "index",
                    "reverse",
                    "pddef",
                    "permute_type",
                    "permute_index",
                    "orig_ok",
                    "perm_ok",
                    "orig_size_bytes",
                    "perm_size_bytes",
                    "orig_n_clauses",
                    "perm_n_clauses",
                    "perm_over_orig_bytes",
                    "perm_over_orig_clauses",
                    "orig_path",
                    "perm_path",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"[OK] Wrote smtcnf comparison CSV: {out_csv}")

    if out_summary_csv:
        os.makedirs(os.path.dirname(out_summary_csv) or ".", exist_ok=True)
        with open(out_summary_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "instance_name",
                    "K",
                    "required_n",
                    "reverse",
                    "pddef",
                    "permute_type",
                    "permute_index",
                    "orig_ok_count",
                    "perm_ok_count",
                    "orig_status",
                    "perm_status",
                    "pair_status",
                ],
            )
            writer.writeheader()
            writer.writerows(summary_rows)
        print(f"[OK] Wrote smtcnf summary CSV: {out_summary_csv}")


def _compare_times(
    *,
    targets: list[Target],
    permute_type: str,
    permute_n: int,
    out_csv: Optional[str],
) -> None:
    rows: list[dict] = []
    valid = 0
    improved = 0
    missing = 0
    sum_orig = 0.0
    sum_perm = 0.0

    for t, perm_idx, perm_cnf in _iter_permuted_cnfs(targets, permute_type, permute_n):
        orig_cnf = f"{get_CNF_dir(t.K)}/{t.instance}.{t.K}.cnf"
        orig_log, _ = _cadical_paths(orig_cnf)
        perm_log, _ = _cadical_paths(perm_cnf)

        if not (os.path.exists(orig_log) and os.path.exists(perm_log)):
            missing += 1
            continue
        t_orig = GetDataFromLog(orig_log)
        t_perm = GetDataFromLog(perm_log)
        if t_orig is None or t_perm is None:
            missing += 1
            continue

        valid += 1
        sum_orig += t_orig
        sum_perm += t_perm
        if t_perm < t_orig:
            improved += 1

        ratio = (t_perm / t_orig) if t_orig and t_orig > 0 else None
        red = ((t_orig - t_perm) / t_orig) if t_orig and t_orig > 0 else None

        rows.append(
            {
                "instance_name": t.instance,
                "K": t.K,
                "permute_type": permute_type,
                "permute_index": perm_idx,
                "orig_time_s": t_orig,
                "perm_time_s": t_perm,
                "perm_over_orig": ratio,
                "reduction": red,
                "orig_log": orig_log,
                "perm_log": perm_log,
            }
        )

    print(f"[COMPARE] Valid pairs: {valid}, missing/invalid: {missing}")
    if valid > 0:
        avg_orig = sum_orig / valid
        avg_perm = sum_perm / valid
        overall_reduction = (avg_orig - avg_perm) / avg_orig if avg_orig > 0 else 0.0
        print(f"[COMPARE] Improved count: {improved}/{valid} ({improved/valid:.1%})")
        print(
            f"[COMPARE] Avg original time: {avg_orig:.3f}s, Avg permuted time: {avg_perm:.3f}s, Reduction: {overall_reduction:.1%}"
        )

    if out_csv:
        os.makedirs(os.path.dirname(out_csv) or ".", exist_ok=True)
        with open(out_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "instance_name",
                    "K",
                    "permute_type",
                    "permute_index",
                    "orig_time_s",
                    "perm_time_s",
                    "perm_over_orig",
                    "reduction",
                    "orig_log",
                    "perm_log",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
        print(f"[OK] Wrote comparison CSV: {out_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, default=None)
    parser.add_argument("--category", type=str, default="linear")
    parser.add_argument("--csv_path", type=str, default=None, help="Defaults to <category>.csv")
    parser.add_argument("--permute_type", type=str, required=True, choices=SCRAMBLE_TYPES)
    parser.add_argument("--permute_n", type=int, default=3, help="How many permute_index values to generate/run/compare")
    parser.add_argument("--limit", type=int, default=PERMUTE_LIMIT, help="Max #instances from CSV to process")
    parser.add_argument(
        "--generate",
        action="store_true",
        default=False,
        help="Generate missing permuted CNFs (scramble). If not set, missing permuted CNFs are skipped.",
    )
    parser.add_argument("--run", action="store_true", default=False, help="Solve original & permuted CNFs (CaDiCaL)")
    parser.add_argument("--slurm", action="store_true", default=False, help="If set, submit sbatch jobs instead of local runs")
    parser.add_argument("--compare", action="store_true", default=False, help="Compare solving time between original and permuted CNFs")
    parser.add_argument("--out_csv", type=str, default=None, help="Write per-instance comparison rows to CSV")
    parser.add_argument(
        "--compare_smtcnf",
        action="store_true",
        default=False,
        help="Compare interpolant smtcnf (size + success) between original and permuted versions (no generation).",
    )
    parser.add_argument("--smtcnf_pddef", type=int, default=1, help="Which pddef directory to use for smtcnf (default: 1)")
    parser.add_argument("--smtcnf_reverse", action="store_true", default=False, help="Use .reverse.smtcnf instead of .smtcnf")
    parser.add_argument("--smtcnf_index_limit", type=int, default=None, help="Only compare indices [0,limit) instead of full K")
    parser.add_argument("--out_smtcnf_csv", type=str, default=None, help="Write smtcnf comparison rows to CSV")
    parser.add_argument(
        "--smtcnf_require_n",
        type=int,
        default=10,
        help="How many interpolant indices must be ok for overall success (default: 10). If K is smaller, uses min(K, require_n).",
    )
    parser.add_argument("--out_smtcnf_summary_csv", type=str, default=None, help="Write per-instance overall status summary to CSV")
    args = parser.parse_args()

    csv_path = args.csv_path or f"{args.category}.csv"
    targets = _collect_targets_from_csv(
        csv_path=csv_path,
        category=args.category,
        name=args.name,
        limit=args.limit,
    )
    print(f"Found {len(targets)} targets from {csv_path}")

    if args.generate:
        # Only generate when explicitly requested.
        for t, perm_idx, perm_cnf in _iter_permuted_cnfs(targets, args.permute_type, args.permute_n):
            if os.path.exists(perm_cnf) and os.path.getsize(perm_cnf) > 0:
                continue
            permute_formula(t.instance, t.K, args.permute_type, perm_idx)

    if args.run:
        for t in targets:
            orig_cnf = f"{get_CNF_dir(t.K)}/{t.instance}.{t.K}.cnf"
            if not os.path.exists(orig_cnf):
                print(f"[SKIP] Original CNF not found: {orig_cnf}")
                continue
            if args.slurm:
                _run_cadical_slurm(orig_cnf, job_name=f"solve_orig_{t.instance}.{t.K}")
            else:
                _run_cadical_local(orig_cnf)

        for t, perm_idx, perm_cnf in _iter_permuted_cnfs(targets, args.permute_type, args.permute_n):
            if not os.path.exists(perm_cnf):
                print(f"[SKIP] Permuted CNF not found: {perm_cnf}")
                continue
            if args.slurm:
                _run_cadical_slurm(perm_cnf, job_name=f"solve_perm_{t.instance}.{t.K}.{args.permute_type}.{perm_idx}")
            else:
                _run_cadical_local(perm_cnf)

    if args.compare:
        _compare_times(
            targets=targets,
            permute_type=args.permute_type,
            permute_n=args.permute_n,
            out_csv=args.out_csv,
        )

    if args.compare_smtcnf:
        _compare_smtcnf(
            targets=targets,
            permute_type=args.permute_type,
            permute_n=args.permute_n,
            pddef=args.smtcnf_pddef,
            reverse=args.smtcnf_reverse,
            index_limit=args.smtcnf_index_limit,
            require_n=args.smtcnf_require_n,
            out_csv=args.out_smtcnf_csv,
            out_summary_csv=args.out_smtcnf_summary_csv,
        )