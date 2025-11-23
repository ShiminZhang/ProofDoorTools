from experiments.experiment import Experiment, ExperimentConfig
from utils.paths import get_interpolant_dir, get_interpolant_cnf_dir, get_latest_PDC_result
from utils.parsing import parse_interpolant
from utils.catagory import get_instance_list
import argparse
from z3 import  *
import time
import json
import os

class SMTTranslationToCNFExperimentConfig(ExperimentConfig):
    def __init__(self, name, data_dir, result_dir, log_dir, K, category, force_instance=None, time="8:00:00"):
        super().__init__(name, data_dir, result_dir, log_dir)
        self.K = K
        self.instance_list = get_instance_list(category)
        if force_instance is not None:
            self.instance_list = [force_instance]
        self.category = category
        self.force_instance = force_instance
        self.time = time

class SMTTranslationToCNFExperiment(Experiment):
    def __init__(self, config: ExperimentConfig):
        super().__init__(config)

    def on_start(self):
        pass

    def on_end(self):
        pass

    
    def experiment_main(self):
        date_and_time_as_directory = self.start_time
        os.makedirs(f"{self.config.log_dir}/{date_and_time_as_directory}", exist_ok=True)
        # test
        # self.config.instance_list = ["6s4"]

        for instance in self.config.instance_list:
            # skip if not all interpolant files exist
            for index in range(self.config.K):
                interpolant_file = f"{get_interpolant_dir(self.config.K,1)}/{instance}.{self.config.K}.{index}.interpolant"
                if not os.path.exists(interpolant_file):
                    print(f"Interpolant file {interpolant_file} does not exist, skipping")
                    continue
                if os.path.getsize(interpolant_file) == 0:
                    print(f"Interpolant file {interpolant_file} is empty, skipping")
                    continue
                # also skip if smtcnf file exists
                smtcnf_file = f"{get_interpolant_cnf_dir(self.config.K,1)}/{instance}.{self.config.K}.{index}.smtcnf"
                if os.path.exists(smtcnf_file) and os.path.getsize(smtcnf_file) > 0:
                    print(f"SMT CNF file {smtcnf_file} exists, skipping")
                    continue

            for index in range(self.config.K):
                cmd = f"python scripts/SMTTranslationToCNFExperiment.py --instance {instance} --K {self.config.K} --index {index}"
                # os.system(cmd)
                self.queue_command_in_slurm(cmd,mem="20g",time=self.config.time,output=f"{self.config.log_dir}/{date_and_time_as_directory}/SMT_to_CNF.{instance}.{self.config.K}.{index}.log")
                print(cmd)
        self.execute_queued_command_in_slurm()
        self.end()

def is_literal(expr):
    # 情况1：是布尔变量
    if is_const(expr) and expr.sort().kind() == Z3_BOOL_SORT:
        return True

    # 情况2：是 (Not p) 且 p 是布尔常量
    if expr.decl().kind() == Z3_OP_NOT:
        child = expr.children()[0]
        return is_const(child) and child.sort().kind() == Z3_BOOL_SORT

    return False

_CNF_CACHE = {}


def expand_to_cnf(expr, simplify=False):
    """
    将 Z3 表达式（NNF）转换为 CNF 子句列表。
    输出格式：list[list[z3.ExprRef]]
    """
    if not simplify:
        assert False, "simplify should be True"
    else:
        cache_key = (expr.get_id(), simplify)
        # print(f"expanding {expr.get_id()} to cnf， size: {len(expr)}")
        if cache_key in _CNF_CACHE:
            return _CNF_CACHE[cache_key]

        if is_literal(expr):
            result = (frozenset((expr,)),)
            _CNF_CACHE[cache_key] = result
            return result

        # Conjunction: merge all sub-clauses
        elif is_and(expr):
            clauses = []
            for sub in expr.children():
                clauses.extend(expand_to_cnf(sub, True))
            result = simplify_and_subsume(clauses)
            _CNF_CACHE[cache_key] = result
            return result

        # Disjunction: apply distributive law incrementally to avoid materializing the full Cartesian product
        elif is_or(expr):
            sub_cnf_list = [expand_to_cnf(sub, True) for sub in expr.children()]
            combined = (frozenset(),)
            for sub_cnf in sub_cnf_list:
                sub_clause_sets = [clause if isinstance(clause, frozenset) else frozenset(clause) for clause in sub_cnf]
                new_clauses = []
                seen = set()
                for base_clause in combined:
                    for clause_set in sub_clause_sets:
                        merged_literals = base_clause | clause_set
                        if _is_tautological_clause(merged_literals):
                            continue
                        if merged_literals in seen:
                            continue
                        new_clauses.append(merged_literals)
                        seen.add(merged_literals)
                combined = simplify_and_subsume(new_clauses)
            _CNF_CACHE[cache_key] = combined
            return combined
        
        result = (frozenset((expr,)),)
        _CNF_CACHE[cache_key] = result
        return result
        
def _is_tautological_clause(literals):
    """
    Return True if clause contains complementary literals (A ∨ ¬A).
    """
    for lit in literals:
        if is_not(lit):
            if lit.children()[0] in literals:
                return True
        elif Not(lit) in literals:
            return True
    return False
        
def _clause_sort_key(clause):
    return (len(clause), tuple(sorted(map(str, clause))))


def simplify_and_subsume(clauses):
    """
    对 CNF 子句集执行：
    1. 子句内去重 / tautology 消除
    2. 子句间 subsumption 吸收
    输入:  list[tuple[z3.ExprRef]]
    输出:  list[tuple[z3.ExprRef]]
    """

    # Step 1: 子句内部简化
    normalized = []
    for clause in clauses:
        clause_frozen = clause if isinstance(clause, frozenset) else frozenset(clause)
        lits = clause_frozen

        # 跳过永真子句: (A ∨ ¬A)
        if _is_tautological_clause(lits):
            continue

        normalized.append(clause_frozen)

    # Step 2: 按长度排序 (短句优先)
    normalized.sort(key=_clause_sort_key)

    # Step 3: 子句间 subsumption
    result = []
    for c in normalized:
        set_c = c
        # 若 result 中已有子句 d ⊂ c，则跳过 c
        if any(d.issubset(set_c) for d in result):
            continue
        result.append(c)

    return tuple(result)

# def distribute_or_over_and(f) -> list:
#     if is_or(f):
#         subs = [distribute_or_over_and(x) for x in f.children()]
#         and_children = [x for x in subs if is_and(x)]
#         if and_children:
#             first_and = and_children[0]
#             others = [x for x in subs if x is not first_and]
#             return [
#                 distribute_or_over_and(Or(y, *others))
#                 for y in first_and.children()
#             ]
#         else:
#             return Or(*subs)
#     elif is_and(f):
#         return [distribute_or_over_and(x) for x in f.children()]
#     else:
#         return f
def sanity_check(interpolant,smt_cnf_interpolant):
    # they should be equivalent
    s = Solver()
    original_interpolant = And(*interpolant)
    cnf_interpolant = And(*[Or(*cnf_clause) for cnf_clause in smt_cnf_interpolant])
    s.add(Not(original_interpolant == cnf_interpolant))
    return s.check() == unsat


def InterpolantToCNF(instance, K, index, simplify=False):
    _CNF_CACHE.clear()
    print("simplify in InterpolantToCNF", simplify)
    SMT_file = f"{get_interpolant_dir(K,1)}/{instance}.{K}.{index}.interpolant"
    SMT_CNF_file = f"{get_interpolant_cnf_dir(K,1)}/{instance}.{K}.{index}.smtcnf"
    if not os.path.exists(SMT_file):
        print(f"SMT file {SMT_file} does not exist, skipping")
        return None
    # if os.path.exists(SMT_CNF_file):
    #     print(f"SMT CNF file {SMT_CNF_file} exists, skipping")
    #     return SMT_CNF_file
    print(f"Parsing interpolant from {SMT_file}")
    interpolant = parse_interpolant(SMT_file)
    print(f"Interpolant: {interpolant}")
    # convert to NNF first
    goal = Goal()
    for f in interpolant:
        goal.add(f)
    nnf_tactic = Tactic('nnf')
    NNF_result = nnf_tactic(goal)
    simplify_tactic = Tactic('simplify')
    NNF_result = simplify_tactic(NNF_result[0])
    cnf_list = []
    # NNF prepared, convert to CNF
    print(f"NNF result: {NNF_result}")
    for nnf in NNF_result[0]:
        cnf_clauses = expand_to_cnf(nnf, simplify)
        cnf_list.extend(cnf_clauses)
    assert sanity_check(interpolant,cnf_list), "Sanity check failed for {instance}.{K}.{index}"
    with open(SMT_CNF_file, 'w') as f:
        for cnf_clause in cnf_list:
            for literal in sorted(cnf_clause, key=str):
                f.write(str(literal))
                f.write(" ")
            f.write("\n")
    return SMT_CNF_file



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", action="store_true", default=False)
    parser.add_argument("--instance", type=str, default=None)
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--category", type=str, default="exponential")
    parser.add_argument("--time", type=str, default="8:00:00")
    parser.add_argument("--simplify", action="store_true", default=True)
    parser.add_argument("--check_result", type=str, default=None)
    args = parser.parse_args()
    if args.main:
        config = SMTTranslationToCNFExperimentConfig(
            name="SMTTranslationToCNFExperiment",
            data_dir="data",
            result_dir="results",
            log_dir="logs",
            K=args.K,
            time=args.time,
            category=args.category,
            force_instance=None
        )
        experiment = SMTTranslationToCNFExperiment(config)
        experiment.run()
    elif args.check_result is not None:
        # read all log files in the logs directory
        instances = get_instance_list("exponential") + get_instance_list("linear")
        results = {}
        K = args.K or 10
        for instance in instances:
            results[instance] = {}

            for index in range(args.K):
                smt_cnf_file = f"{get_interpolant_cnf_dir(K,1)}/{instance}.{K}.{index}.smtcnf"
                if not os.path.exists(smt_cnf_file):
                    results[instance][index] = "smt2 file not found"
                elif os.path.getsize(smt_cnf_file) == 0:
                    results[instance][index] = "empty smt2 file"
                else:
                    results[instance][index] = "success"
        report={}
        for instance in instances:
            if instance not in results.keys():
                report[instance] = ("not started", -1,-1)
            else:
                all_success = True
                count_success = 0
                for index in range(K):
                    if results[instance][index] != "success":
                        all_success = False
                    else:
                        count_success += 1
                if all_success:
                    report[instance] = ("success", count_success, K)
                else:
                    report[instance] = ("partial done", count_success, K)
        # for log_file in log_files:
        #     instance = log_file.split(".")[1]
        #     K = log_file.split(".")[2]
        #     index = log_file.split(".")[3]
        #     with open(os.path.join(log_dir, log_file), "r") as f:
        #         content = f.read()
        #         if "error" in content:
        #             # check if the error is due to empty interpolant file
        #             interpolant_file = f"{get_interpolant_dir(K,1)}/{instance}.{K}.{index}.interpolant"
        #             size = os.path.getsize(interpolant_file)
        #             if size == 0:
        #                 results[log_file] = "empty interpolant file"
        #             else:
        #                 results[log_file] = "error"
        #         elif "NNF result: " in content:
        #             results[log_file] = "success"
        #         elif "SMT CNF file: None" in content:
        #             results[log_file] = "smt2 file not found"
        #         else:
        #             size = os.path.getsize(os.path.join(log_dir, log_file))
        #             if size == 0:
        #                 results[log_file] = "empty log file, likely due to timeout"
        #             else:
        #                 results[log_file] = "unknown"
        # sorted_results = sorted(results.items(), key=lambda x: x[0])
        # dict_results = {log_file.split(".")[1]: result for log_file, result in sorted_results}
        print(f"Saving report to Experiments/SMTTranslationToCNFExperiment/logs/results_{args.check_result}.json")
        with open(f"Experiments/SMTTranslationToCNFExperiment/logs/results_{args.check_result}.json", "w") as f:
            json.dump(report, f, indent=4)
        print(f"Saving report to {get_latest_PDC_result(K)}")
        with open(get_latest_PDC_result(K), "w") as f:
            json.dump(report, f, indent=4)
    else:
        instance = args.instance
        K = args.K
        index = args.index
        print(f"Processing {instance}.{K}.{index}")

        SMT_CNF_file = InterpolantToCNF(instance, K, index, args.simplify)
        print(f"SMT CNF file: {SMT_CNF_file}")
        
