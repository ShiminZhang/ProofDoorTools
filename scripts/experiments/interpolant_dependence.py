import argparse
import csv
import os
from typing import Dict, List, Tuple

from experiments.experiment import Experiment, ExperimentConfig
from utils.catagory import get_instance_list
from utils.paths import get_CNF_dir, get_interpolant_cnf_dir, get_interpolant_dependence_result_dir
from utils.process_cnf import CNF
from tqdm import tqdm

try:
    from PDSScalingExperiment import (
        load_available_ks_from_summary,
        load_instances_from_summary,
    )
except ImportError:
    import sys
    _scripts = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)
    from PDSScalingExperiment import (
        load_available_ks_from_summary,
        load_instances_from_summary,
    )


class InterpolantDependenceExperimentConfig(ExperimentConfig):
    def __init__(self, name, data_dir, result_dir, log_dir, category, summary_path, pddef=1, done_only=False, force_instance=None):
        super().__init__(name, data_dir, result_dir, log_dir)
        self.K = None  # varies per instance
        self.category = category
        self.summary_path = summary_path
        self.pddef = pddef
        self.done_only = done_only
        self.force_instance = force_instance
        if not summary_path or not os.path.exists(summary_path):
            raise FileNotFoundError(f"Summary CSV not found: {summary_path}")
        self.instance_list = load_instances_from_summary(summary_path, category)
        self.k_map = load_available_ks_from_summary(
            summary_path, self.instance_list, done_only=done_only
        )
        if force_instance is not None:
            self.instance_list = [force_instance]


class InterpolantDependenceExperiment(Experiment):
    def __init__(self, config: InterpolantDependenceExperimentConfig):
        super().__init__(config)
        self.config: InterpolantDependenceExperimentConfig = config

    def on_start(self):
        pass

    def on_end(self):
        pass

    def experiment_main(self):
        config = self.config
        pddef = config.pddef
        result_rows: List[Tuple[str, int, int, int]] = []

        # Build (name, K) tasks from k_map or fallback to all K in interpolant dir
        tasks: List[Tuple[str, int]] = []
        for name in config.instance_list:
            ks = config.k_map.get(name) if config.k_map else None
            if ks is not None:
                for k in ks:
                    tasks.append((name, k))
            else:
                # Fallback: probe K from interpolant dir
                base = f"./ProofDoorBenchmark/interpolant_as_cnfs_{pddef}/"
                if not os.path.isdir(base):
                    continue
                k_dirs = [d for d in os.listdir(base) if d.isdigit()]
                for k_str in sorted(k_dirs, key=int):
                    k = int(k_str)
                    path = get_interpolant_cnf_dir(k, pddef) + f"{name}.{k}.0.smtcnf"
                    if os.path.exists(path):
                        tasks.append((name, k))

        for name, K in tqdm(tasks, desc="interpolant_dependence"):
            cnf_path = get_CNF_dir(K) + f"{name}.{K}.cnf"
            if not os.path.exists(cnf_path):
                continue
            try:
                formula = CNF(cnf_path)
            except Exception:
                continue
            for i in range(K):
                interp_path = get_interpolant_cnf_dir(K, pddef) + f"{name}.{K}.{i}.smtcnf"
                if not os.path.exists(interp_path):
                    continue
                try:
                    interpolant = CNF(interp_path)
                except Exception:
                    continue
                ub = get_upper_bound_of_dependence(formula.clauses, interpolant.clauses)
                result_rows.append((name, K, i, ub))

        if config.force_instance is not None:
            out_dir = get_interpolant_dependence_result_dir(config.pddef)
            out_path = os.path.join(out_dir, f"{config.force_instance}.csv")
        else:
            out_dir = config.result_dir
            out_path = os.path.join(out_dir, f"interpolant_dependence_{config.category}.csv")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "K", "i", "ub_dependence"])
            w.writerows(result_rows)
        self.logger.info("Saved %d rows to %s", len(result_rows), out_path)

    def manage(self):
        """Submit one Slurm job per instance."""
        import shutil
        if shutil.which("sbatch") is None:
            raise RuntimeError("sbatch not found; cannot run --manage")
        logs_dir = f"./SlurmLogs/interpolant_dependence_{self.config.category}/"
        os.makedirs(logs_dir, exist_ok=True)
        for instance in self.config.instance_list:
            cmd = (
                f"python scripts/experiments/interpolant_dependence.py "
                f"--category {self.config.category} --summary {self.config.summary_path} "
                f"--pddef {self.config.pddef} --instance {instance}"
            )
            if self.config.done_only:
                cmd += " --done_only"
            log_path = f"{logs_dir}/{instance}.%j.log"
            self.queue_command_in_slurm(cmd, mem="16g", time="6:00:00", output=log_path)
        self.execute_queued_command_in_slurm()
        self.end()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", type=str, required=True)
    parser.add_argument("--summary", type=str, default="regression_summary.csv")
    parser.add_argument("--pddef", type=int, default=1)
    parser.add_argument("--done_only", action="store_true", help="Only use (instance,K) with smt2cnf_status==done")
    parser.add_argument("--instance", type=str, default=None, help="Process single instance (used by --manage jobs)")
    parser.add_argument("--manage", action="store_true", help="Submit one Slurm job per instance")
    args = parser.parse_args()

    config = InterpolantDependenceExperimentConfig(
        name="interpolant_dependence",
        data_dir="data",
        result_dir="result",
        log_dir="log",
        category=args.category,
        summary_path=args.summary,
        pddef=args.pddef,
        done_only=args.done_only,
        force_instance=args.instance,
    )
    exp = InterpolantDependenceExperiment(config)
    if args.manage:
        exp.manage()
    else:
        exp.run()

# return relevant clauses for each interpolant clause
def get_relevant_clauses(formula: List[List[int]], interpolant: List[List[int]]) -> Dict[int, List[List[int]]]:
    relevant_clauses = {i: [] for i in range(len(interpolant))}
    for clause in formula:
        for literal in clause:
            for i in range(len(interpolant)):
                interpolant_clause = interpolant[i]
                if literal in interpolant_clause:
                    relevant_clauses[i].append(clause)
    return relevant_clauses

def upper_bound_relevant_clauses(relevant_clauses: Dict[int, List[List[int]]]) -> int:
    if not relevant_clauses:
        return 0
    return max(len(clauses) for clauses in relevant_clauses.values())

def get_upper_bound_of_dependence(formula: List[List[int]], interpolant: List[List[int]]) -> int:
    relevant_clauses = get_relevant_clauses(formula, interpolant)
    return upper_bound_relevant_clauses(relevant_clauses)

if __name__ == "__main__":
    main()