from experiments.experiment import Experiment, ExperimentConfig
from utils.catagory import get_instance_list
from utils.utils import generate_cnf
from utils.paths import get_CNF_dir, get_interpolant_cnf_dir
from utils.process_cnf import CNF
import argparse
import os
import csv

def get_branching_order_dir(K):
    return f"./ProofDoorBenchmark/branching_orders/{K}/"

def get_branching_order_path(K, instance):
    return f"{get_branching_order_dir(K)}/{instance}.{K}.branching_order"

PBD_BINARY = "./solvers/cadical_pbh"


class PBHExperimentConfig(ExperimentConfig):
    def __init__(self, name, data_dir, result_dir, log_dir, K, category, force_instance=None, index=None):
        super().__init__(name, data_dir, result_dir, log_dir)
        self.K = K
        self.category = category
        self.index = index
        self.force_instance = force_instance
        if force_instance is not None:
            self.instance_list = [force_instance]
        else:
            self.instance_list = select_instances_from_csv()
            # self.instance_list = get_instance_list(category)

class PBHExperiment(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)
    
    def build_branching_list(self, instance, force_rebuild=False):
        if not force_rebuild and os.path.exists(get_branching_order_path(self.config.K, instance)):
            with open(get_branching_order_path(self.config.K, instance), "r") as f:
                branching_list = f.read().split()
            return branching_list
        
        # Build branching list from all interpolants for this instance
        os.makedirs(get_branching_order_dir(self.config.K), exist_ok=True)
        branching_list = []
        
        # Iterate through all interpolants (from 0 to K-1)
        for interpolation_index in range(self.config.K):
            interpolant_cnf_path = f"{get_interpolant_cnf_dir(self.config.K, 1)}/{instance}.{self.config.K}.{interpolation_index}.smtcnf"
            
            # Skip if file doesn't exist or is empty
            if not os.path.exists(interpolant_cnf_path) or os.path.getsize(interpolant_cnf_path) == 0:
                self.logger.warning(f"Interpolant file {interpolant_cnf_path} does not exist or is empty, skipping")
                continue
            
            try:
                interpolant_cnf_obj = CNF.from_file(interpolant_cnf_path, skip_parse_literal_map=True)
                interpolant_clauses = interpolant_cnf_obj.clauses
                
                # Extract all literals from the interpolant clauses
                for clause in interpolant_clauses:
                    for literal in clause:
                        branching_list.append(literal)
            except Exception as e:
                self.logger.error(f"Error processing interpolant file {interpolant_cnf_path}: {e}")
                continue
        
        # Save the branching list to file
        with open(get_branching_order_path(self.config.K, instance), "w") as f:
            for literal in branching_list:
                f.write(f"{literal}\n")
        
        return branching_list

    def process_single_instance(self, instance):
        self.logger.info(f"Processing instance {instance} with K={self.config.K}")
        
        # Build the branching list from interpolants
        branching_list = self.build_branching_list(instance)
        branching_list_path = get_branching_order_path(self.config.K, instance)
        
        # Set up paths
        cnf_path = f"{get_CNF_dir(self.config.K)}/{instance}.{self.config.K}.cnf"
        if not os.path.exists(cnf_path):
            print(f"creating cnf file {cnf_path}")
            generate_cnf(f"{instance}.{self.config.K}.cnf")
        original_drat_path = f"{self.config.result_dir}/{instance}.{self.config.K}.originalcadical.drat"
        original_log_path = f"{self.config.result_dir}/{instance}.{self.config.K}.originalcadical.log"
        pbd_drat_path = f"{self.config.result_dir}/{instance}.{self.config.K}.pbdcadical.drat"
        pbd_log_path = f"{self.config.result_dir}/{instance}.{self.config.K}.pbdcadical.log"
        
        # Check if results already exist
        if os.path.exists(original_log_path) and os.path.exists(pbd_log_path):
            self.logger.info(f"Results already exist for {instance}, skipping")
            return
        
        # Verify CNF file exists
        if not os.path.exists(cnf_path):
            self.logger.error(f"CNF file {cnf_path} does not exist, skipping {instance}")
            return
        
        # Run original CaDiCaL without proof-door branching heuristic
        if not os.path.exists(original_log_path):
            self.logger.info(f"Running original CaDiCaL for {instance}")
            cmd = f"{PBD_BINARY} --plain --no-binary --no-inprocessing --proof={original_drat_path} {cnf_path} > {original_log_path}"
            os.system(cmd)
        
        # Run CaDiCaL with proof-door branching heuristic
        if not os.path.exists(pbd_log_path):
            self.logger.info(f"Running CaDiCaL with PBH for {instance}")
            cmd = f"{PBD_BINARY} --plain --no-binary --no-inprocessing --proof={pbd_drat_path} {cnf_path} {branching_list_path} > {pbd_log_path}"
            os.system(cmd)
        
        self.logger.info(f"Completed processing instance {instance}")

    def on_start(self):
        # Create necessary directories
        os.makedirs(self.config.result_dir, exist_ok=True)
        os.makedirs(self.config.log_dir, exist_ok=True)
        os.makedirs(get_branching_order_dir(self.config.K), exist_ok=True)
        self.logger.info("PBH Experiment started")

    def on_end(self):
        self.logger.info("PBH Experiment completed")

    def manage(self):
        self.experiment_main()

    def experiment_main(self):
        self.logger.info(f"Processing {len(self.config.instance_list)} instances")
        for instance in self.config.instance_list:
            try:
                self.process_single_instance(instance)
            except Exception as e:
                self.logger.error(f"Error processing instance {instance}: {e}")
                continue
    
    def compare_results(self):
        time_map = {}
        for instance in self.config.instance_list:
            original_log_path = f"{self.config.result_dir}/{instance}.{self.config.K}.originalcadical.log"
            pbd_log_path = f"{self.config.result_dir}/{instance}.{self.config.K}.pbdcadical.log"
            if not os.path.exists(original_log_path) or not os.path.exists(pbd_log_path):
                print(f"Skipping instance {instance} because log files do not exist")
                continue
            pbd_time = parse_solve_time(pbd_log_path)
            original_time = parse_solve_time(original_log_path)
            time_map[instance] = {
                "original": original_time,
                "pbd": pbd_time
            }
        
            print(f"Instance {instance}: Original time: {original_time}, PBD time: {pbd_time}")

        average_ratio = sum(time_map[instance]["pbd"] / time_map[instance]["original"] for instance in time_map) / len(time_map)
        print(f"Ratio average: {average_ratio}")
        average_ratio = sum(time_map[instance]["pbd"] for instance in time_map)/ sum(time_map[instance]["original"] for instance in time_map)
        print(f"Average ratio: {average_ratio}")


def parse_solve_time(log_path):
    """
    Parse solve time from CaDiCaL log file.
    
    Returns:
        float: Solve time in seconds, or None if not found
    """
    with open(log_path, 'r') as f:
        for line in f:
            if "Solve time:" in line:
                # Extract the time value (second to last token)
                # Format: "c Solve time: 0.047435 seconds"
                return float(line.split()[-2])
    return None

def select_instances_from_csv(csv_path="./dashboard_data.csv"):
    # instance_list = ["6s4"]
    instance_list = []
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if row[9] == "success (10/10)" and row[1] == "exponential":
                print("matching instance: ", row[0])
                instance_list.append(row[0])
    return instance_list
    # return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, required=False)
    parser.add_argument("--category", type=str, required=False)
    parser.add_argument("--force_instance", type=str, required=False)
    parser.add_argument("--index", type=int, required=False)
    parser.add_argument("--compare", action="store_true", required=False)
    parser.add_argument("--use_summary", type=str, required=False)
    args = parser.parse_args()
    if args.use_summary:
        summary_path = args.use_summary
        if not os.path.exists(summary_path):
            raise FileNotFoundError(f"Summary CSV not found: {summary_path}")
        targets = []
        with open(summary_path, "r") as f:
            reader = csv.DictReader(f)
            required = {"instance_name", "K", "smt2cnf_status"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV missing required columns: {sorted(missing)}")
            for row in reader:
                status = (row.get("smt2cnf_status") or "").strip().lower()
                if status != "done":
                    continue
                instance = (row.get("instance_name") or "").strip()
                if not instance:
                    continue
                try:
                    K = int(row.get("K"))
                except Exception:
                    continue
                targets.append((instance, K))
        print(f"[from_summary] Found {len(targets)} (instance,K) with SMT→CNF done from {summary_path}")
        for instance, K in targets[:20]:
            config = PBHExperimentConfig(name="pbh", data_dir="data", result_dir="result", log_dir="log", K=K, category=args.category, force_instance=instance, index=args.index)
            experiment = PBHExperiment(config)
            experiment.manage()
        return

if __name__ == "__main__":
    main()