from concurrent.futures import ProcessPoolExecutor, as_completed, wait
import logging
import os
import json
from experiments.experiment import Experiment, ExperimentConfig
from utils.paths import get_CNF_dir, get_wires_dir, get_interpolant_dir
from utils.catagory import get_instance_list
from utils.utils import check_aig_file_exists
from utils.prepare_data import prepare_cnf
from utils.absorption_analysis import compute_wire_and_save
from utils.process_cnf import CNF
from utils.interpolant_sanity_check import check_cnf_A_implication

import subprocess
import argparse
from pathlib import Path


_WORKER_LOG_FORMAT = "%(asctime)s [pid %(process)d] %(levelname)s: %(message)s"


def _init_worker_logger(log_dir: str, log_name: str):
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("proofdoor.worker")
    logger.handlers.clear()

    handler = logging.FileHandler(
        os.path.join(log_dir, log_name),
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_WORKER_LOG_FORMAT))

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

def _prepare_cnf_task(instance: str, k_value: int):
    logger = logging.getLogger("proofdoor.worker")
    logger.info("Start prepare_cnf for %s (K=%s)", instance, k_value)
    try:
        prepare_cnf(instance, k_value)
    except Exception:
        logger.exception("prepare_cnf failed for %s", instance)
        raise
    logger.info("Finished prepare_cnf for %s", instance)

def prepare_trimed_proof(instance, k_value, force_refresh=True):
    """Trim a DRAT proof file using drat-trim."""
    logger = logging.getLogger("proofdoor.worker")
    logger.info("Start prepare_trimed_proof for %s (K=%s)", instance, k_value)
    CNF_dir = get_CNF_dir(k_value)
    cnf_path = Path(CNF_dir) / f"{instance}.{k_value}.cnf"
    proof_path = Path(CNF_dir) / f"{instance}.{k_value}.cnf.cadicalplain.drat"
    trimmed_path = Path(CNF_dir) / f"{instance}.{k_value}.cnf.cadicalplain.trimmed.drat"
    
    # Skip if already exists
    if trimmed_path.exists() and not force_refresh:
        logger.info("Trimmed proof exists for %s (K=%s)", instance, k_value)
        return str(trimmed_path)
    
    # Validate inputs
    if not cnf_path.exists() or not proof_path.exists():
        raise FileNotFoundError(f"Missing CNF or proof file for {cnf_path} or {proof_path}")
    
    # Run trimmer
    logger.info("Trimming proof for %s (K=%s)", instance, k_value)
    trimmer = "./solvers/drat-trim"
    # cmd = f"{trimmer} {proof_path} {cnf_path} > {trimmed_path}"
    cmd = f"cp {proof_path} {trimmed_path}"
    logger.info("Running command: %s", cmd)
    os.system(cmd)
    logger.info("Trimmed proof ready for %s (K=%s)", instance, k_value)
    return str(trimmed_path)



class ProofDoorComputationExperimentConfig(ExperimentConfig):
    def __init__(self, name, data_dir, result_dir, log_dir, K, category, force_instance=None):
        super().__init__(name, data_dir, result_dir, log_dir)
        self.K = K
        self.category = category
        self.force_instance = force_instance


class ProofDoorComputationExperiment(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)
        self.instance_list = get_instance_list(config.category)
        if config.force_instance:
            self.instance_list = [config.force_instance]
    
    def compute_interpolant_by_trimed_proof(self, name, k_value, index):
        worker_log_dir = os.path.join(
            self.config.log_dir, "workers", "interpolants"
        )
        _init_worker_logger(worker_log_dir, f"ComputeInterpolant_{name}.{k_value}.{index}.log")
        logger = logging.getLogger("proofdoor.worker")
        CNF_dir = get_CNF_dir(k_value)
        cnf_path = f"{CNF_dir}/{name}.{k_value}.cnf"
        interpolant_path = f"{get_interpolant_dir(k_value)}/{name}.{k_value}.{index}.interpolant"
        if os.path.exists(interpolant_path) and os.path.getsize(interpolant_path) > 0:
            logger.info("Interpolant file %s exists, skipping", interpolant_path)
            return []
        compute_wire_and_save(CNF.from_file(cnf_path))
        # print(wires_map)
        # wires = wires_map[index]["wires"]
        
        wire_path = f"{get_wires_dir(k_value)}/{name}.{k_value}.{index}.wires.json"
        wires = json.load(open(wire_path))["wires"]

        trimmed_proof_path = f"{CNF_dir}/{name}.{k_value}.cnf.cadicalplain.trimmed.drat"
        logger.info(
            "Reading trimmed proof from %s for %s (K=%s, index=%s)",
            trimmed_proof_path,
            name,
            k_value,
            index,
        )
        with open(trimmed_proof_path, 'r') as f:
            lines = f.readlines()
        matched_clauses = []
        for line in lines:
            line = line.strip()
            if line.startswith("c") or line.startswith("d"):
                continue
            else:
                literals = [int(literal) for literal in line.split(" ")[:-1]]
                not_matched = False
                for literal in literals:
                    if not literal in wires:
                        not_matched = True
                        break
                if not_matched or len(literals) == 0:
                    continue

                # check if A -> clause
                if not check_cnf_A_implication(name, k_value, index, literals):
                    continue
                matched_clauses.append(literals)
        logger.info(
            "Matched %d clauses for %s (K=%s, index=%s)",
            len(matched_clauses),
            name,
            k_value,
            index,
        )
        logger.info("Writing matched clauses to %s", interpolant_path)
        with open(interpolant_path, "w") as f:
            for clause in matched_clauses:
                for literal in clause:
                    f.write(str(literal) + " ")
                f.write("0\n")
        return matched_clauses

    def prepare_cnfs(self):
        max_workers = min(len(self.instance_list), os.cpu_count() or 1)
        self.logger.info(
            "Preparing CNFs in parallel with %d worker(s)", max_workers
        )

        worker_log_dir = os.path.join(self.config.log_dir, "workers", "cnf")

        # Parallelize CNF preparation so later stages can assume artifacts exist.
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_worker_logger,
            initargs=(worker_log_dir, f"PrepareCNF_{os.getpid()}.log"),
        ) as executor:
            future_to_instance = {
                executor.submit(
                    _prepare_cnf_task, instance, self.config.K
                ): instance
                for instance in self.instance_list
            }
            for future in as_completed(future_to_instance):
                instance = future_to_instance[future]
                try:
                    future.result()
                    self.logger.info("CNF prepared for %s", instance)
                except Exception:
                    self.logger.exception("CNF preparation failed for %s", instance)
                    raise
        self.logger.info(
            "CNF preparation complete for %d instances", len(self.instance_list)
        )

    def prepare_proofs(self):
        max_workers = min(len(self.instance_list), os.cpu_count() or 1)
        self.logger.info(
            "Trimming proofs in parallel with %d worker(s)", max_workers
        )

        worker_log_dir = os.path.join(self.config.log_dir, "workers", "proofs")

        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_worker_logger,
            initargs=(worker_log_dir, f"PrepareProof_{os.getpid()}.log"),
        ) as executor:
            future_to_instance = {
                executor.submit(
                    prepare_trimed_proof, instance, self.config.K
                ): instance
                for instance in self.instance_list
            }
            for future in as_completed(future_to_instance):
                instance = future_to_instance[future]
                try:
                    future.result()
                    self.logger.info("Proof trimmed for %s", instance)
                except Exception:
                    self.logger.exception("Proof trimming failed for %s", instance)
                    raise
        self.logger.info(
            "Proof trimming complete for %d instances", len(self.instance_list)
        )

    def on_start(self):
        if not self.instance_list:
            self.logger.warning("Instance list empty; skipping preparation")
            return
        self.prepare_cnfs()
        self.prepare_proofs()

    def experiment_main(self):
        max_workers = min(len(self.instance_list), os.cpu_count() or 1)
        if not self.instance_list:
            self.logger.warning("Instance list empty; skipping interpolation")
            return

        self.logger.info(
            "Computing interpolants in parallel with %d worker(s)", max_workers
        )

        worker_log_dir = os.path.join(
            self.config.log_dir, "workers", "interpolants"
        )
        with ProcessPoolExecutor(
            max_workers=max_workers,
            # initializer=_init_worker_logger,
            # initargs=(worker_log_dir, f"ComputeInterpolant_{os.getpid()}.log"),
        ) as executor:
            future_to_task = {
                executor.submit(
                    self.compute_interpolant_by_trimed_proof,
                    instance,
                    self.config.K,
                    index,
                ): (instance, index)
                for instance in self.instance_list
                for index in range(self.config.K)
            }
            wait(future_to_task.keys())
            for future in as_completed(future_to_task):
                instance, index = future_to_task[future]
                try:
                    future.result()
                    self.logger.info(
                        "Interpolant computed for %s (index %s)",
                        instance,
                        index,
                    )
                except Exception:
                    self.logger.exception(
                        "Interpolant computation failed for %s (index %s)",
                        instance,
                        index,
                    )
                    raise

        self.logger.info(
            "Interpolants computed for %d tasks",
            len(self.instance_list) * self.config.K,
        )
        self.end()

    def on_end(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=5)
    parser.add_argument("--category", type=str, default="exponential")
    parser.add_argument("--force_instance", type=str, default=None)
    args = parser.parse_args()
    config = ProofDoorComputationExperimentConfig(
        name="proofdoor_computation_with_trimed_proof",
        data_dir="cnfs",
        result_dir="interpolants",
        log_dir="logs",
        K=args.K,
        category=args.category,
        force_instance=args.force_instance,
    )
    experiment = ProofDoorComputationExperiment(config)
    experiment.run()

if __name__ == "__main__":
    main()

