import argparse
import csv
import json
import os
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Set, Iterable

from experiments.experiment import Experiment, ExperimentConfig
from utils.catagory import get_instance_list
from utils.paths import get_CNF_dir, get_figures_dir, get_interpolant_cnf_dir


def _parse_int(s: object) -> Optional[int]:
    try:
        return int(str(s).strip())
    except Exception:
        return None


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
        cat_col = "category" if "category" in cols else ("best_model" if "best_model" in cols else None)

        for row in reader:
            inst = (row.get("instance_name") or "").strip()
            if not inst or inst in seen:
                continue

            if category_norm != "all" and cat_col is not None:
                raw = (row.get(cat_col) or "").strip().lower()
                raw = "none" if raw == "none" else raw
                if raw != category_norm:
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


def compute_formula_size(instance: str, K: int) -> int:
    cnf_path = os.path.join(get_CNF_dir(K), f"{instance}.{K}.cnf")
    header = _read_dimacs_header_clause_count(cnf_path)
    return header if header is not None else _count_dimacs_clauses(cnf_path)


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
    return sum(_count_nonempty_lines(p) for p in paths)


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

    instances = sorted(set(lin_instances) | set(exp_instances))
    category_by_instance: Dict[str, str] = {inst: "linear" for inst in lin_instances}
    category_by_instance.update({inst: "exponential" for inst in exp_instances})

    merged_ks: Dict[str, List[int]] = {}
    for inst in instances:
        ks = set(lin_ks.get(inst, [])) | set(exp_ks.get(inst, []))
        merged_ks[inst] = sorted(ks)

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

    @property
    def ratio(self) -> float:
        return (self.proofdoor_size / self.formula_size) if self.formula_size > 0 else float("nan")

    def to_dict(self) -> Dict:
        return {
            "K": self.K,
            "formula_size": self.formula_size,
            "proofdoor_size": self.proofdoor_size,
            "ratio": self.ratio,
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

        if self.use_summary_instances:
            self.instance_list = load_instances_from_summary(self.summary_csv_path, category=category)
        else:
            self.instance_list = get_instance_list(category)
            if not self.instance_list:
                self.instance_list = load_instances_from_summary(self.summary_csv_path, category=category)
        if force_instance is not None:
            self.instance_list = [force_instance]


class PDSScalingExperiment(Experiment):
    def __init__(self, config: PDSScalingExperimentConfig):
        super().__init__(config)
        self.config = config
        self.scaling_results: Dict[str, List[ScalingPoint]] = {}
        self.available_ks: Dict[str, List[int]] = {}

        pddef_suffix = f"_pddef{self.config.pddef}"
        self.scaling_results_json_path = os.path.join(
            self.config.result_dir, f"pds_scaling_results{pddef_suffix}.json"
        )
        self.scaling_results_csv_path = os.path.join(
            self.config.result_dir, f"pds_scaling_results{pddef_suffix}.csv"
        )
        if self.config.fixed_k is not None:
            self.scaling_plot_path = os.path.join(
                get_figures_dir(),
                f"pds_scaling_{self.config.category}_K{self.config.fixed_k}{pddef_suffix}.png",
            )
        else:
            self.scaling_plot_path = os.path.join(
                get_figures_dir(), f"pds_scaling_{self.config.category}{pddef_suffix}.png"
            )

    def on_start(self):
        # We don't schedule jobs here; this experiment only reads existing artifacts and summarizes them.
        pass

    def on_end(self):
        pass

    def experiment_main(self):
        self.manage()
        self.end()

    def _compute_instance_scaling(self, instance: str) -> List[ScalingPoint]:
        points: List[ScalingPoint] = []
        for K in self.available_ks.get(instance, []):
            formula_size = compute_formula_size(instance, K)
            if formula_size == 0:
                # CNF missing/empty, skip
                continue

            complete, smtcnf_paths = smt2cnf_paths_complete(
                instance, K, pddef=self.config.pddef, reverse=self.config.reverse
            )
            if self.config.require_complete_smt2cnf and not complete:
                continue

            # If not requiring completeness, allow partial but count only existing/non-empty ones
            usable_paths = (
                smtcnf_paths
                if complete
                else [p for p in smtcnf_paths if os.path.exists(p) and os.path.getsize(p) > 0]
            )
            if not usable_paths:
                continue

            proofdoor_size = compute_proofdoor_size_from_smtcnfs(usable_paths)
            if proofdoor_size == 0:
                continue
            points.append(ScalingPoint(K=K, formula_size=formula_size, proofdoor_size=proofdoor_size))
        return points

    def manage(self):
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

        for instance in self.config.instance_list:
            pts = self._compute_instance_scaling(instance)
            if pts:
                self.scaling_results[instance] = pts

        self._save_scaling_results()
        self._write_dashboard_csv_if_requested()
        self._plot_scaling_results()

    def _write_dashboard_csv_if_requested(self) -> None:
        out_path = (self.config.output_dashboard_csv or "").strip()
        if not out_path:
            return

        # Minimal schema requested by user.
        category_by_instance = {inst: self.config.category for inst in self.config.instance_list}
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

    def _save_scaling_results(self) -> None:
        os.makedirs(self.config.result_dir, exist_ok=True)

        payload = {
            "category": self.config.category,
            "pddef": self.config.pddef,
            "reverse": self.config.reverse,
            "require_complete_smt2cnf": self.config.require_complete_smt2cnf,
            "summary_csv_path": self.config.summary_csv_path,
            "summary_done_only": self.config.summary_done_only,
            "instances": {
                inst: [p.to_dict() for p in pts] for inst, pts in sorted(self.scaling_results.items())
            },
        }
        with open(self.scaling_results_json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        with open(self.scaling_results_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["instance_name", "K", "formula_size", "proofdoor_size", "ratio"],
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
                            "ratio": p.ratio,
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
            return

        if not self.scaling_results:
            self.logger.info("No scaling results; skip plotting.")
            return

        os.makedirs(os.path.dirname(self.scaling_plot_path), exist_ok=True)

        if self.config.fixed_k is not None:
            # Scatter: PDS size vs formula size for a fixed K.
            xs: List[int] = []
            ys: List[int] = []
            for pts in self.scaling_results.values():
                for p in pts:
                    if p.formula_size > 0 and p.proofdoor_size > 0:
                        xs.append(p.formula_size)
                        ys.append(p.proofdoor_size)

            if not xs:
                self.logger.info("No valid points for plotting; skip plot.")
                return

            trim_pct = max(0.0, min(100.0, float(self.config.trim_top_percent or 0.0)))
            if trim_pct > 0.0:
                keep_n = max(1, int(round(len(xs) * (1.0 - trim_pct / 100.0))))
                # Sort by PDS size (y) descending and keep the smallest keep_n points.
                combined = sorted(zip(xs, ys), key=lambda t: t[1], reverse=True)
                kept = combined[-keep_n:] if keep_n < len(combined) else combined
                xs, ys = [k[0] for k in kept], [k[1] for k in kept]

            plt.figure(figsize=(10, 6))
            plt.scatter(xs, ys, alpha=0.6, s=18)
            plt.xlabel("Formula size (#clauses)")
            plt.ylabel("PDS size")
            plt.title(f"PDS size vs formula size (K={self.config.fixed_k}, {self.config.category})")
            plt.grid(True, alpha=0.3)
            self._plot_fit_lines(xs, ys, plt)
            plt.tight_layout()
            plt.savefig(self.scaling_plot_path, dpi=200)
            plt.close()
            self.logger.info("Wrote plot %s", self.scaling_plot_path)
            print(f"[PDSScaling] wrote plot:         {self.scaling_plot_path}")
            return

        # Plot: per-instance ratio curve (light), and mean ratio per K (bold).
        per_k: Dict[int, List[float]] = {}
        plt.figure(figsize=(10, 6))

        for inst, pts in self.scaling_results.items():
            ks = [p.K for p in pts]
            rs = [p.ratio for p in pts]
            for p in pts:
                if p.formula_size > 0:
                    per_k.setdefault(p.K, []).append(p.ratio)
            plt.plot(ks, rs, alpha=0.25, linewidth=1)

        mean_ks = sorted(per_k.keys())
        mean_rs = [sum(per_k[k]) / len(per_k[k]) for k in mean_ks]
        plt.plot(mean_ks, mean_rs, color="black", linewidth=2.5, label="mean ratio")

        plt.xlabel("K")
        plt.ylabel("PDS size / formula size")
        plt.title(f"PDS scaling ({self.config.category})")
        plt.grid(True, alpha=0.3)
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.scaling_plot_path, dpi=200)
        plt.close()
        self.logger.info("Wrote plot %s", self.scaling_plot_path)
        print(f"[PDSScaling] wrote plot:         {self.scaling_plot_path}")

    def _plot_fit_lines(self, xs: List[int], ys: List[int], plt) -> None:
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
    parser.add_argument("--pddef", type=int, default=1)
    parser.add_argument("--reverse", action="store_true", default=False)
    parser.add_argument("--allow_partial_smt2cnf", action="store_true", default=False)
    parser.add_argument(
        "--fixed_k",
        type=int,
        default=None,
        help="If set, only compute for this K and plot ratio vs formula size (scatter).",
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
        help="Drop the highest PDS sizes by this percent when plotting fixed-K scatter.",
    )
    parser.add_argument(
        "--fit",
        type=str,
        default="none",
        help="Fit lines on fixed-K scatter: none|linear|poly4|exp|all.",
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

    if args.prepare_only:
        prepare_data(args.summary_csv)
        return

    # Standalone merged dashboard output (doesn't need to run the Experiment pipeline).
    if args.output_dashboard and args.dashboard_merge_categories:
        write_merged_minimal_dashboard_csv(
            out_path=args.output_dashboard,
            summary_csv_linear=args.summary_csv_linear,
            summary_csv_exponential=args.summary_csv_exponential,
            done_only=args.summary_done_only,
            force_instance=args.force_instance,
            dashboard_k=args.dashboard_k,
            pddef=args.pddef,
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
        pddef=args.pddef,
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
    )
    experiment = PDSScalingExperiment(config)
    experiment.run()


if __name__ == "__main__":
    main()