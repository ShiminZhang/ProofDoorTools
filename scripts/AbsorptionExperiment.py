from experiments.experiment import Experiment, ExperimentConfig
from utils.catagory import get_instance_list
from utils.paths import get_CNF_dir, get_interpolant_cnf_dir, get_absorption_experiments_dir, get_figures_dir, get_latest_PDC_result, get_latest_absorption_result
from concurrent.futures import ProcessPoolExecutor
from utils.process_cnf import CNF, read_proof
from utils.absorption_analysis import check_formula_absorp_clause, check_formula_absorp_clause_accelerated
import matplotlib.pyplot as plt
from tqdm import tqdm
import logging
import argparse
import json
import os
import csv
USE_TRIMM_PROOF = False
DRAT_TRIM_BINARY = "./drat-trim"
GLUCOSE_BINARY = "./External/glucose/simp/glucose"
# MINISAT_BINARY = "./minisat/build/release/bin/minisat"
MINISAT_BINARY = "./External/minisat/build/release/bin/minisat"
MAX_WORKERS = 4
CADICAL_BINARY = "./solvers/cadical"

def include_formula_in_checking_flag_to_suffix(include_formula_in_checking):
    return "withformulainproof." if include_formula_in_checking else ""

def check_single_clause_absorption_worker(args):
    logger = logging.getLogger("proofdoor.worker")
    instance, K, proof_index, interpolation_index, interpolant_clause_index, interpolant_clause, use_minisat_proof, use_glucose_proof, include_formula_in_checking = args
    
    proof_iteration = proof_index + 1  # partial proof i stores clauses up to iteration i
    proof_path = get_partial_proof_path(instance, K, proof_iteration, use_minisat_proof, use_glucose_proof, include_formula_in_checking)
    logger.info("check_single_clause_absorption_worker: %s (proof_index=%s -> iteration=%s)", proof_path, proof_index, proof_iteration)
    proof_as_formula = CNF.from_file(proof_path)
    proof_clauses = proof_as_formula.clauses
    print(f"DEBUG:  interp_{interpolation_index} clause_{interpolant_clause_index} proof_{proof_index} {proof_path}")
    print(f"DEBUG: proof_clauses: {len(proof_clauses)}")

    # if include_formula_in_checking:
    #     print(f"adding original formula to the proof")
    #     # add original formula to the proof
    #     original_formula_path = f"{get_CNF_dir(K)}/{instance}.{K}.cnf"
    #     original_formula = CNF.from_file(original_formula_path)
    #     proof_clauses.extend(original_formula.clauses)
    solver_suffix = "minisat" if use_minisat_proof else "glucose" if use_glucose_proof else "cadical"
    return check_formula_absorp_clause(
        proof_clauses,
        interpolant_clause,
        f"{instance}.{K}.interpolation_{interpolation_index}.interpolant_{interpolant_clause_index}.proof_{proof_index}.{solver_suffix}{include_formula_in_checking_flag_to_suffix(include_formula_in_checking)}.check_absorb.json",
        K,
    )

def get_proof_path(instance, K, use_minisat_proof=False, use_glucose_proof=False, not_trim_proof=False):
    if not not_trim_proof:
        return f"{get_proof_path(instance, K, use_minisat_proof, use_glucose_proof, True)}.trimmed"
    if use_minisat_proof:
        return f"{get_CNF_dir(K)}/{instance}.{K}.cnf.minisatproof"
    elif use_glucose_proof:
        return f"{get_CNF_dir(K)}/{instance}.{K}.cnf.glucoseproof"
    else:
        return f"{get_CNF_dir(K)}/{instance}.{K}.cadicalplain.drat"

def get_partial_proof_path(instance, K, iteration, use_minisat_proof=False, use_glucose_proof=False, include_formula_in_checking=False):
    suffix = "minisat" if use_minisat_proof else "glucose" if use_glucose_proof else "cadical"
    if include_formula_in_checking:
        return f"{get_CNF_dir(K)}/{instance}.{K}.{iteration}.{suffix}.withformulainproof.partialproof"
    else:
        return f"{get_CNF_dir(K)}/{instance}.{K}.{iteration}.{suffix}.partialproof"

def get_smtcnf_path(instance: str, K: int, index: int, reverse: bool = False) -> str:
    suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    return f"{get_interpolant_cnf_dir(K,1)}/{instance}.{K}.{index}{suffix}"

def get_absorption_result_path(instance: str, K: int, interpolation_index: int, solver_suffix: str, include_formula_suffix: str, reverse: bool = False, base_dir: str = None) -> str:
    reverse_suffix = ".reverse" if reverse else ""
    base = base_dir or get_absorption_experiments_dir(K)
    return f"{base}/{instance}.i_{interpolation_index}{reverse_suffix}.{solver_suffix}.{include_formula_suffix}check_absorb.json"

class AbsorptionExperimentConfig(ExperimentConfig):
    def __init__(self, name, data_dir, result_dir, log_dir, K, category, force_instance=None, index = None, use_minisat_proof=False, use_glucose_proof=False, include_formula_in_checking=False, use_pbh_proof=False, reverse: bool = False):
        super().__init__(name, data_dir, result_dir, log_dir)
        self.K = K
        self.index = index
        if force_instance is not None:
            print(f"forcing instance: {force_instance}")
            self.instance_list = [force_instance]
        else:
            self.instance_list = select_instances_from_csv(category=category)
        self.use_glucose_proof = use_glucose_proof
        self.category = category
        self.include_formula_in_checking = include_formula_in_checking
        self.force_instance = force_instance
        self.use_minisat_proof = use_minisat_proof
        self.use_pbh_proof = use_pbh_proof
        self.reverse = reverse
def draw_greyscale_plot(percentage_trend, title, color='Greys', k_value=10):
    plt.figure(figsize=(10, 6))
    plt.xticks(range(len(percentage_trend[0])), [f"{i}" for i in range(len(percentage_trend[0]))])
    plt.imshow(percentage_trend, cmap=color, aspect='auto')
    plt.colorbar(label='Pass Percentage')
    plt.xlabel('Proof partition index')
    plt.ylabel('Interpolant index')
    plt.title(title)
    if not os.path.exists(f"{get_figures_dir()}/absorption_experiments/{k_value}"):
        os.makedirs(f"{get_figures_dir()}/absorption_experiments/{k_value}")
    print(f"saving figure to {get_figures_dir()}/absorption_experiments/{k_value}/{title}.png")
    plt.savefig(f"{get_figures_dir()}/absorption_experiments/{k_value}/{title}.png")


class AbsorptionExperiment(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)

    def on_start(self):
        pass

    def draw_heatmap_for_instance(self, instance):
        K = self.config.K
        percentage_for_iterations = []
        include_formula_suffix = include_formula_in_checking_flag_to_suffix(self.config.include_formula_in_checking)
        include_formula_title = "withFormula" if self.config.include_formula_in_checking else "withoutFormula"
        use_trimmed_proof_title = "trimmed" if USE_TRIMM_PROOF else "notrimmed"
        reverse_title = "reverse" if self.config.reverse else "forward"
        for index in range(K):
            interpolant_absorption_percentage_with_proof_index = []
            output_dir = f"{get_absorption_experiments_dir(K)}/"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            suffix = "minisat" if self.config.use_minisat_proof else "glucose" if self.config.use_glucose_proof else "cadical"
            output_path = get_absorption_result_path(
                instance,
                self.config.K,
                index,
                suffix,
                include_formula_suffix,
                reverse=self.config.reverse,
            )
            # output_path = f"{get_absorption_experiments_dir()}/{basename}.k_{k_value}.i_{index}.check_absorb.json"
            result = json.load(open(output_path))
            for proof_index in range(K):
                pass_count = 0
                total_count = 0
                if proof_index < index:
                    interpolant_absorption_percentage_with_proof_index.append(0)
                    continue

                for clause in result:
                    for literal_absorbed in result[clause][str(proof_index)]:
                        total_count += 1
                        if literal_absorbed:
                            pass_count += 1
                interpolant_absorption_percentage_with_proof_index.append(float(pass_count) / total_count)
            percentage_for_iterations.append(interpolant_absorption_percentage_with_proof_index)
        solver_name = "MiniSat" if self.config.use_minisat_proof else "Glucose" if self.config.use_glucose_proof else "CaDiCaL"
        print(f"drawing heatmap for instance: {instance}, solver_name: {solver_name}, use_trimmed_proof: {USE_TRIMM_PROOF}")
        draw_greyscale_plot(
            percentage_for_iterations,
            f'Literal Absorption Pass Percentage Heatmap {instance} ({solver_name})_{include_formula_title}_{use_trimmed_proof_title}_{reverse_title}',
            k_value=self.config.K,
            color='Blues',
        )
        
        return percentage_for_iterations

    def check_result(self):
        exponential_instances = get_instance_list("exponential")
        linear_instances = get_instance_list("linear")
        instances = exponential_instances + linear_instances
        absorption_log_path = f"{self.config.log_dir}/"
        absorption_results = {}
        solver_suffix = "minisat" if self.config.use_minisat_proof else "glucose" if self.config.use_glucose_proof else "cadical"
        for log_file in os.listdir(absorption_log_path):
            parts = log_file.split(".")
            if len(parts) < 5 or parts[0] != "Absorption" or parts[-1] != "log":
                continue
            solver = parts[-2]
            if solver != solver_suffix:
                continue
            is_reverse_log = "reverse" in parts
            if is_reverse_log != self.config.reverse:
                continue
            instance = parts[1]
            K = parts[2]
            with open(os.path.join(absorption_log_path, log_file), "r") as f:
                content = f.read()
                if "error" in content:
                    absorption_results[instance] = "error"
                elif "dummy" in content:
                    absorption_results[instance] = "dummy interpolant used"
                elif "Absorption experiment results saved to" in content:
                    absorption_results[instance] = "success"
                else:
                    absorption_results[instance] = "WIP"
        PDC_result = json.load(open(get_latest_PDC_result(self.config.K)))
        total_results = {} #{"PDCstatus": PDCstatus, "PDCsuccesses": PDCsuccesses, "PDCtotal": PDCtotal, "absorptionstatus": absorptionstatus}
        
        for instance in tqdm(instances):
            entry = {"PDCstatus": "not started", "PDCsuccesses": -1, "PDCtotal": -1, "absorptionstatus": "not started"}

            if instance in absorption_results.keys():
                entry["absorptionstatus"] = absorption_results[instance]
            else:
                entry["absorptionstatus"] = "not started"

            print(f"Checking instance: {instance}, PDC result: {PDC_result[instance] if instance in PDC_result.keys() else 'None'}")
            if instance not in PDC_result.keys():
                entry["PDCstatus"] = "not started"
                entry["PDCsuccesses"] = -1
                entry["PDCtotal"] = -1
            else:
                entry["PDCstatus"] = PDC_result[instance][0]
                entry["PDCsuccesses"] = PDC_result[instance][1]
                entry["PDCtotal"] = PDC_result[instance][2]
            total_results[instance] = entry
        with open(get_latest_absorption_result(self.config.K), "w") as f:
            json.dump(total_results, f, indent=4)

    def draw_heatmap_all(self):
        # parallelize the drawing of heatmaps
        print(f"drawing heatmap for all instances")
        instances = get_instance_list("linear") + get_instance_list("exponential")
        # instances = get_instance_list(self.config.category)
        filtered_instances = set()
        for instance in instances:
            should_skip = False
            solver_suffix = "minisat" if self.config.use_minisat_proof else "glucose" if self.config.use_glucose_proof else "cadical"
            include_formula_suffix = include_formula_in_checking_flag_to_suffix(self.config.include_formula_in_checking)
            for index in range(self.config.K):
                output_path = get_absorption_result_path(
                    instance,
                    self.config.K,
                    index,
                    solver_suffix,
                    include_formula_suffix,
                    reverse=self.config.reverse,
                )
                if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                    should_skip = True
                    break
            if should_skip:
                print(f"skipped {instance}")
                continue
            filtered_instances.add(instance)

        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            executor.map(self.draw_heatmap_for_instance, filtered_instances)

    def draw_heatmap(self):
        assert(len(self.config.instance_list) == 1)
        instance = self.config.instance_list[0]
        self.draw_heatmap_for_instance(instance)

    def check_cnf(self):
        assert(len(self.config.instance_list) == 1)
        instance = self.config.instance_list[0]
        cnf_path = f"{get_CNF_dir(self.config.K)}/{instance}.{self.config.K}.cnf"
        if not os.path.exists(cnf_path):
            raise FileNotFoundError(f"CNF file {cnf_path} not found")
        pass

    def check_proof(self):
        assert(len(self.config.instance_list) == 1)
        instance = self.config.instance_list[0]
        proof_path = get_proof_path(instance, self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not USE_TRIMM_PROOF)
        if not os.path.exists(proof_path):
            raise FileNotFoundError(f"Proof file {proof_path} not found")
        pass

    def check_proof_partitioned(self):
        assert(len(self.config.instance_list) == 1)
        instance = self.config.instance_list[0]
        for iteration in range(self.config.K):
            proof_path = get_partial_proof_path(instance, self.config.K, iteration, self.config.use_minisat_proof, self.config.use_glucose_proof)
            if not os.path.exists(proof_path):
                raise FileNotFoundError(f"Partial proof file {proof_path} not found")
        pass

    def partition_proof(self):
        assert(len(self.config.instance_list) == 1)
        cnf_path = f"{get_CNF_dir(self.config.K)}/{self.config.instance_list[0]}.{self.config.K}.cnf"
        # the literals should be marked as belonging to which iteration
        cnf_obj = CNF(cnf_path, use_cache=False)

        if self.config.use_pbh_proof:
            proof_path = f"./Experiments/pbh/result/{self.config.instance_list[0]}.{self.config.K}.pbdcadical.log"

            # proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not USE_TRIMM_PROOF)
        else:
            proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not USE_TRIMM_PROOF)
        clauses_in_proof = read_proof(proof_path)

        # the clauses should be marked as belonging to which iteration
        literal_belongs_to_iteration_map = cnf_obj.last_occurrence_map
        clause_belongs_to_iteration_map = {}
        for clause_as_list in clauses_in_proof:
            highest_iteration = -1
            for literal in clause_as_list:
                iteration = literal_belongs_to_iteration_map[abs(literal)]
                highest_iteration = max(highest_iteration, iteration)
            # assert str(clause_as_list) not in clause_belongs_to_iteration_map
            if str(clause_as_list) in clause_belongs_to_iteration_map:
                print(f"clause_as_list: {clause_as_list} already in clause_belongs_to_iteration_map")
                current_iteration = clause_belongs_to_iteration_map[str(clause_as_list)]
                if current_iteration > highest_iteration:
                    highest_iteration = current_iteration
                    clause_belongs_to_iteration_map[str(clause_as_list)] = highest_iteration
            else:
                clause_belongs_to_iteration_map[str(clause_as_list)] = highest_iteration
        
        # the clauses should be partitioned into different iterations
        partial_proofs = {} 
        for iteration in range(self.config.K+1):
            partial_proofs[iteration] = []
        # print(f"clause_belongs_to_iteration_map: {clause_belongs_to_iteration_map}")
        highest_clause_iteration = -1
        for clause in clauses_in_proof:
            iteration = clause_belongs_to_iteration_map[str(clause)]
            highest_clause_iteration = max(highest_clause_iteration, iteration)
            for i in range(highest_clause_iteration, self.config.K+1):
                partial_proofs[i].append(clause)

        # finally, save the partial proofs
        for iteration, partial_proof in partial_proofs.items():
            with open(get_partial_proof_path(self.config.instance_list[0], self.config.K, iteration, self.config.use_minisat_proof, self.config.use_glucose_proof), "w") as f:
                for clause in partial_proof:
                    for literal in clause:
                        f.write(f"{literal} ")
                    f.write("0\n")
        if self.config.include_formula_in_checking:
            for iteration, partial_proof in partial_proofs.items():
                partial_proof_path = get_partial_proof_path(self.config.instance_list[0], self.config.K, iteration, self.config.use_minisat_proof, self.config.use_glucose_proof, include_formula_in_checking=True)
                print(f"adding original formula to the proof {partial_proof_path}")
                with open(partial_proof_path, "w") as f:
                    for clause in partial_proof:
                        for literal in clause:
                            f.write(f"{literal} ")
                        f.write("0\n")
                    for clause in cnf_obj.clauses:
                        for literal in clause:
                            f.write(f"{literal} ")
                        f.write("0\n")
        pass


    def check_absorption(self):
        # assume the proof is already partitioned
        assert(len(self.config.instance_list) == 1)
        instance = self.config.instance_list[0]
        interpolant_map = {}
        # target_interpolant_index = self.config.index
        for interpolation_index in range(self.config.K):
            interpolant_cnf_path = get_smtcnf_path(instance, self.config.K, interpolation_index, reverse=self.config.reverse)
            if not os.path.exists(interpolant_cnf_path) or os.path.getsize(interpolant_cnf_path) == 0:
                print(f"SMT CNF file {interpolant_cnf_path} invalid, fake a dummy interpolant")
                interpolant_map[interpolation_index] = []
                continue
            interpolant_cnf_obj = CNF.from_file(interpolant_cnf_path, skip_parse_literal_map=True)
            interpolant_clauses = interpolant_cnf_obj.clauses
            interpolant_map[interpolation_index] = interpolant_clauses

        workers = os.cpu_count() or 1
        workers = min(workers, MAX_WORKERS)
        # Prepare task records and args for picklable process execution
        task_records = [
            (
                proof_index,
                interpolant_clause_index,
                interpolation_index,
                interpolant_map[interpolation_index][interpolant_clause_index],
            )
            for proof_index in range(self.config.K)
            for interpolation_index in range(proof_index + 1)
            # for interpolation_index in range(self.config.K)
            for interpolant_clause_index in range(len(interpolant_map[interpolation_index]))
        ]
        task_args = [
            (
                instance,
                self.config.K,
                proof_index,
                interpolation_index,
                interpolant_clause_index,
                interpolant_clause,
                self.config.use_minisat_proof,
                self.config.use_glucose_proof,
                self.config.include_formula_in_checking,
            )
            for (proof_index, interpolant_clause_index, interpolation_index, interpolant_clause) in task_records
        ]
        
        with ProcessPoolExecutor(max_workers=workers) as executor:
            # map returns results in the same order as input
            results_list = list(executor.map(check_single_clause_absorption_worker, task_args))
        
        # Map results back to nested dictionary structure
        results = {}
        for interpolation_index in range(self.config.K):
            results[interpolation_index] = {}
        for (proof_index, interpolant_clause_index, interpolation_index, interpolant_clause), result in zip(task_records, results_list):
            if interpolation_index not in results:
                results[interpolation_index] = {}
            clause_str = str(interpolant_clause)
            if clause_str not in results[interpolation_index]:
                results[interpolation_index][clause_str] = {}
            if proof_index not in results[interpolation_index][clause_str]:
                results[interpolation_index][clause_str][proof_index] = {}

            results[interpolation_index][clause_str][proof_index] = result

        for interpolation_index in range(self.config.K):
            solver_suffix = "minisat" if self.config.use_minisat_proof else "glucose" if self.config.use_glucose_proof else "cadical"
            include_formula_suffix = include_formula_in_checking_flag_to_suffix(self.config.include_formula_in_checking)
            output_path = get_absorption_result_path(
                instance,
                self.config.K,
                interpolation_index,
                solver_suffix,
                include_formula_suffix,
                reverse=self.config.reverse,
            )
            with open(output_path, "w") as f:
                json.dump(results[interpolation_index], f)
            print(f"Absorption experiment results saved to {output_path}")

    def check_minisat_result(self):
        instances = get_instance_list("linear") + get_instance_list("exponential")
        results = {}
        include_formula_title = "withFormula" if self.config.include_formula_in_checking else "withoutFormula"
        use_trimmed_proof_title = "trimmed" if USE_TRIMM_PROOF else "notrimmed"
        reverse_title = "reverse" if self.config.reverse else "forward"
        solver_name = "MiniSat" if self.config.use_minisat_proof else "Glucose" if self.config.use_glucose_proof else "CaDiCaL"
        for instance in instances:
            title = f"Literal Absorption Pass Percentage Heatmap {instance} ({solver_name})_{include_formula_title}_{use_trimmed_proof_title}_{reverse_title}"
            figure_path = f"{get_figures_dir()}/absorption_experiments/{self.config.K}/{title}.png"
            if not os.path.exists(figure_path):
                print(f"Figure {figure_path} does not exist, skipping")
                continue
            proof_door_size = 0
            for interpolation_index in range(self.config.K):
                smtcnf_path = get_smtcnf_path(instance, self.config.K, interpolation_index, reverse=self.config.reverse)
                with open(smtcnf_path, "r") as f:
                    lines = f.readlines()
                    proof_door_size += len(lines)
            print(f"Proof door size: {proof_door_size}")
            proof_size = os.path.getsize(get_proof_path(instance, self.config.K, True, False, not USE_TRIMM_PROOF))
            print(f"Proof size: {proof_size}")
            results[instance] = f"Proof door size: {proof_door_size}, Proof size: {proof_size}"

        for instance, result in results.items():
            print(f"Instance: {instance}, Result: {result}")
            
    def process_single_instance(self):
        print(f"Processing instance {self.config.instance_list[0]} with K={self.config.K} and use_minisat_proof={self.config.use_minisat_proof}")
        assert(len(self.config.instance_list) == 1)
        if self.config.use_minisat_proof:
            assert not self.config.use_glucose_proof
            cnf_path = f"{get_CNF_dir(self.config.K)}/{self.config.instance_list[0]}.{self.config.K}.cnf"
            proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not_trim_proof=True)
            if os.path.exists(proof_path) and True:
                print(f"force rerunning {proof_path}")
                os.system(f"rm {proof_path}")
            if not os.path.exists(proof_path):
                print(f"MiniSat proof file {proof_path} does not exist, running MiniSat to generate")
                solver = f"{MINISAT_BINARY} -no-pre"
                cmd = f"{solver} {cnf_path}"
                os.system(cmd)
        elif self.config.use_glucose_proof:
            print(f"Using Glucose proof")
            assert not self.config.use_minisat_proof
            cnf_path = f"{get_CNF_dir(self.config.K)}/{self.config.instance_list[0]}.{self.config.K}.cnf"
            proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not_trim_proof=True)
            if os.path.exists(proof_path) and True:
                print(f"force rerunning {proof_path}")
                os.system(f"rm {proof_path}")
            if not os.path.exists(proof_path):
                cmd = f"{GLUCOSE_BINARY} -no-pre -certified-output={proof_path} {cnf_path} -certified"
                res = os.popen(cmd).read()
                if "s SATISFIABLE" in res:
                    print(f"formula is satisfiable, skipping")
                    return
                print(f"Glucose proof file {proof_path} does not exist, running Glucose to generate")
        else:
            cnf_path = f"{get_CNF_dir(self.config.K)}/{self.config.instance_list[0]}.{self.config.K}.cnf"
            proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not_trim_proof=True)
            if os.path.exists(proof_path) and True:
                print(f"force rerunning {proof_path}")
                os.system(f"rm {proof_path}")
            if not os.path.exists(proof_path):
                cmd = f"{CADICAL_BINARY} --plain --no-reduce --no-binary --no-inprocessing {cnf_path} {proof_path}"
                res = os.popen(cmd).read()
                if "s SATISFIABLE" in res:
                    print(f"formula is satisfiable, skipping")
                    return
                print(f"Cadical proof file {proof_path} does not exist, running Cadical to generate")

            
        self.check_cnf() # assume the cnf is already generated
        # trim the proof if USE_TRIMM_PROOF is True
        if USE_TRIMM_PROOF:
            cnf_path = f"{get_CNF_dir(self.config.K)}/{self.config.instance_list[0]}.{self.config.K}.cnf"
            proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, not_trim_proof=True)
            trim_proof_path = get_proof_path(self.config.instance_list[0], self.config.K, self.config.use_minisat_proof, self.config.use_glucose_proof, False)
            cmd = f"{DRAT_TRIM_BINARY} {cnf_path} {proof_path} -l {trim_proof_path}"
            res = os.popen(cmd).read()
        self.check_proof() # assume the proof is already generated
        # self.check_proof_partitioned()
        self.partition_proof()
        self.check_absorption()
        self.draw_heatmap()
        pass
    

    def compute_KL_divergence(self, res_directory):
        instances = get_instance_list("linear") + get_instance_list("exponential")
        # instances = ["pdtvisbakery2"]
        kl_divergence = {}
        include_formula_suffix = include_formula_in_checking_flag_to_suffix(self.config.include_formula_in_checking)
        for instance in instances:
            sum_kl = 0
            for interpolation_index in range(self.config.K):
                absorption_result_path = get_absorption_result_path(
                    instance,
                    self.config.K,
                    interpolation_index,
                    "cadical",
                    include_formula_suffix,
                    reverse=self.config.reverse,
                    base_dir=res_directory,
                )
                if not os.path.exists(absorption_result_path):
                    print(f"Absorption result file {absorption_result_path} does not exist, skipping")
                    continue
                absorption_result = json.load(open(absorption_result_path, "r"))
                for proof_index in range(1, self.config.K):
                    pass_count = 0
                    total_count = 0
                    for clause in absorption_result:
                        # if str(proof_index) not in absorption_result[clause]:
                        #     continue
                        # print(f"proof_index: {proof_index}, clause: {clause}")
                        if str(proof_index) not in absorption_result[clause]:
                            continue
                        if absorption_result[clause][str(proof_index)]:
                            pass_count += 1
                        total_count += 1
                    # if total_count == 0:
                    #     print(absorption_result)
                    if total_count == 0:
                        continue
                    percentage = pass_count / total_count
                    sum_kl += percentage
            kl_divergence[instance] = sum_kl / self.config.K / self.config.K
        return kl_divergence

    def manage(self):
        # instance_list = get_instance_list(self.config.category)
        instance_list = self.config.instance_list
        for instance in instance_list:
        # for instance in ["6s4"]:   
            failed = False
            for index in range(self.config.K):
                smt_cnf = get_smtcnf_path(instance, self.config.K, index, reverse=self.config.reverse)
                if not os.path.exists(smt_cnf):
                    print(f"SMT CNF file {smt_cnf} does not exist, skipping")
                    continue
                if os.path.getsize(smt_cnf) == 0:
                    print(f"SMT CNF file {smt_cnf} is empty, skipping")
                    continue
            if failed:
                # print(f"Not skipping for now, dummy interpolant will be used")
                print(f"Skipping {instance} for index because it failed during interpolation")
                continue
            cmd = f"python scripts/AbsorptionExperiment.py --instance {instance} --K {self.config.K} --category {self.config.category}"
            if self.config.reverse:
                cmd += " --reverse"
            log_path = f"{self.config.log_dir}/Absorption.{instance}.{self.config.K}{'.reverse' if self.config.reverse else ''}"
            if self.config.use_pbh_proof:
                cmd += " --use_pbh_proof"
                log_path += ".pbh."
            if self.config.include_formula_in_checking:
                cmd += " --include_formula_in_checking"
                log_path += ".include_formula_in_checking."
            if self.config.use_minisat_proof:
                cmd += " --use_minisat_proof"
                log_path += ".minisat.log"
            elif self.config.use_glucose_proof:
                cmd += " --use_glucose_proof"
                log_path += ".glucose.log"
            else:
                log_path += ".cadical.log"

            self.queue_command_in_slurm(cmd,mem="64g",time="12:00:00",output=log_path,cpus_per_task=MAX_WORKERS)
        self.execute_queued_command_in_slurm()
        self.end()

    def experiment_main(self):
        assert(len(self.config.instance_list) == 1)
        self.process_single_instance()
        self.end()

    def on_end(self):
        pass

def select_instances_from_csv(csv_path="./dashboard_data.csv", category=None):
    # instance_list = ["6s4"]
    instance_list = []
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if row[9] == "success (10/10)" and (category is None or row[1] == category):
                print("matching instance: ", row[0])
                instance_list.append(row[0])
    return instance_list

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--main", action="store_true", default=False)
    parser.add_argument("--from_summary", type=str, default=None, help="CSV path with columns: instance_name,K,smt2cnf_status; will run absorption for rows where smt2cnf_status=done")
    parser.add_argument("--instance", type=str, default=None)
    parser.add_argument("--test", action="store_true", default=False)
    parser.add_argument("--force_instance", type=str, default=None)
    parser.add_argument("--clean", action="store_true", default=False)
    parser.add_argument("--draw", action="store_true", default=False)
    parser.add_argument("--use_minisat_proof", action="store_true", default=False)
    parser.add_argument("--use_glucose_proof", action="store_true", default=False)
    parser.add_argument("--draw_all", action="store_true", default=False)
    parser.add_argument("--check_result", action="store_true", default=False)
    parser.add_argument("--include_formula_in_checking", action="store_true", default=True)
    parser.add_argument("--not_include_formula_in_checking", action="store_true", default=False)
    parser.add_argument("--check_minisat_result", action="store_true", default=False)
    parser.add_argument("--use_pbh_proof", action="store_true", default=False)
    parser.add_argument(
        "--reverse",
        dest="reverse",
        action="store_true",
        help="use reverse interpolant / smtcnf files",
    )
    parser.add_argument(
        "--no_reverse",
        dest="reverse",
        action="store_false",
        help="disable reverse interpolant / smtcnf files",
    )
    parser.set_defaults(reverse=False)
    args = parser.parse_args()
    if args.not_include_formula_in_checking:
        args.include_formula_in_checking = False
    else:
        args.include_formula_in_checking = True
    # Batch mode: load (instance,K) from a CSV summary and submit absorption runs for those with SMT→CNF done
    if args.from_summary:
        summary_path = args.from_summary
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
            config = AbsorptionExperimentConfig(
                name="absorption",
                data_dir="data",
                result_dir="result",
                log_dir="log",
                K=K,
                category=args.category,
                force_instance=instance,
                use_minisat_proof=args.use_minisat_proof,
                use_glucose_proof=args.use_glucose_proof,
                include_formula_in_checking=args.include_formula_in_checking,
                use_pbh_proof=args.use_pbh_proof,
                reverse=args.reverse,
            )
            experiment = AbsorptionExperiment(config)
            experiment.manage()
        return
    if args.draw:
        assert args.instance is not None
        config = AbsorptionExperimentConfig(name="absorption", data_dir="data", result_dir="result", log_dir="log", K=args.K, category=args.category, force_instance=args.instance, use_minisat_proof=args.use_minisat_proof, use_glucose_proof=args.use_glucose_proof, include_formula_in_checking=args.include_formula_in_checking, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.draw_heatmap()
        return
    
    if args.check_minisat_result:
        assert(args.instance is None)
        config = AbsorptionExperimentConfig(name="absorption", data_dir="data", result_dir="result", log_dir="log", K=args.K, category=args.category, force_instance=args.force_instance, use_minisat_proof=True, use_glucose_proof=args.use_glucose_proof, include_formula_in_checking=args.include_formula_in_checking, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.check_minisat_result()
        return
    
    if args.check_result:
        assert(args.instance is None)
        config = AbsorptionExperimentConfig(name="absorption", data_dir="data", result_dir="result", log_dir="log", K=args.K, category=args.category, force_instance=args.force_instance, use_minisat_proof=args.use_minisat_proof, use_glucose_proof=args.use_glucose_proof, include_formula_in_checking=args.include_formula_in_checking, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.check_result()
        return
    
    if args.draw_all:
        assert(args.instance is None)
        config = AbsorptionExperimentConfig(name="absorption", data_dir="data", result_dir="result", log_dir="log", K=args.K, category=args.category, force_instance=args.force_instance, use_minisat_proof=args.use_minisat_proof, use_glucose_proof=args.use_glucose_proof, include_formula_in_checking=args.include_formula_in_checking, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.draw_heatmap_all()

    if args.clean:
        os.system(f"rm {get_absorption_experiments_dir(args.K)}/*.json")
        os.system(f"rm {get_absorption_experiments_dir(args.K)}/caches/*")

    if args.main:
        # assert(args.instance is None)
        config = AbsorptionExperimentConfig(name="absorption", data_dir="data", result_dir="result", log_dir="log", K=args.K, category=args.category, force_instance=args.force_instance, use_minisat_proof=args.use_minisat_proof, use_glucose_proof=args.use_glucose_proof,
        include_formula_in_checking=args.include_formula_in_checking, use_pbh_proof=args.use_pbh_proof, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.manage()
        # experiment.run()
        return
    
    if args.instance is not None:
        instance = args.instance
        K = args.K
        config = AbsorptionExperimentConfig(
            name="absorption",
            data_dir="data",
            result_dir="result",
            log_dir="log", K=K,
            category=args.category,
            force_instance=instance, use_minisat_proof=args.use_minisat_proof, use_glucose_proof=args.use_glucose_proof, include_formula_in_checking=args.include_formula_in_checking, use_pbh_proof=args.use_pbh_proof, reverse=args.reverse)
        experiment = AbsorptionExperiment(config)
        experiment.run()
        return
    
    if args.test:
        # Lightweight test flow with synthetic data
        # instance = "6s209b0"
        K = 11
        test_instances = ["intel020"]
        for instance in test_instances:
            config = AbsorptionExperimentConfig(
                name="absorption",
                data_dir="data",
                result_dir="result",
                log_dir="log",
                K=K,
                category=args.category,
                force_instance=instance,
                use_minisat_proof=args.use_minisat_proof,
                use_glucose_proof=args.use_glucose_proof,
                include_formula_in_checking=args.include_formula_in_checking,
                use_pbh_proof=args.use_pbh_proof,
                reverse=args.reverse,
            )
            experiment = AbsorptionExperiment(config)
            experiment.process_single_instance()
        return


if __name__ == "__main__":
    main()