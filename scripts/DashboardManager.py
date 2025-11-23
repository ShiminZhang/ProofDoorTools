NOT_STARTED = "not started"
NOT_AVAILABLE = "not available"
from utils.catagory import get_instance_list
import numpy as np
from datetime import datetime
import csv
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
    # build_dashboard_data_and_save()
    archive_current_result()

if __name__ == "__main__":
    main()