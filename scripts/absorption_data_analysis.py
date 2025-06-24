import json
import os
import argparse
from utils.utils import group_files_by_basename, GetData, RewriteMap, GetDataFromLog
from utils.paths import get_absorption_experiments_dir, get_CNF_dir, get_exp_pbh_dir,get_interpolant_cnf_dir,get_interpolant_dimacs_dir
from utils.process_cnf import compute_cnf_size_for_category
from debug import logging
import warnings


class AbsorptionDataAnalyzer:
    def __init__(self, interested_names, K, solver='cadical'):
        self.keys = interested_names
        self.solver = solver
        self.solver_bin = "./solvers/cadical"
        self.K = K
        self.data = {}
        data,solving_time_map,par2,mem = GetData(f"./ProofDoorBenchmark/cnfs/{K}/", solver, True)
        self.data["par2"] = par2
        self.init_solving_times(solving_time_map)
        pbh_dir = get_exp_pbh_dir(K)
        data_pbh,map_pbh,par2_pbh,mem_pbh = GetData(pbh_dir,"top_100.minisat")
        data_original,map_original,par2_original,mem_original = GetData(pbh_dir,"original.minisat")
        self.init_pbh_solving_times(map_pbh)
    
    def run_solver(self,name, override_cnf=None):
        extra_flags = "--reduce=0 --restoreall=2 --flush=0 --no-binary"
        if override_cnf is None:
            cnf_dir = get_CNF_dir(self.K)
            cnf_path = f"{cnf_dir}/{name}.{self.K}.cnf"
            log_path = f"{cnf_dir}/{name}.{self.K}.{self.solver}.log"
        else:
            cnf_path = override_cnf
            log_path = f"{override_cnf}.{self.solver}.log"
        cmd = f"{self.solver_bin} {extra_flags} {cnf_path} > {log_path}"
        os.system(cmd)
        return log_path
    
    def init_solving_times(self,solving_time_map):
        self.solving_times = RewriteMap(solving_time_map)
        self.solving_times = {k:v for k,v in self.solving_times.items() if k in self.keys}
        for k in self.keys:
            if k not in self.solving_times:
                logging.LOG(f"Solving data not found for {k}")
                self.run_solver(k)
        
    def init_pbh_solving_times(self,map_pbh):
        self.pbh_solving_times = RewriteMap(map_pbh)
        self.pbh_solving_times = {k:v for k,v in self.pbh_solving_times.items() if k in self.keys}
        # for key in self.keys:
        #     if key not in self.pbh_solving_times:
        #         logging.LOG(f"PBH solving data not found for {key}")
                # self.run_solver(key)

    def get_solving_time(self,name):
        if name not in self.keys:
            logging.LOG(f"Name {name} not found in the data")
            return None
        if name not in self.solving_times:
            output_path = self.run_solver(name)
            res = GetDataFromLog(output_path)
            self.solving_times[name] = res
        return self.solving_times[name]

    def get_pbh_solving_time(self,name):
        if name not in self.keys:
            logging.LOG(f"Name {name} not found in the data")
            return None
        elif name in self.pbh_solving_times:
            return self.pbh_solving_times[name]
        else:
            logging.LOG(f"PBH solving data not found for {name}")
            return None

    def get_cnf_size(self,name):
        cnf_file = f"{get_CNF_dir(self.K)}/{name}.{self.K}.cnf"
        with open(cnf_file, 'r') as f:
            line_count = sum(1 for line in f)
        return line_count

    def get_pd_size(self,name):
        pd_size = 0
        for i in range(1,int(self.K)+1):
            interpolant_cnf_path = f"{get_interpolant_dimacs_dir()}/{name}.{self.K}.index_{i-1}.dimacs"
            assert(os.path.exists(interpolant_cnf_path))
            with open(interpolant_cnf_path, 'r') as f:
                line_count = sum(1 for line in f)
            pd_size += line_count
        return pd_size

    def get_solving_time_after_pd_combined(self,name):
        combined_dir = get_interpolant_dimacs_dir()
        combined_cnf = f"{combined_dir}/{name}.{self.K}.combined.cnf"
        combined_output = f"{combined_dir}/{name}.{self.K}.combined.cnf.{self.solver}.log"
        if not os.path.exists(combined_cnf):
            self.run_solver(name,combined_cnf)
            assert os.path.exists(combined_cnf)
        if not os.path.exists(combined_output):
            self.run_solver(name,combined_cnf)
            assert os.path.exists(combined_output)
        res = GetDataFromLog(combined_output)
        assert res is not None
        return res

    def analyze(self,name):
        output={}
        output["name"] = name
        output["solving_time"] = self.get_solving_time(name)
        # output["pbh_solving_time"] = self.get_pbh_solving_time(name)
        output["cnf_size"] = self.get_cnf_size(name)
        output["pd_size"] = self.get_pd_size(name)
        # output["solving_time_after_pd_combined"] = self.get_solving_time_after_pd_combined(name)
        return output


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=str, required=True)
    return parser.parse_args()

def main():
    interested_names= [
        "intel020"
    ]
    logging.TOGGLE_SHOWLOG(True)
    args = parse_args()
    analyzer = AbsorptionDataAnalyzer(interested_names, args.K)
    output = analyzer.analyze("intel020")
    json.dump(output, open("output.json", "w"), indent=4)

if __name__ == "__main__":
    main()