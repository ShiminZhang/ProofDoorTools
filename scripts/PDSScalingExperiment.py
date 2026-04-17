import argparse
import csv
import json
import os
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set, Iterable
from utils.bits import theoretical_bits_smtcnf, theoretical_bits_dimacs
from experiments.experiment import Experiment, ExperimentConfig
from utils.catagory import get_instance_list
from utils.paths import get_CNF_dir, get_CNF_info, get_figures_dir, get_interpolant_cnf_dir, get_interpolant_dependence_result_dir, get_aiger_dir


def _tqdm(iterable, **kwargs):
    try:
        mod = __import__("tqdm", fromlist=["tqdm"])
        return mod.tqdm(iterable, **kwargs)
    except Exception:
        return iterable


def _parse_int(s: object) -> Optional[int]:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    try:
        return int(t)
    except Exception:
        # Accept float-looking integers from CSVs, e.g. "10.0".
        try:
            fv = float(t)
            if math.isfinite(fv) and fv.is_integer():
                return int(fv)
        except Exception:
            pass
        return None


def _parse_float(s: object) -> Optional[float]:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    try:
        v = float(t)
    except Exception:
        return None
    if not math.isfinite(v):
        return None
    return float(v)


def _extract_solvingtime_from_info_row(row: Optional[Dict[str, object]]) -> Optional[float]:
    if not isinstance(row, dict):
        return None
    # CNF info commonly stores this as "time".
    for key in ("time", "solvingtime", "solve_time", "cadical_solving_time"):
        v = _parse_float(row.get(key))
        if v is not None and v > 0:
            return float(v)
    return None


def _load_cnf_info_results_by_k(instance: str) -> Dict[int, Dict[str, object]]:
    """
    Load CNF info JSON for an instance and return a mapping K -> result dict.

    Expected file: ProofDoorBenchmark/cnfs/info/{instance}.info.json
    Typical schema:
      { "name": "...", "results": [ { "K": 2, "n": ..., "proofsize": ... }, ... ] }
    """
    info_path = get_CNF_info(instance)
    if not os.path.exists(info_path) or os.path.getsize(info_path) == 0:
        return {}
    try:
        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
            payload = json.load(f)
    except Exception:
        return {}

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return {}

    out: Dict[int, Dict[str, object]] = {}
    for row in results:
        if not isinstance(row, dict):
            continue
        k = _parse_int(row.get("K"))
        if k is None:
            continue
        out[int(k)] = row
    return out


def prepare_data(summary_csv_path: str) -> None:
    """
    Backwards-compatible hook for '--prepare_only'.
    This experiment reads existing artifacts directly; here we only validate inputs.
    """
    if not summary_csv_path:
        raise ValueError("summary_csv_path is empty")
    if not os.path.exists(summary_csv_path):
        raise FileNotFoundError(f"summary CSV not found: {summary_csv_path}")
    print(f"[PDSScaling] prepare_only: summary CSV exists: {summary_csv_path}")


def _x_axis_label(x_mode: str) -> str:
    if x_mode == "K":
        return "K"
    if x_mode == "n":
        return "Number of variables (n)"
    if x_mode == "proofsize":
        return "Proof size (proofsize)"
    if x_mode == "proofdoor_size":
        return "ProofDoor size (bits)"
    if x_mode == "solvingtime":
        return "Solving time (s)"
    return x_mode


def _y_axis_label(y_mode: str, interpolant_unit: str = "bits") -> str:
    if y_mode == "pds":
        return "PDS/K"
    if y_mode == "pgs":
        return "PGS/K"
    if y_mode == "pdsdfs":
        return "PDS/formula size"
    if y_mode == "pgsdfs":
        return "PGS/formula size"
    if y_mode == "proofsize":
        return "Proof size"
    if y_mode == "avg_dependence":
        return "avg ub_dependence"
    if y_mode == "max_dependence":
        return "max ub_dependence"
    if y_mode == "solvingtime":
        return "Solving time (s)"
    if y_mode == "max_interpolant":
        unit_label = "clauses" if interpolant_unit == "clauses" else "bits"
        return f"Max interpolant size ({unit_label})"
    if y_mode == "avg_interpolant":
        unit_label = "clauses" if interpolant_unit == "clauses" else "bits"
        return f"Avg interpolant size ({unit_label})"
    return y_mode


def _y_short_name(y_mode: str) -> str:
    return {
        "pds": "proofdoor/K",
        "pgs": "proofgate/K",
        "pdsdfs": "proofdoor/fs",
        "pgsdfs": "proofgate/fs",
        "proofsize": "proofsize",
        "avg_dependence": "avg_dep",
        "max_dependence": "max_dep",
        "solvingtime": "solving_time",
        "max_interpolant": "max_interp",
        "avg_interpolant": "avg_interp",
    }.get(y_mode, y_mode)


def load_available_ks_from_summary(
    summary_csv_path: str,
    instances: List[str],
    done_only: bool = False,
) -> Dict[str, List[int]]:
    """
    Load per-instance available K values from a "summary" CSV.

    Supported formats:
    1) regression_summary.csv style:
       - columns: instance_name, local_max_k [, best_model ...]
       - available K is interpreted as range(1..local_max_k) if local_max_k > 0

    2) pipeline_scheduler --output_status_to_csv --scaling style:
       - columns include: instance_name, K [, smt2cnf_status ...]
       - available K is the set of K values present in the file, optionally filtered by smt2cnf_status == "done"
    """
    if not os.path.exists(summary_csv_path):
        raise FileNotFoundError(f"summary CSV not found: {summary_csv_path}")

    instance_set: Set[str] = set(instances)
    k_map: Dict[str, Set[int]] = {inst: set() for inst in instances}
    maxk_map: Dict[str, int] = {}

    with open(summary_csv_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {inst: [] for inst in instances}

        cols = set(reader.fieldnames)
        has_k = "K" in cols
        has_local_max_k = "local_max_k" in cols
        if not has_k and not has_local_max_k:
            raise ValueError(
                f"summary CSV {summary_csv_path} missing required columns. "
                f"Need either 'K' or 'local_max_k'. got={reader.fieldnames}"
            )

        for row in reader:
            inst = (row.get("instance_name") or "").strip()
            if not inst or inst not in instance_set:
                continue

            if has_k:
                if done_only and "smt2cnf_status" in cols:
                    status = (row.get("smt2cnf_status") or "").strip().lower()
                    if status != "done":
                        continue
                k = _parse_int(row.get("K"))
                if k is None or k <= 0:
                    continue
                k_map[inst].add(k)
            else:
                mk = _parse_int(row.get("local_max_k"))
                if mk is None or mk <= 0:
                    continue
                prev = maxk_map.get(inst, 0)
                if mk > prev:
                    maxk_map[inst] = mk

    if not has_k:
        for inst in instances:
            mk = maxk_map.get(inst, 0)
            if mk > 0:
                k_map[inst] = set(range(1, mk + 1))

    return {inst: sorted(ks) for inst, ks in k_map.items()}


def load_instances_from_summary(summary_csv_path: str, category: str = "all") -> List[str]:
    """
    Fallback instance discovery when category.csv is missing/empty.

    - If summary contains 'category' column (pipeline_scheduler status CSV), use it.
    - Else if it contains 'best_model' column (regression_summary.csv), use it.
    - Else return all instances present in summary (and ignore category filtering).
    """
    if not os.path.exists(summary_csv_path):
        return []

    instances: List[str] = []
    seen: Set[str] = set()
    category_norm = (category or "all").strip().lower()

    with open(summary_csv_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        cols = set(reader.fieldnames)
        cat_col = (
            "category"
            if "category" in cols
            else ("best_model" if "best_model" in cols else ("class" if "class" in cols else None))
        )

        for row in reader:
            inst = (row.get("instance_name") or "").strip()
            if not inst or inst in seen:
                continue

            if category_norm != "all" and cat_col is not None:
                raw = (row.get(cat_col) or "").strip().lower()
                raw = "none" if raw == "none" else raw
                # Allow nonlinear/exponential aliases in either direction.
                alias_match = (
                    (category_norm == "exponential" and raw == "nonlinear")
                    or (category_norm == "nonlinear" and raw == "exponential")
                )
                if raw != category_norm and not alias_match:
                    continue

            seen.add(inst)
            instances.append(inst)

    return instances


def _count_dimacs_clauses(path: str) -> int:
    """
    Count number of clauses in a DIMACS CNF-like file:
    - ignore empty lines and comment lines starting with 'c'
    - ignore header line starting with 'p '
    - count lines that end with 0 (common DIMACS terminator)
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0
    clauses = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c") or line.startswith("p "):
                continue
            # Most files in this repo use one clause per line ending with 0
            if line.endswith(" 0") or line.endswith("\t0") or line == "0":
                clauses += 1
    return clauses


def load_category_map_from_summary(summary_csv_path: str) -> Dict[str, str]:
    """
    Load per-instance category/label from summary CSV.
    Supports columns: category | best_model | class.
    """
    if not os.path.exists(summary_csv_path):
        return {}
    out: Dict[str, str] = {}
    with open(summary_csv_path, newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return {}
        cols = set(reader.fieldnames)
        cat_col = (
            "category"
            if "category" in cols
            else ("best_model" if "best_model" in cols else ("class" if "class" in cols else None))
        )
        if cat_col is None:
            return {}
        for row in reader:
            inst = (row.get("instance_name") or "").strip()
            if not inst:
                continue
            raw = (row.get(cat_col) or "").strip().lower()
            if raw:
                out[inst] = raw
    return out


def load_instances_from_aigs() -> List[str]:
    aiger_dir = get_aiger_dir()
    if not os.path.isdir(aiger_dir):
        return []
    return sorted(
        os.path.splitext(fn)[0]
        for fn in os.listdir(aiger_dir)
        if fn.endswith(".aig")
    )


def _read_dimacs_header_clause_count(path: str) -> Optional[int]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p cnf"):
                parts = line.split()
                if len(parts) >= 4 and parts[3].isdigit():
                    return int(parts[3])
                return None
    return None


def _count_nonempty_lines(path: str) -> int:
    """
    Count non-empty lines in a text file (used for *.smtcnf size).
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0
    n = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _count_clauses_smtcnf(path: str) -> int:
    """Count the number of clauses in an smtcnf/DIMACS file (skipping headers and comments)."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0
    n = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c") or line.startswith("p"):
                continue
            n += 1
    return n


def compute_formula_size(instance: str, K: int) -> int:
    cnf_path = os.path.join(get_CNF_dir(K), f"{instance}.{K}.cnf")
    if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
        return 0
    # Keep formula_size unit aligned with proofdoor_size: both are theoretical bits.
    try:
        return int(theoretical_bits_dimacs(cnf_path))
    except Exception:
        return 0


def smt2cnf_paths_complete(instance: str, K: int, pddef: int = 1, reverse: bool = False) -> Tuple[bool, List[str]]:
    base = get_interpolant_cnf_dir(K, pddef)
    suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    paths = [os.path.join(base, f"{instance}.{K}.{i}{suffix}") for i in range(K)]
    for p in paths:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return False, paths
    return True, paths


def compute_proofdoor_size_from_smtcnfs(paths: List[str]) -> int:
    # In this repo, "*.smtcnf" files are often NOT DIMACS; we define size as number of lines.
    # return sum(_count_nonempty_lines(p) for p in paths)
    return sum(theoretical_bits_smtcnf(p) for p in paths)


def _y_mode_uses_proofdoor_size(y_mode: str) -> bool:
    return y_mode in ("pds", "pgs", "pdsdfs", "pgsdfs")


def _load_dependence_by_k(instance: str, pddef: int) -> Dict[int, Dict[str, float]]:
    """
    Load interpolant dependence CSV for instance (name.K.i.ub_dependence).
    Return {K: {"avg": float, "max": float}} for each K with at least one row.
    """
    out: Dict[int, List[int]] = {}  # K -> list of ub_dependence
    base_dir = get_interpolant_dependence_result_dir(pddef)
    csv_path = os.path.join(base_dir, f"{instance}.csv")
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "K" in reader.fieldnames and "ub_dependence" in reader.fieldnames:
            for row in reader:
                k_val = _parse_int(row.get("K"))
                ub = _parse_int(row.get("ub_dependence"))
                if k_val is not None and ub is not None:
                    out.setdefault(k_val, []).append(ub)
    result: Dict[int, Dict[str, float]] = {}
    for K, values in out.items():
        if values:
            result[K] = {"avg": sum(values) / float(len(values)), "max": float(max(values))}
    return result


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _read_csv_header(path: str) -> Optional[List[str]]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                return None
            return [h.strip() for h in header if h is not None]
    except Exception:
        return None


def _infer_dashboard_header(template_csv_path: str = "dashboard_data.csv") -> List[str]:
    """
    Infer dashboard CSV header from an existing file (preferred),
    otherwise fall back to the current repo's historical header.
    """
    header = _read_csv_header(template_csv_path)
    if header:
        return header
    # Fallback: matches the checked-in dashboard_data.csv snapshot in this repo.
    return [
        "instance_name",
        "category",
        "formula_size",
        "proofdoor_size",
        "formula-pd-size-ratio",
        "smallest_interpolant_size",
        "largest_interpolant_size",
        "proofdoor_expansion_status",
        "cadical_solving_time",
        "cadical_proof_size",
        "cadical_absorption_result",
        "minisat_solving_time",
        "minisat_learntclauses_size",
        "minisat_absorption_result",
    ]


def _dashboard_default_value(col: str) -> str:
    # Keep defaults consistent with existing dashboard_data.csv conventions.
    if col in ("instance_name", "category"):
        return ""
    if col in ("formula_size",):
        return "0"
    if col in ("proofdoor_size",):
        return "not started"
    if col.endswith("_status") or col.endswith("_result"):
        return "not started" if col.endswith("_status") else ""
    if "smallest" in col or "largest" in col or "variance" in col or "average" in col:
        return "NA"
    if "time" in col or "proof_size" in col or "learnt" in col:
        return "not available"
    return ""


def _iter_to_list(xs: Iterable[str]) -> List[str]:
    return list(xs)


def _is_scalington_summary(path: Optional[str]) -> bool:
    base = os.path.basename((path or "").strip()).lower()
    return base == "scalington.csv"


def _format_dashboard_ratio(formula_size: int, proofdoor_size: int) -> str:
    if formula_size <= 0 or proofdoor_size <= 0:
        return ""
    # dashboard_data.csv uses formula/proofdoor (e.g., 69502/172 = 404.08)
    return f"{(formula_size / proofdoor_size):.2f}"


def _format_expansion_status(done: int, total: int) -> str:
    if total <= 0:
        return "not started"
    if done <= 0:
        return "not started"
    if done >= total:
        return f"success ({total}/{total})"
    return f"partial done ({done}/{total})"


def smt2cnf_progress(
    instance: str, K: int, pddef: int = 1, reverse: bool = False
) -> Tuple[int, int, int, Optional[int], Optional[int]]:
    """
    Returns:
      done_count, total_count, total_size, min_size, max_size
    Size is defined as non-empty line count in each *.smtcnf file.
    min/max only computed if done_count == total_count and total_count > 0.
    """
    base = get_interpolant_cnf_dir(K, pddef)
    suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    paths = [os.path.join(base, f"{instance}.{K}.{i}{suffix}") for i in range(K)]
    sizes: List[int] = []
    for p in paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            s = _count_nonempty_lines(p)
            if s > 0:
                sizes.append(s)
    done = len(sizes)
    total = K
    total_size = sum(sizes)
    if done == total and total > 0 and sizes:
        return done, total, total_size, min(sizes), max(sizes)
    return done, total, total_size, None, None


def parse_cadical_solve_time(log_path: str) -> Optional[float]:
    """
    Parse solve time from a CaDiCaL log file.

    Expected line example: "c Solve time: 0.047435 seconds"
    """
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return None
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "Solve time:" in line:
                    return float(line.split()[-2])
    except Exception:
        return None
    return None


def _format_solve_time(t: Optional[float]) -> str:
    if t is None:
        return ""
    # Compact like dashboard_data.csv (e.g. 0.21)
    return f"{t:.6f}".rstrip("0").rstrip(".")


def _dashboard_minimal_header() -> List[str]:
    return [
        "instance_name",
        "K",
        "category",
        "formula_size",
        "proofdoor_size",
        "formula-pd-size-ratio",
        "smallest_interpolant_size",
        "largest_interpolant_size",
        "cadical_solving_time",
    ]


def write_minimal_dashboard_csv(
    *,
    out_path: str,
    category_by_instance: Dict[str, str],
    instances: List[str],
    available_ks: Dict[str, List[int]],
    dashboard_k: Optional[int],
    pddef: int,
    reverse: bool,
) -> None:
    header = _dashboard_minimal_header()
    _ensure_parent_dir(out_path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        # Default behavior:
        # - If dashboard_k is set: output that K only (if present / >0).
        # - Else: output ALL inferred K values per instance (one row per K).
        for instance in instances:
            ks = available_ks.get(instance, [])
            target_ks = [dashboard_k] if dashboard_k is not None else ks
            for K in sorted(k for k in target_ks if k is not None and int(k) > 0):
                formula_size = compute_formula_size(instance, int(K))
                if formula_size <= 0:
                    continue

                done, total, pd_size, min_i, max_i = smt2cnf_progress(
                    instance, int(K), pddef=pddef, reverse=reverse
                )

                # User request: drop "not started" rows entirely.
                if done <= 0:
                    continue

                ratio_val = _format_dashboard_ratio(formula_size, pd_size) if (total > 0 and done == total) else ""
                smallest_val = str(min_i) if min_i is not None else "NA"
                largest_val = str(max_i) if max_i is not None else "NA"
                cnf_path = os.path.join(get_CNF_dir(int(K)), f"{instance}.{int(K)}.cnf")
                solve_time = parse_cadical_solve_time(f"{cnf_path}.cadicalplain.log")
                solve_time_val = _format_solve_time(solve_time)

                writer.writerow(
                    [
                        instance,
                        str(int(K)),
                        category_by_instance.get(instance, ""),
                        str(formula_size),
                        str(pd_size),
                        ratio_val,
                        smallest_val,
                        largest_val,
                        solve_time_val,
                    ]
                )


def build_available_ks_and_instances(
    *,
    category: str,
    summary_csv_path: str,
    done_only: bool,
    force_instance: Optional[str],
) -> Tuple[List[str], Dict[str, List[int]]]:
    instances = get_instance_list(category)
    if not instances:
        instances = load_instances_from_summary(summary_csv_path, category=category)
    if force_instance is not None:
        instances = [force_instance]
    available_ks = load_available_ks_from_summary(summary_csv_path, instances=instances, done_only=done_only)
    return instances, available_ks


def write_merged_minimal_dashboard_csv(
    *,
    out_path: str,
    summary_csv_linear: str,
    summary_csv_exponential: str,
    done_only: bool,
    force_instance: Optional[str],
    dashboard_k: Optional[int],
    pddef: int,
    reverse: bool,
) -> None:
    lin_instances, lin_ks = build_available_ks_and_instances(
        category="linear",
        summary_csv_path=summary_csv_linear,
        done_only=done_only,
        force_instance=force_instance,
    )
    exp_instances, exp_ks = build_available_ks_and_instances(
        category="exponential",
        summary_csv_path=summary_csv_exponential,
        done_only=done_only,
        force_instance=force_instance,
    )

    summary_category_by_instance: Dict[str, str] = {inst: "linear" for inst in lin_instances}
    summary_category_by_instance.update({inst: "exponential" for inst in exp_instances})

    instances = load_instances_from_aigs()
    if not instances:
        instances = sorted(set(lin_instances) | set(exp_instances))
    if force_instance is not None:
        instances = [force_instance]

    category_by_instance: Dict[str, str] = {
        inst: summary_category_by_instance.get(inst, "unknown") for inst in instances
    }

    merged_ks: Dict[str, List[int]] = {}
    supplement_k = int(dashboard_k) if dashboard_k is not None else 10
    for inst in instances:
        ks = set(lin_ks.get(inst, [])) | set(exp_ks.get(inst, []))
        # If the K is complete on disk, include it even when the summary marks
        # smt2cnf_status as non-done (e.g. historical "none" rows for rast-*).
        complete, _ = smt2cnf_paths_complete(inst, supplement_k, pddef=pddef, reverse=reverse)
        if complete:
            ks.add(supplement_k)
        merged_ks[inst] = sorted(ks)

    unknown_complete = sum(
        1 for inst in instances if category_by_instance.get(inst) == "unknown" and merged_ks.get(inst)
    )
    print(
        f"[PDSScaling] merged dashboard seed: aigs={len(instances)} "
        f"labeled={len(summary_category_by_instance)} unknown_with_rows={unknown_complete}"
    )

    write_minimal_dashboard_csv(
        out_path=out_path,
        category_by_instance=category_by_instance,
        instances=instances,
        available_ks=merged_ks,
        dashboard_k=dashboard_k,
        pddef=pddef,
        reverse=reverse,
    )

@dataclass
class ScalingPoint:
    K: int
    formula_size: int
    proofdoor_size: int

    # y used in plots (depends on --y):
    # - pds/pgs: proofdoor_size / K
    # - pdsdfs/pgsdfs: proofdoor_size / formula_size
    # - proofsize: proofsize read from info json (stored as y_value, proofdoor_size may be 0)
    # - max_interpolant: max interpolant size (bits) under this proofdoor
    y_value: float

    largest_interpolant_size: int = 0

    @property
    def ratio(self) -> float:
        return (self.proofdoor_size / self.formula_size) if self.formula_size > 0 else float("nan")

    def to_dict(self) -> Dict:
        return {
            "K": self.K,
            "formula_size": self.formula_size,
            "proofdoor_size": self.proofdoor_size,
            "largest_interpolant_size": self.largest_interpolant_size,
            "ratio": self.ratio,
            "y_value": self.y_value,
        }


class PDSScalingExperimentConfig(ExperimentConfig):
    def __init__(
        self,
        name: str,
        data_dir: str,
        result_dir: str,
        log_dir: str,
        category: str,
        force_instance: Optional[str] = None,
        pddef: int = 1,
        reverse: bool = False,
        require_complete_smt2cnf: bool = True,
        summary_csv_path: str = "regression_summary.csv",
        summary_done_only: bool = False,
        output_dashboard_csv: Optional[str] = None,
        dashboard_k: Optional[int] = None,
        dashboard_merge_categories: bool = False,
        summary_csv_linear: str = "linear.scaling.csv",
        summary_csv_exponential: str = "exponential.scaling.csv",
        fixed_k: Optional[int] = None,
        use_summary_instances: bool = False,
        trim_top_percent: float = 0.0,
        fit_mode: str = "none",
        x_axis: str = "K",
        y_axis: str = "pds",
        output_suffix: Optional[str] = None,
        plot_dots: bool = False,
        x_bound: Optional[float] = None,
        plot_mean: bool = False,
        plot_max: bool = False,
        log_x: bool = False,
        log_y: bool = False,
        missing_report: bool = False,
        read_pds_from_source: bool = False,
        plot_max_regression: bool = True,
        max_regression_mode: str = "both",
        interpolant_unit: str = "bits",
    ):
        super().__init__(name, data_dir, result_dir, log_dir)
        # NOTE: Experiment base class expects config.K + config.category for metadata.
        # This experiment derives K values from summary CSV.
        self.K = 0
        self.category = category
        self.force_instance = force_instance
        self.pddef = pddef
        self.reverse = reverse
        self.require_complete_smt2cnf = require_complete_smt2cnf
        self.summary_csv_path = summary_csv_path
        self.summary_done_only = summary_done_only
        self.output_dashboard_csv = output_dashboard_csv
        self.dashboard_k = dashboard_k
        self.dashboard_merge_categories = dashboard_merge_categories
        self.summary_csv_linear = summary_csv_linear
        self.summary_csv_exponential = summary_csv_exponential
        self.fixed_k = fixed_k
        self.use_summary_instances = use_summary_instances
        self.trim_top_percent = trim_top_percent
        self.fit_mode = fit_mode
        self.x_axis = (x_axis or "K").strip()
        self.y_axis = (y_axis or "pds").strip()
        self.output_suffix = (output_suffix or "").strip() or None
        self.plot_dots = bool(plot_dots)
        self.x_bound = float(x_bound) if x_bound is not None else None
        self.plot_mean = bool(plot_mean)
        self.plot_max = bool(plot_max)
        self.log_x = bool(log_x)
        self.log_y = bool(log_y)
        self.missing_report = bool(missing_report)
        self.read_pds_from_source = bool(read_pds_from_source)
        self.plot_max_regression = bool(plot_max_regression)
        self.interpolant_unit = (interpolant_unit or "bits").strip().lower()
        if self.interpolant_unit not in ("bits", "clauses"):
            self.interpolant_unit = "bits"
        self.max_regression_mode = (max_regression_mode or "both").strip().lower()
        if self.max_regression_mode not in ("both", "linear", "log"):
            self.max_regression_mode = "both"

        category_norm = (category or "all").strip().lower()

        # Special category: "both" = union of linear + {exponential|nonlinear}.
        # For scalington.csv, categories are linear/nonlinear.
        if category_norm == "both":
            right_category = "nonlinear" if _is_scalington_summary(self.summary_csv_path) else "exponential"
            lin = get_instance_list("linear")
            exp = get_instance_list(right_category)
            if not lin:
                lin = load_instances_from_summary(self.summary_csv_path, category="linear")
            if not exp:
                exp = load_instances_from_summary(self.summary_csv_path, category=right_category)
            self.instance_list = sorted(set(lin) | set(exp))
            self.category_by_instance: Dict[str, str] = {inst: "linear" for inst in lin}
            self.category_by_instance.update({inst: right_category for inst in exp})
        else:
            if self.use_summary_instances:
                self.instance_list = load_instances_from_summary(self.summary_csv_path, category=category)
            else:
                self.instance_list = get_instance_list(category)
                if not self.instance_list:
                    self.instance_list = load_instances_from_summary(self.summary_csv_path, category=category)
            if category_norm == "all":
                summary_map = load_category_map_from_summary(self.summary_csv_path)
                self.category_by_instance = {inst: summary_map.get(inst, "unknown") for inst in self.instance_list}
            else:
                self.category_by_instance = {inst: category_norm for inst in self.instance_list}

        if force_instance is not None:
            self.instance_list = [force_instance]
            self.category_by_instance = {force_instance: self.category_by_instance.get(force_instance, category_norm)}


class PDSScalingExperiment(Experiment):
    def __init__(self, config: PDSScalingExperimentConfig):
        super().__init__(config)
        self.config = config
        self.scaling_results: Dict[str, List[ScalingPoint]] = {}
        self.available_ks: Dict[str, List[int]] = {}
        self.category_by_instance: Dict[str, str] = getattr(self.config, "category_by_instance", {})

        x_mode = (self.config.x_axis or "K").strip()
        if x_mode not in ("K", "n", "proofsize", "proofdoor_size", "solvingtime"):
            x_mode = "K"
        self._x_mode = x_mode

        y_mode = (self.config.y_axis or "pds").strip().lower()
        if y_mode not in ("pds", "pgs", "pdsdfs", "pgsdfs", "proofsize", "avg_dependence", "max_dependence", "solvingtime", "max_interpolant", "avg_interpolant"):
            y_mode = "pds"
        self._y_mode = y_mode

        category_suffix = f"_cat{(self.config.category or 'all').strip().lower()}"
        pddef_suffix = f"_pddef{self.config.pddef}"
        y_suffix = f"_y{self._y_mode}"
        x_suffix = f"_x{self._x_mode}"
        fixed_k_suffix = f"_K{int(self.config.fixed_k)}" if self.config.fixed_k is not None else ""
        unit_suffix = "_clauses" if getattr(self.config, "interpolant_unit", "bits") == "clauses" else ""
        out_tag = f"{category_suffix}{fixed_k_suffix}{y_suffix}{pddef_suffix}{x_suffix}{unit_suffix}"
        if getattr(self.config, "output_suffix", None):
            out_tag += f"_{self.config.output_suffix}"
        self.scaling_results_json_path = os.path.join(
            self.config.result_dir, f"pds_scaling_results{out_tag}.json"
        )
        self.scaling_results_csv_path = os.path.join(
            self.config.result_dir, f"pds_scaling_results{out_tag}.csv"
        )
        plot_tag = f"{pddef_suffix}{unit_suffix}"
        if getattr(self.config, "output_suffix", None):
            plot_tag += f"_{self.config.output_suffix}"
        trim_pct_init = max(0.0, min(100.0, float(getattr(self.config, "trim_top_percent", 0) or 0)))
        if trim_pct_init > 0.0:
            plot_tag += f"_trim{trim_pct_init:g}"
        if self.config.log_x:
            plot_tag += "_logx"
        if self.config.log_y:
            plot_tag += "_logy"
        x_bound_init = getattr(self.config, "x_bound", None)
        if x_bound_init is not None and self.config.fixed_k is None:
            plot_tag += f"_xbound{x_bound_init:g}"
        if self.config.force_instance is not None:
            inst_safe = self.config.force_instance.replace("/", "_").replace("\\", "_")
            inst_unit = "_clauses" if getattr(self.config, "interpolant_unit", "bits") == "clauses" else ""
            per_inst_dir = os.path.join(get_figures_dir(), f"per_instance_{self._y_mode}{inst_unit}")
            os.makedirs(per_inst_dir, exist_ok=True)
            self.scaling_plot_path = os.path.join(
                per_inst_dir,
                f"{inst_safe}_{self._y_mode}{inst_unit}.png",
            )
        elif self.config.fixed_k is not None:
            self.scaling_plot_path = os.path.join(
                get_figures_dir(),
                f"pds_scaling_{self.config.category}_K{self.config.fixed_k}_x{self._x_mode}_y{self._y_mode}{plot_tag}.png",
            )
        else:
            self.scaling_plot_path = os.path.join(
                get_figures_dir(),
                f"pds_scaling_{self.config.category}_x{self._x_mode}_y{self._y_mode}{plot_tag}.png",
            )

    def _needs_proofdoor_size(self) -> bool:
        return self._x_mode == "proofdoor_size" or _y_mode_uses_proofdoor_size(self._y_mode)

    def _load_proofdoor_size_from_source(self, instance: str, K: int) -> int:
        sizes = self._load_interpolant_sizes_from_source(instance, K)
        if not sizes:
            return 0
        return int(sum(sizes))

    def _load_interpolant_sizes_from_source(self, instance: str, K: int) -> List[int]:
        complete, smtcnf_paths = smt2cnf_paths_complete(
            instance, K, pddef=self.config.pddef, reverse=self.config.reverse
        )
        if self.config.require_complete_smt2cnf and not complete:
            return []
        usable_paths = (
            smtcnf_paths
            if complete
            else [p for p in smtcnf_paths if os.path.exists(p) and os.path.getsize(p) > 0]
        )
        if not usable_paths:
            return []
        try:
            if getattr(self.config, "interpolant_unit", "bits") == "clauses":
                return [_count_clauses_smtcnf(p) for p in usable_paths]
            return [int(theoretical_bits_smtcnf(p)) for p in usable_paths]
        except Exception:
            return []

    def _refresh_cached_proofdoor_sizes_from_source(self) -> bool:
        if not self.config.read_pds_from_source or not self._needs_proofdoor_size():
            return False
        changed = False
        repaired = 0
        for inst, pts in self.scaling_results.items():
            for p in pts:
                if int(p.proofdoor_size) > 0:
                    continue
                proofdoor_size = self._load_proofdoor_size_from_source(inst, int(p.K))
                if proofdoor_size <= 0:
                    continue
                p.proofdoor_size = int(proofdoor_size)
                if _y_mode_uses_proofdoor_size(self._y_mode):
                    if self._y_mode in ("pdsdfs", "pgsdfs"):
                        if p.formula_size > 0:
                            p.y_value = float(p.proofdoor_size) / float(p.formula_size)
                    elif p.K > 0:
                        p.y_value = float(p.proofdoor_size) / float(p.K)
                changed = True
                repaired += 1
        if repaired > 0:
            print(f"[PDSScaling] refreshed {repaired} cached proofdoor_size values from interpolant_as_cnfs")
        return changed

    def on_start(self):
        # We don't schedule jobs here; this experiment only reads existing artifacts and summarizes them.
        pass

    def on_end(self):
        pass

    def experiment_main(self):
        self.manage()
        self.end()

    def _collect_missing_proofdoor_pairs(self) -> List[Tuple[str, int, str]]:
        """
        Return (instance, K, reason) for pairs present in input summary/selection
        but missing a usable proofdoor size.
        """
        if self._y_mode not in ("pds", "pgs", "pdsdfs", "pgsdfs"):
            return []
        missing: List[Tuple[str, int, str]] = []
        for instance in self.config.instance_list:
            for K in self.available_ks.get(instance, []):
                formula_size = compute_formula_size(instance, K)
                if formula_size <= 0:
                    # Not a proofdoor-size issue; CNF/formula itself missing.
                    continue
                complete, smtcnf_paths = smt2cnf_paths_complete(
                    instance, K, pddef=self.config.pddef, reverse=self.config.reverse
                )
                if self.config.require_complete_smt2cnf and not complete:
                    missing.append((instance, int(K), "incomplete_smt2cnf"))
                    continue
                if not any(os.path.exists(p) and os.path.getsize(p) > 0 for p in smtcnf_paths):
                    missing.append((instance, int(K), "no_smtcnf_files"))
                    continue
                proofdoor_size = self._load_proofdoor_size_from_source(instance, K)
                if proofdoor_size <= 0:
                    missing.append((instance, int(K), "proofdoor_size_nonpositive"))
        return missing

    def _print_missing_proofdoor_pairs(self) -> None:
        missing = self._collect_missing_proofdoor_pairs()
        if not missing:
            print("[PDSScaling] missing proofdoor list: none")
            return
        print(f"[PDSScaling] missing proofdoor list: {len(missing)} (instance,K) pairs")
        for inst, k, reason in sorted(missing, key=lambda t: (t[0], t[1])):
            print(f"[PDSScaling][missing_proofdoor] instance={inst} K={k} reason={reason}")

    def _compute_instance_scaling(self, instance: str) -> List[ScalingPoint]:
        points: List[ScalingPoint] = []
        y_mode = self._y_mode
        need_proofdoor_for_x = (self._x_mode == "proofdoor_size")
        y_uses_proofdoor = y_mode in ("pds", "pgs", "pdsdfs", "pgsdfs")
        y_uses_interpolant_sizes = y_mode in ("max_interpolant", "avg_interpolant")
        info_by_k = _load_cnf_info_results_by_k(instance) if y_mode in ("proofsize", "solvingtime") else {}
        dep_by_k = _load_dependence_by_k(instance, self.config.pddef) if y_mode in ("avg_dependence", "max_dependence") else {}
        for K in self.available_ks.get(instance, []):
            formula_size = compute_formula_size(instance, K)
            if formula_size == 0:
                # CNF missing/empty, skip
                continue

            proofdoor_size = 0
            largest_interpolant_size = 0
            interpolant_sizes: List[int] = []
            if need_proofdoor_for_x or y_uses_proofdoor or y_uses_interpolant_sizes:
                interpolant_sizes = self._load_interpolant_sizes_from_source(instance, K)
                proofdoor_size = int(sum(interpolant_sizes))
                largest_interpolant_size = int(max(interpolant_sizes)) if interpolant_sizes else 0
                if proofdoor_size <= 0:
                    continue

            if y_mode == "proofsize":
                row = info_by_k.get(int(K))
                if not row:
                    continue
                pv = _parse_int(row.get("proofsize"))
                if pv is None or pv <= 0:
                    continue
                points.append(
                    ScalingPoint(
                        K=K,
                        formula_size=formula_size,
                        proofdoor_size=proofdoor_size,
                        largest_interpolant_size=largest_interpolant_size,
                        y_value=float(pv),
                    )
                )
                continue

            if y_mode in ("avg_dependence", "max_dependence"):
                row = dep_by_k.get(K)
                if not row:
                    continue
                y_val = row["avg"] if y_mode == "avg_dependence" else row["max"]
                points.append(
                    ScalingPoint(
                        K=K,
                        formula_size=formula_size,
                        proofdoor_size=proofdoor_size,
                        largest_interpolant_size=largest_interpolant_size,
                        y_value=float(y_val),
                    )
                )
                continue

            if y_mode == "solvingtime":
                row = info_by_k.get(int(K))
                solve_time = _extract_solvingtime_from_info_row(row)
                if solve_time is None:
                    continue
                points.append(
                    ScalingPoint(
                        K=K,
                        formula_size=formula_size,
                        proofdoor_size=proofdoor_size,
                        largest_interpolant_size=largest_interpolant_size,
                        y_value=float(solve_time),
                    )
                )
                continue

            if y_mode == "max_interpolant":
                max_interp = max(interpolant_sizes) if interpolant_sizes else 0
                if max_interp <= 0:
                    continue
                points.append(
                    ScalingPoint(
                        K=K,
                        formula_size=formula_size,
                        proofdoor_size=proofdoor_size,
                        largest_interpolant_size=largest_interpolant_size,
                        y_value=float(max_interp),
                    )
                )
                continue

            if y_mode == "avg_interpolant":
                if not interpolant_sizes:
                    continue
                avg_interp = sum(interpolant_sizes) / len(interpolant_sizes)
                if avg_interp <= 0:
                    continue
                points.append(
                    ScalingPoint(
                        K=K,
                        formula_size=formula_size,
                        proofdoor_size=proofdoor_size,
                        largest_interpolant_size=largest_interpolant_size,
                        y_value=float(avg_interp),
                    )
                )
                continue

            # y_mode == pds/pgs/pdsdfs/pgsdfs: proofdoor_size already computed above.
            if proofdoor_size <= 0 or K <= 0:
                continue
            if y_mode in ("pdsdfs", "pgsdfs"):
                y_val = float(proofdoor_size) / float(formula_size)
            else:
                y_val = float(proofdoor_size) / float(K)
            points.append(
                ScalingPoint(
                    K=K,
                    formula_size=formula_size,
                    proofdoor_size=proofdoor_size,
                    largest_interpolant_size=largest_interpolant_size,
                    y_value=y_val,
                )
            )
        return points

    def manage(self):
        # If results JSON already exists, load from cache and skip recomputation.
        if self._load_scaling_results():
            # Cache may not contain all (instance,K) from the input summary.
            if self.config.fixed_k is not None:
                self.available_ks = {inst: [int(self.config.fixed_k)] for inst in self.config.instance_list}
            else:
                self.available_ks = load_available_ks_from_summary(
                    self.config.summary_csv_path,
                    instances=self.config.instance_list,
                    done_only=self.config.summary_done_only,
                )
            if self._refresh_cached_proofdoor_sizes_from_source():
                self._save_scaling_results()
            self.logger.info("Loaded scaling results from cache: %s", self.scaling_results_json_path)
            print(f"[PDSScaling] loaded results from cache: {self.scaling_results_json_path}")
            if self.config.missing_report:
                self._print_missing_proofdoor_pairs()
            print(f"[PDSScaling] plot path:           {self.scaling_plot_path}")
            self._write_dashboard_csv_if_requested()
            self._plot_scaling_results()
            return

        if self.config.fixed_k is not None:
            if self.config.fixed_k <= 0:
                raise ValueError(f"fixed_k must be positive, got {self.config.fixed_k}")
            self.available_ks = {inst: [int(self.config.fixed_k)] for inst in self.config.instance_list}
        else:
            self.available_ks = load_available_ks_from_summary(
                self.config.summary_csv_path,
                instances=self.config.instance_list,
                done_only=self.config.summary_done_only,
            )
        total_k = sum(len(v) for v in self.available_ks.values())
        if total_k == 0:
            raise RuntimeError(
                "No K values inferred from summary (after filtering). "
                f"summary={self.config.summary_csv_path} category={self.config.category} "
                f"instances={len(self.config.instance_list)} summary_done_only={self.config.summary_done_only}"
            )

        self.logger.info(
            "PDSScalingExperiment: category=%s instances=%s pddef=%s reverse=%s require_complete_smt2cnf=%s summary=%s summary_done_only=%s",
            self.config.category,
            len(self.config.instance_list),
            self.config.pddef,
            self.config.reverse,
            self.config.require_complete_smt2cnf,
            self.config.summary_csv_path,
            self.config.summary_done_only,
        )
        if self.config.missing_report:
            self._print_missing_proofdoor_pairs()

        for instance in _tqdm(self.config.instance_list, desc="PDSScaling instances", unit="inst"):
            pts = self._compute_instance_scaling(instance)
            if pts:
                self.scaling_results[instance] = pts

        # If we got no data with require_complete_smt2cnf, retry once with partial allowed (e.g. pddef 3 may have incomplete smtcnf)
        if not self.scaling_results and self.config.require_complete_smt2cnf:
            self.logger.info("No data with require_complete_smt2cnf; retrying with partial smt2cnf allowed.")
            print("[PDSScaling] no data with complete smt2cnf; retrying with partial allowed.")
            orig_require = self.config.require_complete_smt2cnf
            try:
                self.config.require_complete_smt2cnf = False
                for instance in _tqdm(self.config.instance_list, desc="PDSScaling retry(partial)", unit="inst"):
                    pts = self._compute_instance_scaling(instance)
                    if pts:
                        self.scaling_results[instance] = pts
            finally:
                self.config.require_complete_smt2cnf = orig_require

        if not self.scaling_results:
            print(
                "[PDSScaling] no instances with data (run from repo root; check ProofDoorBenchmark/cnfs/ and "
                f"interpolant_as_cnfs_{self.config.pddef}/ exist for this category)."
            )
        if self.scaling_results:
            self._save_scaling_results()
        print(f"[PDSScaling] plot path:           {self.scaling_plot_path}")
        self._write_dashboard_csv_if_requested()
        self._plot_scaling_results()

    def _write_dashboard_csv_if_requested(self) -> None:
        out_path = (self.config.output_dashboard_csv or "").strip()
        if not out_path:
            return

        # Minimal schema requested by user.
        category_norm = (self.config.category or "").strip().lower()
        category_by_instance = (
            self.category_by_instance
            if category_norm == "both"
            else {inst: self.config.category for inst in self.config.instance_list}
        )
        write_minimal_dashboard_csv(
            out_path=out_path,
            category_by_instance=category_by_instance,
            instances=self.config.instance_list,
            available_ks=self.available_ks,
            dashboard_k=self.config.dashboard_k,
            pddef=self.config.pddef,
            reverse=self.config.reverse,
        )
        self.logger.info("Wrote minimal dashboard CSV %s", out_path)

    def _load_scaling_results(self) -> bool:
        """Load scaling_results from existing JSON. Returns True if loaded, False if file missing/invalid."""
        path = self.scaling_results_json_path
        if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False
        # Invalidate historical caches where formula_size was stored in clauses.
        if str(payload.get("formula_size_unit", "")).strip().lower() != "bits":
            return False
        # Ensure cache matches current summary CSV (by filename).
        cached_summary = os.path.basename(str(payload.get("summary_csv_path", "")).strip()).lower()
        current_summary = os.path.basename(str(self.config.summary_csv_path or "").strip()).lower()
        if cached_summary and current_summary and cached_summary != current_summary:
            return False
        instances_data = payload.get("instances")
        if not isinstance(instances_data, dict) or not instances_data:
            # Empty or missing instances: treat as invalid, remove file so next run recomputes
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
            return False
        self.scaling_results = {}
        for inst, pts_data in instances_data.items():
            if not isinstance(pts_data, list):
                continue
            pts: List[ScalingPoint] = []
            for d in pts_data:
                if not isinstance(d, dict):
                    continue
                K = _parse_int(d.get("K"))
                formula_size = _parse_int(d.get("formula_size"))
                proofdoor_size = _parse_int(d.get("proofdoor_size"))
                largest_interpolant_size = _parse_int(d.get("largest_interpolant_size"))
                y_val = d.get("y_value")
                if K is None or formula_size is None:
                    continue
                try:
                    y_value = float(y_val)
                except (TypeError, ValueError):
                    continue
                pts.append(
                    ScalingPoint(
                        K=int(K),
                        formula_size=int(formula_size),
                        proofdoor_size=int(proofdoor_size or 0),
                        largest_interpolant_size=int(largest_interpolant_size or 0),
                        y_value=y_value,
                    )
                )
            if pts:
                self.scaling_results[inst] = pts
        if not self.scaling_results:
            return False
        # Invalidate historical cache produced before proofdoor_size was populated
        # for non-proofdoor y modes when plotting with x=proofdoor_size.
        if self._x_mode == "proofdoor_size" and self._y_mode in ("proofsize", "avg_dependence", "max_dependence", "solvingtime"):
            has_positive_proofdoor = any(
                p.proofdoor_size > 0 for pts in self.scaling_results.values() for p in pts
            )
            if not has_positive_proofdoor:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
                return False
        # Restrict to current category: only use instances in config.instance_list (e.g. exponential vs linear)
        # Normalize names (strip) so cache from summary vs get_instance_list still matches
        instance_list_set = {str(i).strip() for i in self.config.instance_list}
        filtered = {inst: pts for inst, pts in self.scaling_results.items() if (inst.strip() if isinstance(inst, str) else str(inst).strip()) in instance_list_set}
        if filtered:
            self.scaling_results = filtered
        # If filter would remove all but cache had data, keep all (e.g. instance_list from summary vs get_instance_list mismatch)
        if not self.scaling_results:
            return False
        # Derive available_ks from loaded results (for dashboard / consistency)
        self.available_ks = {inst: sorted(set(p.K for p in pts)) for inst, pts in self.scaling_results.items()}
        return True

    def _save_scaling_results(self) -> None:
        os.makedirs(self.config.result_dir, exist_ok=True)

        payload = {
            "category": self.config.category,
            "pddef": self.config.pddef,
            "reverse": self.config.reverse,
            "require_complete_smt2cnf": self.config.require_complete_smt2cnf,
            "summary_csv_path": self.config.summary_csv_path,
            "summary_done_only": self.config.summary_done_only,
            "formula_size_unit": "bits",
            "proofdoor_size_unit": "bits",
            "instances": {
                inst: [p.to_dict() for p in pts] for inst, pts in sorted(self.scaling_results.items())
            },
        }
        with open(self.scaling_results_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        with open(self.scaling_results_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "instance_name",
                    "K",
                    "formula_size",
                    "proofdoor_size",
                    "largest_interpolant_size",
                    "ratio",
                    "y_mode",
                    "y_value",
                ],
            )
            writer.writeheader()
            for inst, pts in sorted(self.scaling_results.items()):
                for p in pts:
                    writer.writerow(
                        {
                            "instance_name": inst,
                            "K": p.K,
                            "formula_size": p.formula_size,
                            "proofdoor_size": p.proofdoor_size,
                            "largest_interpolant_size": p.largest_interpolant_size,
                            "ratio": p.ratio,
                            "y_mode": self._y_mode,
                            "y_value": p.y_value,
                        }
                    )

        self.logger.info("Wrote %s and %s", self.scaling_results_json_path, self.scaling_results_csv_path)
        print(f"[PDSScaling] wrote results json: {self.scaling_results_json_path}")
        print(f"[PDSScaling] wrote results csv:  {self.scaling_results_csv_path}")

    def _plot_scaling_results(self) -> None:
        # Plotting is optional; skip if matplotlib is not installed.
        try:
            import matplotlib.pyplot as plt  # type: ignore
        except ModuleNotFoundError:
            self.logger.info("matplotlib not installed; skip plotting.")
            print(f"[PDSScaling] plot NOT written: matplotlib not installed.")
            return

        if not self.scaling_results:
            self.logger.info("No scaling results; skip plotting.")
            print(f"[PDSScaling] plot NOT written: no scaling results (no instances with data).")
            return

        os.makedirs(os.path.dirname(self.scaling_plot_path), exist_ok=True)

        if self.config.fixed_k is not None:
            # Scatter for a fixed K:
            # - if --x is n/proofsize: use that from cnf info json (per instance at this K)
            # - if --x is solvingtime: use solving time from cnf info json (per instance at this K)
            # - if --x is proofdoor_size: use proofdoor_size computed in this experiment (bits)
            # - if --x is K: fall back to formula_size bits (since K is constant)
            xs: List[float] = []
            ys: List[float] = []
            ys_for_mean: List[float] = []
            cats: List[str] = []
            x_mode = self._x_mode
            fixed_k = int(self.config.fixed_k)
            for inst, pts in self.scaling_results.items():
                info_by_k_for_inst = _load_cnf_info_results_by_k(inst) if x_mode in ("n", "proofsize", "solvingtime") else {}
                for p in pts:
                    if p.K != fixed_k:
                        continue
                    y_val = float(p.y_value)
                    if math.isnan(y_val) or y_val <= 0:
                        continue
                    if x_mode in ("n", "proofsize"):
                        row = info_by_k_for_inst.get(int(fixed_k))
                        if not row:
                            continue
                        x_val = _parse_int(row.get(x_mode))
                        if x_val is None or x_val <= 0:
                            continue
                        xs.append(int(x_val))
                        ys.append(float(y_val))
                        ys_for_mean.append(float(y_val))
                        cats.append(self.category_by_instance.get(inst, self.config.category))
                    elif x_mode == "solvingtime":
                        row = info_by_k_for_inst.get(int(fixed_k))
                        solve_time = _extract_solvingtime_from_info_row(row)
                        if solve_time is None:
                            continue
                        xs.append(float(solve_time))
                        ys.append(float(y_val))
                        ys_for_mean.append(float(y_val))
                        cats.append(self.category_by_instance.get(inst, self.config.category))
                    elif x_mode == "proofdoor_size":
                        if p.proofdoor_size > 0:
                            xs.append(float(p.proofdoor_size))
                            ys.append(float(y_val))
                            ys_for_mean.append(float(y_val))
                            cats.append(self.category_by_instance.get(inst, self.config.category))
                    else:
                        # formula size (theoretical bits)
                        if p.formula_size > 0:
                            xs.append(float(p.formula_size))
                            ys.append(float(y_val))
                            ys_for_mean.append(float(y_val))
                            cats.append(self.category_by_instance.get(inst, self.config.category))

            if not xs:
                self.logger.info("No valid points for plotting; skip plot.")
                print(
                    f"[PDSScaling] plot NOT written: no valid (x,y) points for x={x_mode} at K={fixed_k}. "
                    f"(Need matching CNF info fields for the selected x-axis mode.)"
                )
                return

            trim_pct = max(0.0, min(100.0, float(self.config.trim_top_percent or 0.0)))
            if trim_pct > 0.0:
                # Use floor (not round) so small trim_pct still drops points.
                keep_n = max(1, int(math.floor(len(xs) * (1.0 - trim_pct / 100.0))))
                # Sort by PDS size (y) descending and keep the smallest keep_n points.
                combined = sorted(zip(xs, ys, ys_for_mean, cats), key=lambda t: t[1], reverse=True)
                kept = combined[-keep_n:] if keep_n < len(combined) else combined
                xs = [k[0] for k in kept]
                ys = [k[1] for k in kept]
                ys_for_mean = [k[2] for k in kept]
                cats = [k[3] for k in kept]

            if self.config.log_x or self.config.log_y:
                filtered = []
                for x_v, y_v, ym_v, c_v in zip(xs, ys, ys_for_mean, cats):
                    if self.config.log_x and x_v <= 0:
                        continue
                    if self.config.log_y and y_v <= 0:
                        continue
                    filtered.append((x_v, y_v, ym_v, c_v))
                xs = [t[0] for t in filtered]
                ys = [t[1] for t in filtered]
                ys_for_mean = [t[2] for t in filtered]
                cats = [t[3] for t in filtered]

            # Print summary statistics for the plotted scatter.
            if xs and ys and ys_for_mean:
                category_norm = (self.config.category or "").strip().lower()
                if category_norm in ("both", "all"):
                    groups: Dict[str, List[int]] = {}
                    for i, c in enumerate(cats):
                        key = str(c).strip().lower() or "unknown"
                        groups.setdefault(key, []).append(i)
                    labels_sorted = sorted(groups.keys(), key=lambda k: (k != "linear", k))
                    for label_name in labels_sorted:
                        idxs = groups[label_name]
                        if not idxs:
                            continue
                        x_mean = sum(float(xs[i]) for i in idxs) / float(len(idxs))
                        y_mean = sum(float(ys[i]) for i in idxs) / float(len(idxs))
                        r_mean = sum(float(ys_for_mean[i]) for i in idxs) / float(len(idxs))
                        print(
                            f"[PDSScaling] scatter means (K={fixed_k}, x={x_mode}, category={label_name}): "
                            f"x_mean={x_mean:.6f} y_mean={y_mean:.6f} ({_y_short_name(self._y_mode)})mean={r_mean:.6f} n={len(idxs)}"
                        )
                else:
                    x_mean = sum(float(v) for v in xs) / float(len(xs))
                    y_mean = sum(float(v) for v in ys) / float(len(ys))
                    r_mean = sum(float(v) for v in ys_for_mean) / float(len(ys_for_mean))
                    print(
                        f"[PDSScaling] scatter means (K={fixed_k}, x={x_mode}): "
                        f"x_mean={x_mean:.6f} y_mean={y_mean:.6f} ({_y_short_name(self._y_mode)})mean={r_mean:.6f} n={len(xs)}"
                    )

            plt.figure(figsize=(10, 6))
            category_norm = (self.config.category or "").strip().lower()
            if category_norm in ("both", "all"):
                # Color points by all observed labels (e.g. linear/nonlinear/exclude).
                groups: Dict[str, List[int]] = {}
                for i, c in enumerate(cats):
                    key = str(c).strip().lower() or "unknown"
                    groups.setdefault(key, []).append(i)
                palette = [
                    "tab:blue",
                    "tab:orange",
                    "tab:green",
                    "tab:red",
                    "tab:purple",
                    "tab:brown",
                    "tab:pink",
                    "tab:gray",
                    "tab:olive",
                    "tab:cyan",
                ]
                labels_sorted = sorted(groups.keys(), key=lambda k: (k != "linear", k))
                for j, label_name in enumerate(labels_sorted):
                    idxs = groups[label_name]
                    plt.scatter(
                        [xs[i] for i in idxs],
                        [ys[i] for i in idxs],
                        alpha=0.6,
                        s=18,
                        label=label_name,
                        color=palette[j % len(palette)],
                    )
                if groups:
                    plt.legend()
            else:
                plt.scatter(xs, ys, alpha=0.6, s=18)
            if x_mode in ("n", "proofsize", "solvingtime", "proofdoor_size"):
                x_label = _x_axis_label(x_mode)
            else:
                x_label = "Formula size (bits)"
            plt.xlabel(x_label)
            _unit = getattr(self.config, "interpolant_unit", "bits")
            title = f"{_y_axis_label(self._y_mode, _unit)} vs {x_label} (K={fixed_k}, {self.config.category})"
            if trim_pct > 0.0:
                title += f", trim top {trim_pct:g}%"
            if self.config.log_x or self.config.log_y:
                if self.config.log_x and self.config.log_y:
                    title += ", log-log"
                elif self.config.log_x:
                    title += ", log-x"
                else:
                    title += ", log-y"
            plt.title(title)
            plt.ylabel(_y_axis_label(self._y_mode, _unit))
            if self.config.log_x:
                plt.xscale("log")
            if self.config.log_y:
                plt.yscale("log")
            plt.grid(True, alpha=0.3)
            self._plot_fit_lines(xs, ys, plt)
            # Make lower bounds match the plotted data minimums.
            if xs:
                plt.xlim(left=min(xs))
            if ys:
                plt.ylim(bottom=min(ys))
            plt.tight_layout()
            plt.savefig(self.scaling_plot_path, dpi=200)
            plt.close()
            self.logger.info("Wrote plot %s", self.scaling_plot_path)
            print(f"[PDSScaling] wrote plot:         {self.scaling_plot_path}")
            return

        # Plot: per-instance ratio curve (light), and mean ratio per K (bold).
        x_mode = self._x_mode
        per_k: Dict[int, List[float]] = {}
        per_k_by_cat: Dict[str, Dict[int, List[float]]] = {}
        all_xy_pairs: List[Tuple[float, float]] = []  # for x!=K max line
        all_xy_pairs_by_cat: Dict[str, List[Tuple[float, float]]] = {}
        x_bound = getattr(self.config, "x_bound", None)
        if x_bound is not None:
            x_bound = float(x_bound)
        plt.figure(figsize=(10, 6))

        category_norm = (self.config.category or "").strip().lower()
        is_multi_cat = category_norm in ("both", "all")
        labeled: Set[str] = set()
        palette = [
            "tab:blue",
            "tab:orange",
            "tab:green",
            "tab:red",
            "tab:purple",
            "tab:brown",
            "tab:pink",
            "tab:gray",
            "tab:olive",
            "tab:cyan",
        ]
        observed_labels = sorted(
            {
                (str(self.category_by_instance.get(inst, self.config.category) or "").strip().lower() or "unknown")
                for inst in self.scaling_results.keys()
            },
            key=lambda k: (k != "linear", k),
        )
        color_map = {label: palette[i % len(palette)] for i, label in enumerate(observed_labels)}

        # Optional trimming: drop instances with the highest mean y-value (any x axis).
        trim_pct = max(0.0, min(100.0, float(self.config.trim_top_percent or 0.0)))
        keep_instances: Optional[Set[str]] = None
        if trim_pct > 0.0 and self.scaling_results:
            # Build per-instance mean y.
            inst_means: List[Tuple[str, float, str]] = []
            for inst, pts in self.scaling_results.items():
                ys = [float(p.y_value) for p in pts if not math.isnan(float(p.y_value))]
                if not ys:
                    continue
                cat = str(self.category_by_instance.get(inst, self.config.category) or "").strip().lower()
                inst_means.append((inst, sum(ys) / float(len(ys)), cat))

            def _keep_from_group(rows: List[Tuple[str, float, str]]) -> Set[str]:
                if not rows:
                    return set()
                # keep_n uses floor so small trim_pct still drops.
                keep_n = max(1, int(math.floor(len(rows) * (1.0 - trim_pct / 100.0))))
                if keep_n >= len(rows):
                    return {r[0] for r in rows}
                # Sort by mean y descending, drop the top trimmed ones.
                rows_sorted = sorted(rows, key=lambda t: t[1], reverse=True)
                kept = rows_sorted[-keep_n:]
                return {r[0] for r in kept}

            if is_multi_cat:
                lin_rows = [r for r in inst_means if r[2] == "linear"]
                other_rows = [r for r in inst_means if r[2] != "linear"]
                keep_instances = _keep_from_group(lin_rows) | _keep_from_group(other_rows)
                trimmed = len(inst_means) - len(keep_instances)
                print(
                    f"[PDSScaling] trim_top_percent={trim_pct:g}% (x={x_mode}): kept {len(keep_instances)}/{len(inst_means)} instances (trimmed {trimmed}) split by category"
                )
            else:
                keep_instances = _keep_from_group(inst_means)
                trimmed = len(inst_means) - len(keep_instances)
                print(
                    f"[PDSScaling] trim_top_percent={trim_pct:g}% (x={x_mode}): kept {len(keep_instances)}/{len(inst_means)} instances (trimmed {trimmed})"
                )

        n_plotted = 0
        n_skipped_x_bound = 0
        plotted_x_values: List[float] = []
        plotted_y_values: List[float] = []
        for inst, pts in self.scaling_results.items():
            if keep_instances is not None and inst not in keep_instances:
                continue
            inst_cat = str(self.category_by_instance.get(inst, self.config.category) or "").strip().lower()
            if not inst_cat:
                inst_cat = "unknown"
            color = color_map.get(inst_cat, None) if is_multi_cat else None
            label = None
            if is_multi_cat and inst_cat not in labeled:
                label = inst_cat
                labeled.add(inst_cat)

            if x_mode == "K":
                ks = [p.K for p in pts]
                rs = [p.y_value for p in pts]
                if self.config.log_x or self.config.log_y:
                    pairs_k = []
                    for k_v, r_v in zip(ks, rs):
                        if self.config.log_x and k_v <= 0:
                            continue
                        if self.config.log_y and r_v <= 0:
                            continue
                        pairs_k.append((k_v, r_v))
                    ks = [t[0] for t in pairs_k]
                    rs = [t[1] for t in pairs_k]
                    if not ks:
                        continue
                if x_bound is not None and (not ks or max(ks) < x_bound):
                    n_skipped_x_bound += 1
                    continue
                n_plotted += 1
                for p in pts:
                    if p.K > 0:
                        per_k.setdefault(p.K, []).append(p.y_value)
                        per_k_by_cat.setdefault(inst_cat, {}).setdefault(p.K, []).append(p.y_value)
                if getattr(self.config, "plot_dots", False):
                    plt.scatter(ks, rs, alpha=0.25, s=12, color=color, label=label)
                else:
                    plt.plot(ks, rs, alpha=0.25, linewidth=1, color=color, label=label)
                plotted_x_values.extend(float(v) for v in ks)
                plotted_y_values.extend(float(v) for v in rs)
                continue

            info_by_k = _load_cnf_info_results_by_k(inst) if x_mode in ("n", "proofsize", "solvingtime") else {}
            pairs: List[Tuple[float, float]] = []
            for p in pts:
                if x_mode == "proofdoor_size":
                    if p.proofdoor_size <= 0:
                        continue
                    x_val = float(p.proofdoor_size)
                elif x_mode == "solvingtime":
                    row = info_by_k.get(int(p.K))
                    solve_time = _extract_solvingtime_from_info_row(row)
                    if solve_time is None:
                        continue
                    x_val = float(solve_time)
                else:
                    row = info_by_k.get(int(p.K))
                    if not row:
                        continue
                    parsed = _parse_int(row.get(x_mode))
                    if parsed is None:
                        continue
                    x_val = float(parsed)
                if self.config.log_x and x_val <= 0:
                    continue
                if self.config.log_y and float(p.y_value) <= 0:
                    continue
                pairs.append((float(x_val), float(p.y_value)))
            if not pairs:
                continue
            pairs.sort(key=lambda t: t[0])
            xs = [t[0] for t in pairs]
            rs = [t[1] for t in pairs]
            if x_bound is not None and max(xs) < x_bound:
                n_skipped_x_bound += 1
                continue
            n_plotted += 1
            all_xy_pairs.extend(pairs)
            all_xy_pairs_by_cat.setdefault(inst_cat, []).extend(pairs)
            if getattr(self.config, "plot_dots", False):
                plt.scatter(xs, rs, alpha=0.25, s=12, color=color, label=label)
            else:
                plt.plot(xs, rs, alpha=0.25, linewidth=1, color=color, label=label)
            plotted_x_values.extend(float(v) for v in xs)
            plotted_y_values.extend(float(v) for v in rs)

        max_x_vals: Optional[List[float]] = None
        max_y_vals: Optional[List[float]] = None
        mean_x_vals: Optional[List[float]] = None
        mean_y_vals: Optional[List[float]] = None
        draw_max = getattr(self.config, "plot_max", False) or x_bound is not None
        draw_mean = getattr(self.config, "plot_mean", False)
        if x_mode == "K" and per_k:
            if draw_mean:
                if is_multi_cat and per_k_by_cat:
                    labels_sorted = sorted(per_k_by_cat.keys(), key=lambda k: (k != "linear", k))
                    for label_name in labels_sorted:
                        cat_per_k = per_k_by_cat.get(label_name, {})
                        if not cat_per_k:
                            continue
                        mean_ks_cat = sorted(cat_per_k.keys())
                        mean_rs_cat = [sum(cat_per_k[k]) / len(cat_per_k[k]) for k in mean_ks_cat]
                        plt.plot(
                            mean_ks_cat,
                            mean_rs_cat,
                            color=color_map.get(label_name, "black"),
                            linewidth=2.5,
                            label=f"mean {label_name} ({_y_short_name(self._y_mode)})",
                        )
                else:
                    mean_ks = sorted(per_k.keys())
                    mean_rs = [sum(per_k[k]) / len(per_k[k]) for k in mean_ks]
                    plt.plot(mean_ks, mean_rs, color="black", linewidth=2.5, label=f"mean ({_y_short_name(self._y_mode)})")
                    mean_x_vals = [float(k) for k in mean_ks]
                    mean_y_vals = [float(v) for v in mean_rs]
            if draw_max:
                mean_ks = sorted(per_k.keys())
                max_rs = [max(per_k[k]) for k in mean_ks]
                plt.plot(mean_ks, max_rs, color="red", linewidth=2, linestyle="--", label=f"max ({_y_short_name(self._y_mode)})")
                max_x_vals = [float(k) for k in mean_ks]
                max_y_vals = [float(v) for v in max_rs]
        elif (x_mode in ("n", "proofsize", "solvingtime", "proofdoor_size")) and all_xy_pairs:
            x_to_ys: Dict[float, List[float]] = {}
            for xv, yv in all_xy_pairs:
                x_to_ys.setdefault(float(xv), []).append(float(yv))
            if draw_mean:
                if is_multi_cat and all_xy_pairs_by_cat:
                    labels_sorted = sorted(all_xy_pairs_by_cat.keys(), key=lambda k: (k != "linear", k))
                    for label_name in labels_sorted:
                        pairs_cat = all_xy_pairs_by_cat.get(label_name, [])
                        if not pairs_cat:
                            continue
                        x_to_ys_cat: Dict[float, List[float]] = {}
                        for xv, yv in pairs_cat:
                            x_to_ys_cat.setdefault(float(xv), []).append(float(yv))
                        x_vals_cat = sorted(x_to_ys_cat.keys())
                        mean_ys_cat = [sum(x_to_ys_cat[x]) / len(x_to_ys_cat[x]) for x in x_vals_cat]
                        plt.plot(
                            x_vals_cat,
                            mean_ys_cat,
                            color=color_map.get(label_name, "black"),
                            linewidth=2.5,
                            label=f"mean {label_name} ({_y_short_name(self._y_mode)})",
                        )
                else:
                    x_vals = sorted(x_to_ys.keys())
                    mean_ys = [sum(x_to_ys[x]) / len(x_to_ys[x]) for x in x_vals]
                    plt.plot(x_vals, mean_ys, color="black", linewidth=2.5, label=f"mean ({_y_short_name(self._y_mode)})")
                    mean_x_vals = list(x_vals)
                    mean_y_vals = list(mean_ys)
            if draw_max:
                x_vals = sorted(x_to_ys.keys())
                max_ys = [max(x_to_ys[x]) for x in x_vals]
                plt.plot(x_vals, max_ys, color="red", linewidth=2, linestyle="--", label=f"max ({_y_short_name(self._y_mode)})")
                max_x_vals = list(x_vals)
                max_y_vals = list(max_ys)
        if max_x_vals is not None and max_y_vals is not None:
            if getattr(self.config, "plot_max_regression", True):
                self._plot_aggregate_fits(
                    plt,
                    max_x_vals,
                    max_y_vals,
                    tag="max",
                    mode=getattr(self.config, "max_regression_mode", "both"),
                )
        if mean_x_vals is not None and mean_y_vals is not None:
            self._plot_aggregate_fits(plt, mean_x_vals, mean_y_vals, tag="mean", mode="both")

        if x_bound is not None and n_skipped_x_bound > 0:
            print(f"[PDSScaling] x_bound={x_bound:g}: kept {n_plotted} instances, skipped {n_skipped_x_bound} (max(x) < x_bound)")

        x_label = _x_axis_label(x_mode)
        plt.xlabel(x_label)
        _unit = getattr(self.config, "interpolant_unit", "bits")
        plt.ylabel(_y_axis_label(self._y_mode, _unit))
        if self.config.log_x:
            plt.xscale("log")
        if self.config.log_y:
            plt.yscale("log")
        title = f"{_y_axis_label(self._y_mode, _unit)} vs {x_label} ({self.config.category})"
        if trim_pct > 0.0:
            title += f", trim top {trim_pct:g}%"
        if self.config.log_x or self.config.log_y:
            if self.config.log_x and self.config.log_y:
                title += ", log-log"
            elif self.config.log_x:
                title += ", log-x"
            else:
                title += ", log-y"
        if x_bound is not None:
            title += f", x>={x_bound:g}"
        plt.title(title)
        plt.grid(True, alpha=0.3)
        if (x_mode == "K" and per_k) or (x_mode in ("n", "proofsize", "solvingtime", "proofdoor_size") and all_xy_pairs) or is_multi_cat:
            plt.legend()
        # Make lower bounds match the plotted data minimums.
        if plotted_x_values:
            plt.xlim(left=min(plotted_x_values))
        if plotted_y_values:
            plt.ylim(bottom=min(plotted_y_values))
        plt.tight_layout()
        plt.savefig(self.scaling_plot_path, dpi=200)
        plt.close()
        self.logger.info("Wrote plot %s", self.scaling_plot_path)
        print(f"[PDSScaling] wrote plot:         {self.scaling_plot_path}")

    def _plot_aggregate_fits(
        self,
        plt,
        x_vals: List[float],
        y_vals: List[float],
        tag: str = "max",
        mode: str = "both",
    ) -> None:
        """Fit an aggregate line (max or mean) with linear/log curves and plot R^2 in legend."""
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            return
        x = np.array(x_vals, dtype=float)
        y = np.array(y_vals, dtype=float)
        if len(x) < 3:
            return

        def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
            ss_res = float(np.sum((y_true - y_pred) ** 2))
            ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
            if ss_tot <= 0:
                return float("nan")
            return 1.0 - ss_res / ss_tot

        lin_color = "green" if tag == "max" else "dodgerblue"
        log_color = "purple" if tag == "max" else "darkorange"

        x_line = np.linspace(float(np.min(x)), float(np.max(x)), 200)

        mode_norm = (mode or "both").strip().lower()
        if mode_norm not in ("both", "linear", "log"):
            mode_norm = "both"

        if mode_norm in ("both", "linear"):
            coeffs_lin = np.polyfit(x, y, deg=1)
            y_hat_lin = np.polyval(coeffs_lin, x)
            r2_lin = r2_score(y, y_hat_lin)
            plt.plot(
                x_line,
                np.polyval(coeffs_lin, x_line),
                linewidth=1.5,
                color=lin_color,
                linestyle="-",
                label=f"{tag} linear (r2={r2_lin:.4f})",
            )

        mask = x > 0
        if mode_norm in ("both", "log") and np.any(mask):
            x_pos = x[mask]
            y_pos = y[mask]
            if len(x_pos) >= 3:
                logx = np.log(x_pos)
                coeffs_log = np.polyfit(logx, y_pos, deg=1)
                y_hat_log = np.polyval(coeffs_log, logx)
                r2_log = r2_score(y_pos, y_hat_log)
                x_line_pos = x_line[x_line > 0]
                if len(x_line_pos) > 0:
                    plt.plot(
                        x_line_pos,
                        np.polyval(coeffs_log, np.log(x_line_pos)),
                        linewidth=1.5,
                        color=log_color,
                        linestyle="-",
                        label=f"{tag} log (r2={r2_log:.4f})",
                    )

    def _plot_fit_lines(self, xs: List[int], ys: List[float], plt) -> None:
        mode = (self.config.fit_mode or "none").strip().lower()
        if mode in ("none", "off", "false", "0"):
            return
        try:
            import numpy as np  # type: ignore
        except ModuleNotFoundError:
            self.logger.info("numpy not installed; skip fitting.")
            print("[PDSScaling] numpy not installed; skip fitting.")
            return

        x = np.array(xs, dtype=float)
        y = np.array(ys, dtype=float)
        if len(x) < 3:
            self.logger.info("Not enough points for fitting.")
            print("[PDSScaling] not enough points for fitting.")
            return

        def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
            ss_res = float(np.sum((y_true - y_pred) ** 2))
            ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
            if ss_tot <= 0:
                return float("nan")
            return 1.0 - ss_res / ss_tot

        def plot_linear() -> None:
            coeffs = np.polyfit(x, y, deg=1)
            y_hat = np.polyval(coeffs, x)
            r2 = r2_score(y, y_hat)
            x_line = np.linspace(float(np.min(x)), float(np.max(x)), 200)
            y_line = np.polyval(coeffs, x_line)
            plt.plot(x_line, y_line, linewidth=2, label=f"linear (r2={r2:.4f})")
            print(f"[PDSScaling] linear r2={r2:.6f}")

        def plot_poly4() -> None:
            coeffs = np.polyfit(x, y, deg=4)
            y_hat = np.polyval(coeffs, x)
            r2 = r2_score(y, y_hat)
            x_line = np.linspace(float(np.min(x)), float(np.max(x)), 200)
            y_line = np.polyval(coeffs, x_line)
            plt.plot(x_line, y_line, linewidth=2, label=f"poly4 (r2={r2:.4f})")
            print(f"[PDSScaling] poly4 r2={r2:.6f}")

        def plot_exponential() -> None:
            mask = y > 0
            if not np.any(mask):
                print("[PDSScaling] exponential fit skipped (no positive y).")
                return
            x_pos = x[mask]
            y_pos = y[mask]
            logy = np.log(y_pos)
            coeffs = np.polyfit(x_pos, logy, deg=1)
            a = coeffs[0]
            b = coeffs[1]
            y_hat = np.exp(a * x_pos + b)
            r2 = r2_score(y_pos, y_hat)
            x_line = np.linspace(float(np.min(x_pos)), float(np.max(x_pos)), 200)
            y_line = np.exp(a * x_line + b)
            plt.plot(x_line, y_line, linewidth=2, label=f"exp (r2={r2:.4f})")
            print(f"[PDSScaling] exp r2={r2:.6f}")

        if mode in ("linear", "lin"):
            plot_linear()
        elif mode in ("poly4", "poly", "polynomial", "degree4", "deg4"):
            plot_poly4()
        elif mode in ("exp", "exponential"):
            plot_exponential()
        elif mode in ("all", "both", "full"):
            plot_linear()
            plot_poly4()
            plot_exponential()

        if mode not in ("none", "off", "false", "0"):
            plt.legend()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=str, default="all")
    parser.add_argument("--force_instance", type=str, default=None)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--pddef", type=int, default=1)
    group.add_argument(
        "--y",
        type=str,
        default=None,
        choices=["pds", "pgs", "pdsdfs", "pgsdfs", "proofsize", "avg_dependence", "max_dependence", "solvingtime", "max_interpolant", "avg_interpolant"],
        help="Y axis metric. max_interpolant->max interpolant size; avg_interpolant->mean interpolant size; use --interpolant_unit to switch bits/clauses.",
    )
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--allow_partial_smt2cnf", action="store_true", default=False)
    parser.add_argument(
        "--x",
        type=str,
        default="K",
        choices=["K", "proofsize", "n", "solvingtime", "proofdoor_size"],
        help="X axis for plots: K|proofsize|n|solvingtime|proofdoor_size (proofsize/n/time from cnf info json; proofdoor_size from this experiment, bits). For --fixed_k, K falls back to formula_size_bits.",
    )
    parser.add_argument(
        "--fixed_k",
        type=int,
        default=None,
        help="If set, only compute for this K and plot ratio vs formula size in bits (scatter).",
    )
    parser.add_argument(
        "--x_bound",
        type=float,
        default=None,
        help="When K is not fixed: only show instances whose data extends to x >= this bound (by max x for the chosen --x).",
    )
    parser.add_argument(
        "--no_max_regression",
        action="store_true",
        default=False,
        help="If set, do not draw regression fit lines for the red 'max' curve (only affects plots with --x_bound).",
    )
    parser.add_argument(
        "--max_regression_mode",
        type=str,
        default="both",
        choices=["both", "linear", "log"],
        help="Regression lines for max curve when enabled: both|linear|log.",
    )
    parser.add_argument(
        "--interpolant_unit",
        type=str,
        default="bits",
        choices=["bits", "clauses"],
        help="Unit for interpolant size: bits (theoretical_bits_smtcnf) or clauses (line count).",
    )
    parser.add_argument(
        "--use_summary_instances",
        action="store_true",
        default=False,
        help="If set, load instance list from summary CSV (category filter applied).",
    )
    parser.add_argument(
        "--trim_top_percent",
        type=float,
        default=0.0,
        help="Drop the highest proofdoor sizes by this percent when plotting fixed-K scatter.",
    )
    parser.add_argument(
        "--dot",
        action="store_true",
        default=False,
        help="Force scatter/dot plot for scaling curves (per-instance points instead of lines).",
    )
    parser.add_argument(
        "--mean",
        action="store_true",
        default=False,
        help="Draw the mean (average y per x) line on scaling plot.",
    )
    parser.add_argument(
        "--max",
        action="store_true",
        default=False,
        help="Draw the max (max y per x) line on scaling plot with log regression fit and R2.",
    )
    parser.add_argument(
        "--logx",
        action="store_true",
        default=False,
        help="Use logarithmic scale on x axis.",
    )
    parser.add_argument(
        "--logy",
        action="store_true",
        default=False,
        help="Use logarithmic scale on y axis.",
    )
    parser.add_argument(
        "--fit",
        type=str,
        default="none",
        help="Fit lines on fixed-K scatter: none|linear|poly4|exp|all.",
    )
    parser.add_argument(
        "--missing",
        action="store_true",
        default=False,
        help="If set, print (instance,K) pairs from input selection where proofdoor size is missing.",
    )
    parser.add_argument(
        "--read_pds_from_source",
        action="store_true",
        default=False,
        help="If set and the current plot needs proofdoor_size, repair missing cached proofdoor_size values by rereading interpolant_as_cnfs and recomputing bits.",
    )
    parser.add_argument(
        "--output_dashboard",
        type=str,
        default=None,
        help="If set, write a minimal dashboard CSV (7 columns).",
    )
    parser.add_argument(
        "--dashboard_k",
        type=int,
        default=None,
        help="If set, only output this K in the dashboard CSV; otherwise output all inferred K values per instance.",
    )
    parser.add_argument(
        "--dashboard_merge_categories",
        action="store_true",
        default=False,
        help="If set, merge exponential+linear into a single dashboard CSV (uses --summary_csv_linear/--summary_csv_exponential).",
    )
    parser.add_argument(
        "--summary_csv_linear",
        type=str,
        default="linear.scaling.csv",
        help="Summary CSV for the linear category (used when --dashboard_merge_categories).",
    )
    parser.add_argument(
        "--summary_csv_exponential",
        type=str,
        default="exponential.scaling.csv",
        help="Summary CSV for the exponential category (used when --dashboard_merge_categories).",
    )
    parser.add_argument(
        "--summary_csv",
        type=str,
        default="regression_summary.csv",
        help="CSV used to infer available K values (supports regression_summary.csv or *.scaling*.csv with a K column).",
    )
    parser.add_argument(
        "--output_suffix",
        type=str,
        default=None,
        help="Suffix for result/plot filenames (e.g. scalingtonSN). If not set and summary_csv is scalington.csv, uses scalingtonSN.",
    )
    parser.add_argument(
        "--summary_done_only",
        action="store_true",
        default=False,
        help="If set and summary has smt2cnf_status, ONLY keep rows with smt2cnf_status == 'done' when inferring K.",
    )
    parser.add_argument(
        "--prepare_only",
        action="store_true",
        default=False,
        help="If set, only prepare the data and exit.",
    )
    args = parser.parse_args()

    # Derive pddef and y mode.
    y_mode = "pds"
    effective_pddef = int(args.pddef)
    if args.y is not None:
        y_mode = str(args.y).strip().lower()
        if y_mode == "pds":
            effective_pddef = 1
        elif y_mode == "pgs":
            effective_pddef = 3
        elif y_mode == "pdsdfs":
            effective_pddef = 1
        elif y_mode == "pgsdfs":
            effective_pddef = 3
        elif y_mode == "proofsize":
            effective_pddef = 1  # not used; keep stable default for other paths
        elif y_mode == "solvingtime":
            effective_pddef = int(args.pddef)  # not used for y, keep user-specified value stable
        elif y_mode in ("avg_dependence", "max_dependence"):
            effective_pddef = int(args.pddef)  # interpolant_dependence_pddef_{pddef}/
        elif y_mode in ("max_interpolant", "avg_interpolant"):
            effective_pddef = int(args.pddef)  # interpolant_as_cnfs_{pddef}/
        else:
            y_mode = "pds"
            effective_pddef = int(args.pddef)

    if args.prepare_only:
        prepare_data(args.summary_csv)
        return

    output_suffix = (args.output_suffix or "").strip() or None
    if output_suffix is None and args.summary_csv:
        # By default, bind cache/plot/result filenames to the input summary CSV.
        base_no_ext = os.path.splitext(os.path.basename(args.summary_csv))[0].strip().lower()
        if base_no_ext:
            # Keep suffix filesystem-friendly and deterministic.
            safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in base_no_ext).strip("_")
            output_suffix = safe or None

    # Standalone merged dashboard output (doesn't need to run the Experiment pipeline).
    if args.output_dashboard and args.dashboard_merge_categories:
        if y_mode in ("proofsize", "avg_dependence", "max_dependence"):
            raise ValueError(f"--y {y_mode} is not compatible with --output_dashboard (dashboard uses smtcnf sizes).")
        write_merged_minimal_dashboard_csv(
            out_path=args.output_dashboard,
            summary_csv_linear=args.summary_csv_linear,
            summary_csv_exponential=args.summary_csv_exponential,
            done_only=args.summary_done_only,
            force_instance=args.force_instance,
            dashboard_k=args.dashboard_k,
            pddef=effective_pddef,
            reverse=args.reverse,
        )
        return

    config = PDSScalingExperimentConfig(
        name="pds_scaling",
        data_dir="data",
        result_dir="result",
        log_dir="log",
        category=args.category,
        force_instance=args.force_instance,
        pddef=effective_pddef,
        reverse=args.reverse,
        require_complete_smt2cnf=(not args.allow_partial_smt2cnf),
        summary_csv_path=args.summary_csv,
        summary_done_only=args.summary_done_only,
        output_dashboard_csv=args.output_dashboard,
        dashboard_k=args.dashboard_k,
        dashboard_merge_categories=args.dashboard_merge_categories,
        summary_csv_linear=args.summary_csv_linear,
        summary_csv_exponential=args.summary_csv_exponential,
        fixed_k=args.fixed_k,
        use_summary_instances=(args.use_summary_instances or args.fixed_k is not None),
        trim_top_percent=args.trim_top_percent,
        fit_mode=args.fit,
        x_axis=args.x,
        y_axis=y_mode,
        output_suffix=output_suffix,
        plot_dots=args.dot,
        x_bound=args.x_bound,
        plot_mean=args.mean,
        plot_max=getattr(args, "max", False),
        log_x=args.logx,
        log_y=args.logy,
        missing_report=args.missing,
        read_pds_from_source=args.read_pds_from_source,
        plot_max_regression=(not args.no_max_regression),
        max_regression_mode=args.max_regression_mode,
        interpolant_unit=getattr(args, "interpolant_unit", "bits"),
    )
    experiment = PDSScalingExperiment(config)
    experiment.run()


if __name__ == "__main__":
    main()
