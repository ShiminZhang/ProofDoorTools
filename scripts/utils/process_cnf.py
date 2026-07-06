import os
import json
# from debug.logging import LOG, LOG_TAG
from tqdm import tqdm
from utils.utils import literal_to_expr, clause_to_expr, block_to_and_expr, parse_interpolant_cnf_to_dimacs_nice_format
import argparse
import numpy as np
# from catagory import get_instance_list
from utils.catagory import get_instance_list
import logging
# from typing import List, Set, Dict, Optional

def read_proof(proof_path):
    clauses = []
    with open(proof_path, "r") as file:
        lines = file.readlines()
        if len(lines) == 0:
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! proof file {proof_path} is empty")
            # return {}
        for line in lines:

            if line.startswith("d "):
                continue
            elif line.startswith("0"):
                continue
            elif line.startswith("p "):
                continue
            else:
                clauses.append([int(literal) for literal in line.strip().split(" ") if literal != "" and literal != "0"])
    return clauses

# def convert_to_cnf(smtcnf_path,cnf_path):
#     # I should have this logic somewhere in the repo
#     parse_interpolant_cnf_to_dimacs(smtcnf_path,cnf_path)
#     pass
class CNF:
    def __init__(self,cnf_path=None, use_cache=False, skip_parse_literal_map=False):
        if cnf_path is not None and cnf_path.endswith(".smtcnf"):
            self.smtcnf_format = True
        else:
            self.smtcnf_format = False

        if self.smtcnf_format:
            smtcnf_path = cnf_path
            converted_cnf_path = cnf_path.replace(".smtcnf", ".cnf")
            try:
                parse_interpolant_cnf_to_dimacs_nice_format(smtcnf_path, converted_cnf_path)
                cnf_path = converted_cnf_path
            except Exception as e:
                print(f"parsing meets error, but maybe the suffix is incorrect. {e}")
                cnf_path = smtcnf_path

        self.cnf_path = cnf_path
        if cnf_path is not None:
            if cnf_path.endswith(".cnf"):
                self.cnf_obj_path = cnf_path.replace(".cnf", ".cnfobj.json")
            else:
                self.cnf_obj_path = cnf_path + ".cnfobj.json"
        else:
            self.cnf_obj_path = None
        self.clauses = []
        self.N = None
        self.L = None
        self.iter_map = {}
        self.literal_set = set()
        self.literal_map = {}
        self.K = -1

        if cnf_path is not None:
            self.parse_cnf()
            if not skip_parse_literal_map:
                self.parse_literal_map(use_cache)
        
    
    @classmethod
    def from_file(cls, cnf_path, **kwargs):
        return cls(cnf_path, **kwargs)
    
    def get_variables_local_in_A(self, i):
        literals_in_A = set()
        for iter_idx in range(i+1):
            literals_in_A.update(self.literal_map[iter_idx])
        # print(f"literals_in_A: {literals_in_A}")    
        literals_in_B = set()
        for iter_idx in range(i+1, self.K):
            literals_in_B.update(self.literal_map[iter_idx])
        # print(f"literals_in_B: {literals_in_B}")
        # print(self.literal_map)
        return literals_in_A - literals_in_B
    
    def get_smt_definitions(self):
        smt_definitions = []
        variables = set()
        for literal in self.literal_set:
            variable = abs(literal)
            variables.add(variable)
        for variable in variables:
            smt_definitions.append(f"(declare-const v{variable} Bool)")
        return smt_definitions

    def to_smt(self):
        clauses_in_smt = block_to_and_expr(self.clauses)
        # for clause in self.clauses:
        #     clauses_in_smt.append(clause_to_expr(clause))
        return clauses_in_smt

    def get_variables_local_in_B(self, i):
        literals_in_B = set()
        for iter_idx in range(i+1, self.K):
            literals_in_B.update(self.literal_map[iter_idx])
        literals_in_A = set()
        for iter_idx in range(i):
            literals_in_A.update(self.literal_map[iter_idx])
        return literals_in_B - literals_in_A
    
    def get_variables_global(self, i):
        literals_in_global = self.literal_set
        return literals_in_global - self.get_variables_local_in_A(i) - self.get_variables_local_in_B(i)

    def get_variables_in_iter(self, i):
        return set(self.literal_map.get(i, set()))

    def get_variables_shared_between_adjacent_iters(self, left_iter, right_iter):
        if right_iter != left_iter + 1:
            raise ValueError("Only adjacent iteration blocks are supported")
        return self.get_variables_in_iter(left_iter) & self.get_variables_in_iter(right_iter)

    def get_variables_local_in_iter(self, i):
        current = self.get_variables_in_iter(i)
        previous = self.get_variables_in_iter(i - 1) if i > 0 else set()
        future = set()
        for iter_idx in range(i + 1, self.K):
            future.update(self.literal_map[iter_idx])
        return current - previous - future

    def get_progressive_shared_local_elim_set(self, i):
        if i < 0 or i >= self.K:
            raise IndexError(f"iteration index out of range: {i}")
        elim_vars = set()
        for iter_idx in range(i):
            elim_vars.update(self.get_variables_shared_between_adjacent_iters(iter_idx, iter_idx + 1))
        elim_vars.update(self.get_variables_local_in_iter(i))
        return elim_vars

    def write_progressive_shared_local_qdimacs(self, output_dir, file_stem=None):
        os.makedirs(output_dir, exist_ok=True)
        if file_stem is None:
            if self.cnf_path is None:
                raise ValueError("file_stem is required when CNF has no source path")
            file_stem = os.path.basename(self.cnf_path).removesuffix(".cnf")

        if self.clauses:
            max_var = max(abs(literal) for clause in self.clauses for literal in clause)
        else:
            max_var = 0
        num_clauses = len(self.clauses)
        all_vars = set(range(1, max_var + 1))

        output_paths = []
        for iter_idx in range(self.K):
            elim_vars = sorted(self.get_progressive_shared_local_elim_set(iter_idx))
            remaining_vars = sorted(all_vars - set(elim_vars))
            output_path = os.path.join(output_dir, f"{file_stem}.{iter_idx}.qdimacs")
            with open(output_path, "w") as f:
                f.write(f"p cnf {max_var} {num_clauses}\n")
                if elim_vars:
                    f.write("e " + " ".join(str(v) for v in elim_vars) + " 0\n")
                if remaining_vars:
                    f.write("a " + " ".join(str(v) for v in remaining_vars) + " 0\n")
                for clause in self.clauses:
                    f.write(" ".join(str(lit) for lit in clause) + " 0\n")
            output_paths.append(output_path)
        return output_paths
    
    def parse_cnf(self):
        with open(self.cnf_path, 'r') as file:
            line_count = 0
            self.iter_map[0] = 0
            iter_count = 1
            for line in file:
                if line.startswith('p cnf'):
                    _, _, L , N = line.split()
                    self.N = int(N)
                    self.L = int(L)
                elif line.startswith('c'):
                    if line.startswith('c iter'):
                        self.iter_map[iter_count] = line_count
                        iter_count += 1
                    continue
                elif line.startswith('v'):
                    continue
                else:
                    # Split the line into literals and remove the trailing 0
                    literals = [int(x) for x in line.strip().split() if x != '0']
                    if literals:  # Only add non-empty clauses
                        self.clauses.append(literals)
                        line_count += 1
            self.K = iter_count - 1
            if self.N is None or self.L is None:
                self.L = len(self.clauses)
                if self.L == 0:
                    self.N = 0
                else:
                    self.N = max(max(abs(literal) for literal in clause) for clause in self.clauses)
            # assert self.N is not None and self.L is not None
            self.parse_literals()

    def dump_stats(self):
        print(f"N: {self.N}, L: {self.L}")
        print(f"Number of clauses: {len(self.clauses)}")
        print(f"Number of literals: {len(self.literal_set)}")
        print(f"Number of unique literals: {len(self.literal_set)}")
        print(f"Number of clauses: {len(self.clauses)}")
        print(self.iter_map)

    def append_clause(self, clause):
        if not isinstance(clause, list):
            raise TypeError("Clause must be a list of integers")
        if not all(isinstance(x, int) for x in clause):
            raise TypeError("All elements in clause must be integers")
        if not clause:
            raise ValueError("Clause cannot be empty")
        self.clauses.insert(0,clause)
        self.N += 1
        self.L = max(self.L, max(abs(literal) for literal in clause))
        self.parse_literals()
        return self
    
    def parse_literals(self):
        assert self.clauses is not None
        for iter_index in range(self.K+1):
            self.literal_map[iter_index] = set()
        for clause in self.clauses:
            for literal in clause:
                self.literal_set.add(literal)

    def parse_literal_map(self, use_cache=False):
        logger = logging.getLogger("proofdoor.worker")
        logger.info("parse_literal_map from file: %s", self.cnf_path)
        iter_index = 0
        clause_index = 0
        if use_cache and os.path.exists(self.cnf_obj_path):
            logger.info("use_cache: %s", self.cnf_obj_path)
            result = json.load(open(self.cnf_obj_path, 'r'))
            literal_map = result['literal_map']
            for key in literal_map:
                self.literal_map[int(key)].update(literal_map[key])
            self.literal_set = set(result['literal_set'])
            return
        
        for clause in self.clauses:
            # find which iteration the clause belongs to
            if self.iter_map[iter_index] <= clause_index and (iter_index == self.K or self.iter_map[iter_index+1] > clause_index):
                # clause belongs to the current iteration
                pass
            else:
                # clause belongs to the next iteration
                iter_index += 1
                assert iter_index <= self.K and clause_index == self.iter_map[iter_index], f"iter_index: {iter_index}, clause_index: {clause_index}, self.iter_map[iter_index]: {self.iter_map[iter_index]}"
            
            for literal in clause:
                self.literal_map[iter_index].add(abs(literal))
                self.literal_set.add(abs(literal))
            clause_index += 1
        cnfobj = {}
        literal_map_obj = {}
        for key in self.literal_map:
            literal_map_obj[key] = list(self.literal_map[key])
        last_occurrence_map = {}
        for literal in self.literal_set:
            last_occurrence_map[literal] = -1

            for i,literals in self.literal_map.items():
                if abs(literal) in literals:
                    last_occurrence_map[literal] = i
                    break
            
            assert last_occurrence_map[literal] != -1, f"literal: {literal}"
        cnfobj['literal_map'] = literal_map_obj
        cnfobj['literal_set'] = list(self.literal_set)
        cnfobj['last_occurrence_map'] = last_occurrence_map
        self.last_occurrence_map = last_occurrence_map
        json.dump(cnfobj, open(self.cnf_obj_path, 'w'))
    
    def get_clauses(self):
        return self.clauses
    
    def get_N(self):
        return self.N
    
    def get_L(self):
        return self.L
    
    def get_clause_at(self, index):
        return self.clauses[index]
    
    def get_iter_map(self):
        return self.iter_map
    
    def get_literals(self):
        return self.literal_set
    
    def init_with_clauses(self,clauses):
        # LOG_TAG(f"init_with_clauses: {clauses}", "detailed")
        self.clauses = clauses
        self.N = len(clauses)
        if len(clauses) == 0:
            self.L = 0   
            self.iter_map = {}
            return         
        self.L = max(max(abs(literal) for literal in clause) for clause in clauses if len(clause) > 0)
        self.iter_map = {}
        self.parse_literals()
    
    def get_A(self, i):
        clauses = self.clauses[0:self.iter_map[i+1]]
        A = CNF()
        A.init_with_clauses(clauses)
        return A
    
    def get_B(self, i):
        clauses = self.clauses[self.iter_map[i+1]:]
        B = CNF()
        B.init_with_clauses(clauses)
        return B
    
    def to_dimacs(self, file_path):
        """Write the CNF formula to a file in DIMACS format."""
        with open(file_path, 'w') as f:
            # Write header
            f.write(f"p cnf {self.L} {self.N}\n")
            # Write clauses
            # Insert iteration boundary comments like original CNFs: "c iter <i>"
            # self.iter_map maps iter_index -> start clause index of that iteration block.
            boundary_at = {}
            for iter_idx, start in (self.iter_map or {}).items():
                try:
                    boundary_at[int(start)] = int(iter_idx)
                except Exception:
                    continue

            for clause_idx, clause in enumerate(self.clauses):
                if clause_idx in boundary_at:
                    f.write(f"c iter {boundary_at[clause_idx]} \n")
                f.write(" ".join(str(lit) for lit in clause) + " 0\n")
        return file_path

def compute_cnf_size_for_category(category,K,use_cache=False,interested_instances=None):
    instance_list = get_instance_list(category)
    if interested_instances is not None:
        instance_list = interested_instances
    if use_cache and os.path.exists(f'ProofDoorBenchmark/cnfs/{K}/{category}_cnfs_sizes.json'):
        cnf_sizes = json.load(open(f'ProofDoorBenchmark/cnfs/{K}/{category}_cnfs_sizes.json', 'r'))
    else:
        cnf_sizes = {}
        for instance in instance_list:
            cnf_path = f"ProofDoorBenchmark/cnfs/{K}/{instance}.{K}.cnf"
            if os.path.exists(cnf_path):
                with open(cnf_path, 'r') as file:
                    for line in file:
                        if line.startswith('p cnf'):
                            _, _, N , L = line.split()
                            cnf_sizes[instance] = int(L)
                            break
                # cnf_sizes[instance] = 
        json.dump(cnf_sizes, open(f'ProofDoorBenchmark/cnfs/{K}/{category}_cnfs_sizes.json', 'w'))
    return cnf_sizes

def get_N_of_literals(cnf_path):
    with open(cnf_path, 'r') as file:
        for line in file:
            if line.startswith('p cnf'):
                _, _, N , L = line.split()
                return int(N)
    return None

def compute_N_map(K,use_cache=False):
    N_map = {}
    if use_cache and os.path.exists(f'ProofDoorBenchmark/cnfs/{K}/N_map.json'):
        N_map = json.load(open(f'ProofDoorBenchmark/cnfs/{K}/N_map.json', 'r'))
    else:
        for file in tqdm(os.listdir(f'ProofDoorBenchmark/cnfs/{K}')):
            if file.endswith('.cnf'):
                N_map[file] = get_N_of_literals(f'ProofDoorBenchmark/cnfs/{K}/{file}')
        json.dump(N_map, open(f'ProofDoorBenchmark/cnfs/{K}/N_map.json', 'w'))
    return N_map

def compute_cnf_sizes(cnf_path,K,use_cache=False):
    cnf_sizes = {}
    if use_cache and os.path.exists(f'ProofDoorBenchmark/cnfs/{K}/cnfs_sizes.json'):
        cnf_sizes = json.load(open(f'ProofDoorBenchmark/cnfs/{K}/cnfs_sizes.json', 'r'))
    else:
        for file in tqdm(os.listdir(cnf_path)):
            if file.endswith('.cnf'):
                cnf_sizes[file] = os.path.getsize(os.path.join(cnf_path, file))
    json.dump(cnf_sizes, open(f'ProofDoorBenchmark/cnfs/{K}/cnfs_sizes.json', 'w'))
    return cnf_sizes

if __name__ == "__main__":
    K = 10
    instance = "beembrptwo6b1"
    CNF_path = f"ProofDoorBenchmark/cnfs/{K}/{instance}.{K}.cnf"
    cnf = CNF.from_file(CNF_path)
    print(cnf.get_N())
    print(cnf.get_L())
    print(cnf.get_clauses())
    print(cnf.get_iter_map())
    print(cnf.get_literals())
    print(cnf.get_literal_map())
    print(cnf.get_literal_set())
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--K", type=int, required=True)
    # parser.add_argument("--UseCache", action="store_true")
    # parser.add_argument("--Category", type=str, required=False)
    # args = parser.parse_args()
    # if args.Category:
    #     print(f"Computing CNF sizes for category: {args.Category}")
    #     cnf_sizes = compute_cnf_size_for_category(args.Category,args.K,args.UseCache)
    # else:
    #     cnf_sizes = compute_cnf_sizes(f"ProofDoorBenchmark/cnfs/{args.K}",args.K,args.UseCache)
        
    # average_cnf_size = sum(cnf_sizes.values()) / len(cnf_sizes)
    # std_cnf_size = np.std(list(cnf_sizes.values()))
    # print(f"Average CNF size: {average_cnf_size}")
    # print(f"Standard deviation of CNF size: {std_cnf_size}")
    # print(f"Median CNF size: {np.median(list(cnf_sizes.values()))}")
    # print(f"Minimum CNF size: {min(list(cnf_sizes.values()))}")
    # print(f"Maximum CNF size: {max(list(cnf_sizes.values()))}")
    # print(f"CNF sizes: {len(cnf_sizes)}")
    # print(cnf_sizes)
