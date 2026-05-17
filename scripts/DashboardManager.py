NOT_STARTED = "not started"
NOT_AVAILABLE = "not available"
from utils.catagory import get_instance_list
import numpy as np
from datetime import datetime
import csv
import argparse
from utils.paths import (
    get_CNF_dir,
    get_interpolant_cnf_dir,
    get_absorption_experiments_dir,
    get_solving_time_dir,
)
from utils.utils import GetDataFromLog
import os
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple
from utils.process_cnf import CNF
import gc
import threading

REGRESSION_SUMMARY_PATH = "./regression_summary.csv"


def load_categories() -> Dict[str, str]:
    """Load instance → best_model category from regression_summary.csv."""
    cats: Dict[str, str] = {}
    with open(REGRESSION_SUMMARY_PATH, newline="") as f:
        for row in csv.DictReader(f):
            cats[row["instance_name"]] = row["best_model"] or "unknown"
    return cats


def _collect_interpolant_indices(directory: str) -> Dict[str, set]:
    """Return {instance_name: set_of_completed_indices} for a given directory.

    Files are expected to be named name.K.idx.interpolant.
    """
    from collections import defaultdict
    indices: Dict[str, set] = defaultdict(set)
    if not os.path.isdir(directory):
        return indices
    for fn in os.listdir(directory):
        if not fn.endswith(".interpolant"):
            continue
        stem = fn[: -len(".interpolant")]
        parts = stem.split(".")
        # expect exactly 3 parts: name, K, idx
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            indices[parts[0]].add(int(parts[2]))
    return indices


def _consecutive_from_zero(index_set: set) -> int:
    """Return the length of the consecutive run starting from index 0."""
    i = 0
    while i in index_set:
        i += 1
    return i  # number of consecutive indices: 0,1,...,i-1


def _collect_smtcnf_indices(directory: str) -> Dict[str, set]:
    """Return {instance_name: set_of_completed_indices} for a given smtcnf directory.

    Only counts files matching name.K.idx.smtcnf (no extra dots in the stem).
    """
    from collections import defaultdict
    indices: Dict[str, set] = defaultdict(set)
    if not os.path.isdir(directory):
        return indices
    for fn in os.listdir(directory):
        if not fn.endswith(".smtcnf"):
            continue
        stem = fn[: -len(".smtcnf")]
        parts = stem.split(".")
        # expect exactly 3 parts: name, K, idx
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            indices[parts[0]].add(int(parts[2]))
    return indices


def print_stats() -> None:
    cats = load_categories()

    # ── Q1: total families (= total AIG instances) ───────────────────────────
    print(f"Q1  总 family 数: {len(cats)}")

    # ── Q2: counts per category ───────────────────────────────────────────────
    from collections import Counter
    cat_counts = Counter(cats.values())
    print(f"Q2  linear:      {cat_counts.get('linear', 0)}")
    print(f"    exponential: {cat_counts.get('exponential', 0)}")
    print(f"    polynomial:  {cat_counts.get('polynomial', 0)}")
    print(f"    unknown/None:{cat_counts.get('unknown', 0) + cat_counts.get('None', 0)}")

    # ── Q3: linear, k=10, pddef=1, fully computed ────────────────────────────
    K = 10
    smtcnf_dir = f"./ProofDoorBenchmark/interpolant_as_cnfs_1/{K}"
    smtcnf_idx = _collect_smtcnf_indices(smtcnf_dir)
    q3 = sum(
        1 for name, idx_set in smtcnf_idx.items()
        if len(idx_set) >= K and cats.get(name) == "linear"
    )
    print(f"Q3  linear, k=10, pddef=1, 完整完成: {q3}")

    # ── Q3b: exponential, pddef=1, any k, fully computed (unique name) ───────
    base1 = "./ProofDoorBenchmark/interpolant_as_cnfs_1"
    success_exp_pd1: set = set()
    if os.path.isdir(base1):
        for k_str in os.listdir(base1):
            if not k_str.isdigit():
                continue
            ki = int(k_str)
            idir = os.path.join(base1, k_str)
            for name, idx_set in _collect_smtcnf_indices(idir).items():
                if len(idx_set) >= ki and cats.get(name) == "exponential":
                    success_exp_pd1.add(name)
    print(f"Q3b exponential, 任意k, pddef=1, 完整完成 (唯一name): {len(success_exp_pd1)}")

    # ── Q4: pddef=5, any k, consecutive from index 0 past index 3 ───────────
    # Success = exists at least one K where indices 0,1,2,3 are all present.
    base5 = "./ProofDoorBenchmark/interpolants_def5"
    success_linear_pd5: set = set()
    success_exp_pd5: set = set()
    if os.path.isdir(base5):
        for k_str in os.listdir(base5):
            if not k_str.isdigit():
                continue
            idir = os.path.join(base5, k_str)
            for name, idx_set in _collect_interpolant_indices(idir).items():
                if _consecutive_from_zero(idx_set) > 3:
                    cat = cats.get(name, "")
                    if cat == "linear":
                        success_linear_pd5.add(name)
                    elif cat == "exponential":
                        success_exp_pd5.add(name)
    print(f"Q4  linear,      pddef=5, 任意k, 连续到index>3 (唯一name): {len(success_linear_pd5)}")
    print(f"    exponential, pddef=5, 任意k, 连续到index>3 (唯一name): {len(success_exp_pd5)}")

    # ── Q5: exponential, weakest PD (reverse-SPD negation), any k, fully computed
    # Output files: interpolant_as_cnfs_spd7/{K}/{name}.{K}.{i}.cnf
    base_spd7 = "./ProofDoorBenchmark/interpolant_as_cnfs_spd7"
    success_exp_wpd: set = set()
    if os.path.isdir(base_spd7):
        for k_str in os.listdir(base_spd7):
            if not k_str.isdigit():
                continue
            ki = int(k_str)
            idir = os.path.join(base_spd7, k_str)
            # collect index sets from name.K.idx.cnf files
            from collections import defaultdict as _dd
            idx_map: Dict[str, set] = _dd(set)
            for fn in os.listdir(idir):
                if not fn.endswith(".cnf"):
                    continue
                stem = fn[: -len(".cnf")]
                parts = stem.split(".")
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    idx_map[parts[0]].add(int(parts[2]))
            for name, idx_set in idx_map.items():
                if _consecutive_from_zero(idx_set) > 3 and cats.get(name) == "exponential":
                    success_exp_wpd.add(name)
    print(f"Q5  exponential, weakest PD (spd7 negation), 任意k, 连续到index>3 (唯一name): {len(success_exp_wpd)}")

def get_rss_mb():
    """
    Try to get current process RSS in MB. Falls back gracefully if unavailable.
    """
    try:
        import psutil  # type: ignore
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        try:
            import resource  # type: ignore
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # On Linux ru_maxrss is in KB; on macOS it's in bytes.
            # Heuristic: treat values < 10**7 as KB, otherwise bytes.
            return (rss / 1024.0) if rss < 10**7 else (rss / (1024.0 * 1024.0))
        except Exception:
            return -1.0

def log_mem(msg: str):
    mem_mb = get_rss_mb()
    if mem_mb >= 0:
        print(f"[MEM] {msg}: {mem_mb:.1f} MB", flush=True)
    else:
        print(f"[MEM] {msg}: unknown", flush=True)


class InstanceData:
    def __init__(self, name):
        self.name = name
        self.data = {}
        self.add_default_data()

    def add_default_data(self):
        self.data["instance_name"] = self.name
        self.data["category"] = NOT_STARTED
        self.data["cadical_solving_time"] = NOT_STARTED
        self.data["minisat_solving_time"] = NOT_STARTED
        self.data["formula_size"] = NOT_STARTED
        self.data["minisat_proof_size"] = NOT_STARTED
        self.data["proofdoor_size"] = NOT_STARTED
        self.data["proofdoor_expansion_status"] = NOT_STARTED

def fill_instance_data(instance_data):
    """
    Populate fields by reading raw files directly (no parsed summary JSON).
    """
    instance = instance_data.name
    K = 10
    print(f"[START] {instance} fill_instance_data", flush=True)
    log_mem(f"{instance} start")
    cnf_obj = CNF.from_file(f"{get_CNF_dir(K)}/{instance}.{K}.cnf")
    n_of_literals_in_formula_until_iteration = {}
    for i in range(K):
        n_of_literals_in_formula_until_iteration[i] = len(cnf_obj.literal_map[i])
    # release CNF object early
    del cnf_obj
    gc.collect()
    # 1) Formula size: number of clauses in CNF file
    try:
        cnf_path = f"{get_CNF_dir(K)}/{instance}.{K}.cnf"
        if os.path.exists(cnf_path) and os.path.getsize(cnf_path) > 0:
            clauses = 0
            header_count = None
            with open(cnf_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("c"):
                        continue
                    if line.startswith("p cnf"):
                        parts = line.split()
                        if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
                            header_count = int(parts[3])
                        continue
                    if line.endswith(" 0") or line.endswith(" 0\n") or line.endswith("\t0") or line == "0":
                        clauses += 1
            instance_data.data["formula_size"] = header_count if header_count is not None else clauses
            log_mem(f"{instance} after CNF parse (clauses={instance_data.data['formula_size']})")
    except Exception as e:
        instance_data.data["formula_size"] = NOT_AVAILABLE  
        print(f"Formula size not available for {instance}, error: {e}")
        pass

    # 2) ProofDoor size: sum of clauses across all interpolant CNF files
    smallest_interpolant_size = float('inf')
    largest_interpolant_size = 0
    instance_data.data["smallest_interpolant_size"] = "NA"
    instance_data.data["largest_interpolant_size"] = "NA"
    interpolant_size_list = []
    # stream variables across iterations to avoid retaining all sets in memory
    previous_vars_set = set()
    have_prev = False
    sum_shared_variables = 0
    ratios = []
    try:
        total_pd_clauses = 0
        expanded_count = 0
        for idx in range(K):
            smtcnf_path = f"{get_interpolant_cnf_dir(K,1)}/{instance}.{K}.{idx}.smtcnf"
            current_set = set()
            interpolant_size = 0
            if os.path.exists(smtcnf_path) and os.path.getsize(smtcnf_path) > 0:
                expanded_count += 1
                with open(smtcnf_path, "r") as f:
                    for line in f:
                        literals = line.split()
                        for literal in literals:
                            if literal != "0":
                                current_set.add(int(literal.replace('v', '').replace('Not(', '').replace(')', '')))
                        interpolant_size += 1
                if interpolant_size < smallest_interpolant_size:
                    smallest_interpolant_size = interpolant_size
                if interpolant_size > largest_interpolant_size:
                    largest_interpolant_size = interpolant_size
                interpolant_size_list.append(interpolant_size)
                # Each line is a clause listing literals separated by space
                total_pd_clauses += interpolant_size
            # streaming metrics
            if have_prev:
                sum_shared_variables += len(previous_vars_set & current_set)
            previous_vars_set = current_set
            have_prev = True
            num_lits_formula = n_of_literals_in_formula_until_iteration.get(idx, 0)
            if num_lits_formula > 0:
                ratios.append(len(current_set) / num_lits_formula)
            print(f"[INTERP] {instance} idx={idx} clauses={interpolant_size} vars={len(current_set)}", flush=True)
            log_mem(f"{instance} after interpolant idx={idx}")
        if expanded_count > 0:
            instance_data.data["proofdoor_size"] = total_pd_clauses
        # print(f"literals_in_interpolant_at_iteration: {literals_in_interpolant_at_iteration}")
    # 3) ProofDoor expansion status: determine by existence of smtcnf files
        if expanded_count == 0:
            instance_data.data["proofdoor_expansion_status"] = "not started"
        elif expanded_count < K:
            instance_data.data["proofdoor_expansion_status"] = f"partial done ({expanded_count}/{K})"
        else:
            instance_data.data["proofdoor_expansion_status"] = f"success ({expanded_count}/{K})"
        
        instance_data.data["smallest_interpolant_size"] = float(np.min(interpolant_size_list))
        instance_data.data["largest_interpolant_size"] = float(np.max(interpolant_size_list))
        log_mem(f"{instance} after interpolants summary")
    except Exception as e:
        instance_data.data["proofdoor_size"] = NOT_AVAILABLE
        print(f"ProofDoor size not available for {instance}, error: {e}")
        pass


    # 3) Cadical proof size (bytes)
    instance_data.data["cadical_proof_size"] = NOT_AVAILABLE
    instance_data.data["minisat_proof_size"] = NOT_AVAILABLE
    def get_proof_size(file_path):
        size = 0
        with open(file_path, "r") as f:
            for line in f:
                if line.startswith("d "):
                    continue
                elif line.startswith("0"):
                    continue
                else:
                    size += 1
        return size
    try:
        cadical_drat = f"{get_CNF_dir(K)}/{instance}.{K}.cadicalplain.drat"
        if os.path.exists(cadical_drat) and os.path.getsize(cadical_drat) > 0:
            instance_data.data["cadical_proof_size"] = get_proof_size(cadical_drat)
    except Exception as e:
        instance_data.data["cadical_proof_size"] = NOT_AVAILABLE
        print(f"Cadical proof size not available for {instance}, error: {e}")
        pass
    # 4) Minisat proof size (bytes)
    try:
        minisat_proof = f"{get_CNF_dir(K)}/{instance}.{K}.cnf.minisatproof"
        if os.path.exists(minisat_proof) and os.path.getsize(minisat_proof) > 0:
            instance_data.data["minisat_proof_size"] = get_proof_size(minisat_proof)
    except Exception as e:
        instance_data.data["minisat_proof_size"] = NOT_AVAILABLE
        print(f"Minisat proof size not available for {instance}, error: {e}")
        pass

    # 5) Solving times: parse solver logs directly
    def parse_time_from_candidates(candidates):
        for path in candidates:
            if os.path.exists(path) and os.path.getsize(path) > 0:
                try:
                    t = GetDataFromLog(path)
                    if t is not None:
                        return t
                except Exception:
                    continue
        return None

    try:
        cadical_time = GetDataFromLog(f"{get_CNF_dir(K)}/{instance}.{K}.cnf.cadicalplain.log")
        if cadical_time is not None:
            instance_data.data["cadical_solving_time"] = cadical_time
    except Exception as e:
        instance_data.data["cadical_solving_time"] = NOT_AVAILABLE
        print(f"Cadical solving time not available for {instance}, error: {e}")
        pass

    try:
        # MiniSat logs common locations
        minisat_log = f"{get_CNF_dir(K)}/{instance}.{K}.cnf.minisat.log"
        # if not os.path.exists(minisat_log):
        #     solver = "./solvers/minisat"
        #     cmd = f"{solver} {get_CNF_dir(K)}/{instance}.{K}.cnf -no-pre > {minisat_log}"
        #     os.system(cmd)
        minisat_time = GetDataFromLog(minisat_log)
        if minisat_time is not None:
            instance_data.data["minisat_solving_time"] = minisat_time
    except Exception as e:
        instance_data.data["minisat_solving_time"] = NOT_AVAILABLE  
        print(f"Minisat solving time not available for {instance}, error: {e}")
        pass
    # cadical absorption result(just empty now)
    instance_data.data["cadical_absorption_result"] = NOT_AVAILABLE
    print(f"Cadical absorption result not available for {instance}")
    # minisat absorption result(just empty now)
    instance_data.data["minisat_absorption_result"] = NOT_AVAILABLE
    print(f"Minisat absorption result not available for {instance}")

    # interpolant_size_variance
    instance_data.data["interpolant_size_variance"] = NOT_AVAILABLE
    if len(interpolant_size_list) > 0:
        instance_data.data["interpolant_size_variance"] = float(np.var(interpolant_size_list))
    
    # average_n_of_shared_variables_between_iterations
    instance_data.data["average_n_of_shared_variables_between_iterations"] = sum_shared_variables / (K-1)
    # average(n_of_variables_in_interpolant/n_of_variables_in_previous_formula)
    instance_data.data["average(n_of_variables_in_interpolant/n_of_variables_in_previous_formula)"] = float(np.mean(ratios)) if len(ratios) > 0 else NOT_AVAILABLE
    # drop references to large locals
    previous_vars_set = None
    del previous_vars_set
    gc.collect()
    log_mem(f"{instance} end fill_instance_data")

def process_instance(instance: str, exp_set) -> Tuple[str, Dict]:
    """
    Top-level worker for parallel processing.
    """
    print(f"[PROC] start {instance} (thread={threading.current_thread().name})", flush=True)
    log_mem(f"{instance} process start")
    instance_data = InstanceData(instance)
    instance_data.data["category"] = "exponential" if instance in exp_set else "linear"
    fill_instance_data(instance_data)
    print(instance_data.data, flush=True)
    print(f"[PROC] done {instance}", flush=True)
    gc.collect()
    log_mem(f"{instance} after gc")
    return instance, instance_data.data

def build_dashboard_data_and_save():
    instance_list = get_instance_list("exponential") + get_instance_list("linear")
    # instance_list = instance_list[:1]
    # instance_list = ["6s4"]
    ordering = [
        "instance_name",
        "category",
        "formula_size",
        "proofdoor_size",
        "smallest_interpolant_size",
        "interpolant_size_variance",
        "average_n_of_shared_variables_between_iterations",
        "average(n_of_variables_in_interpolant/n_of_variables_in_previous_formula)",
        "largest_interpolant_size",
        "proofdoor_expansion_status",
        "cadical_solving_time",
        "cadical_proof_size",
        "cadical_absorption_result",
        "minisat_solving_time",
        "minisat_proof_size",
        "minisat_absorption_result",
    ]
    dashboard_data = {}
    
    exp_set = set(get_instance_list("exponential"))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_instance, instance, exp_set) for instance in instance_list]
        for future in as_completed(futures):
            instance, data = future.result()
            dashboard_data[instance] = data

    with open("dashboard_data.json", "w") as f:
        json.dump(dashboard_data, f)
    with open("dashboard_data.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerow(ordering)
        for instance in dashboard_data:

            writer.writerow([dashboard_data[instance][key] for key in ordering])
    return dashboard_data

def archive_current_result():
    build_dashboard_data_and_save()
    # date = datetime.now().strftime("%Y%m%d_%H%M%S")
    # os.system(f"mv dashboard_data.json dashboard_data_{date}.json")
    # os.system(f"mv dashboard_data.csv dashboard_data_{date}.csv")
    # K=10
    # # # zip absorption experiments results
    # os.system(f"zip -r absorption_experiments_{date}.zip ProofDoorBenchmark/absorption_experiments/{K}/")
    # shutil.rmtree(f"ProofDoorBenchmark/absorption_experiments/{K}", ignore_errors=True)
    # shutil.rmtree("ProofDoorBenchmark/absorption_experiments/caches", ignore_errors=True)
    # # zip figures
    # os.system(f"zip -r figures_{date}.zip figures/absorption_experiments/")
    # shutil.rmtree("figures/absorption_experiments", ignore_errors=True)
    # # zip absorption experiments logs
    # os.system(f"zip -r absorption_experiment_{date}.zip Experiments/absorption/")
    # shutil.rmtree("Experiments/absorption", ignore_errors=True)
    

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", action="store_true", help="Print benchmark statistics and exit")
    args = parser.parse_args()

    if args.stats:
        print_stats()
    else:
        archive_current_result()

if __name__ == "__main__":
    main()