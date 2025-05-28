import os
import json
from tqdm import tqdm
import argparse
import numpy as np
# from catagory import get_instance_list
from utils.catagory import get_instance_list
# from typing import List, Set, Dict, Optional

class CNF:
    def __init__(self,cnf_path=None):
        self.cnf_path = cnf_path
        self.clauses = []
        self.N = None
        self.L = None
        self.iter_map = {}
        self.literal_set = set()
        self.K = -1
        if cnf_path is not None:
            self.parse_cnf()
    
    @classmethod
    def from_file(cls, cnf_path):
        return cls(cnf_path)
    
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
                    literals = [int(x) for x in line.strip().split()[:-1]]
                    if literals:  # Only add non-empty clauses
                        self.clauses.append(literals)
                        line_count += 1
            self.K = iter_count - 1
            assert self.N is not None and self.L is not None
            print(f"N: {self.N}, L: {self.L}")
            print(f"Number of clauses: {len(self.clauses)}")
            # assert len(self.clauses) == self.N
            self.parse_literals()
            # self.dump_stats()
            # assert len(self.literal_set) == self.L

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
        for clause in self.clauses:
            for literal in clause:
                self.literal_set.add(literal)
    
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
        self.clauses = clauses
        self.N = len(clauses)
        self.L = max(max(abs(literal) for literal in clause) for clause in clauses)
        self.iter_map = {}
        self.parse_literals()
    
    def get_A(self, i):
        clauses = self.clauses[0:self.iter_map[i]]
        A = CNF()
        A.init_with_clauses(clauses)
        return A
    
    def get_B(self, i):
        clauses = self.clauses[self.iter_map[i]:]
        B = CNF()
        B.init_with_clauses(clauses)
        return B
    
    def to_dimacs(self, file_path):
        """Write the CNF formula to a file in DIMACS format."""
        with open(file_path, 'w') as f:
            # Write header
            f.write(f"p cnf {self.L} {self.N}\n")
            # Write clauses
            for clause in self.clauses:
                f.write(" ".join(str(lit) for lit in clause) + " 0\n")
        return file_path

def compute_cnf_size_for_category(category,K,use_cache=False):
    instance_list = get_instance_list(category)
    if use_cache and os.path.exists(f'ProofDoorBenchmark/cnfs/{K}/{category}_cnfs_sizes.json'):
        cnf_sizes = json.load(open(f'ProofDoorBenchmark/cnfs/{K}/{category}_cnfs_sizes.json', 'r'))
    else:
        cnf_sizes = {}
        for instance in instance_list:
            cnf_path = f"ProofDoorBenchmark/cnfs/{K}/{instance}.{K}.cnf"
            if os.path.exists(cnf_path):
                cnf_sizes[instance] = os.path.getsize(cnf_path)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--UseCache", action="store_true")
    parser.add_argument("--Category", type=str, required=False)
    args = parser.parse_args()
    if args.Category:
        print(f"Computing CNF sizes for category: {args.Category}")
        cnf_sizes = compute_cnf_size_for_category(args.Category,args.K,args.UseCache)
    else:
        cnf_sizes = compute_cnf_sizes(f"ProofDoorBenchmark/cnfs/{args.K}",args.K,args.UseCache)
        
    average_cnf_size = sum(cnf_sizes.values()) / len(cnf_sizes)
    std_cnf_size = np.std(list(cnf_sizes.values()))
    print(f"Average CNF size: {average_cnf_size}")
    print(f"Standard deviation of CNF size: {std_cnf_size}")
    print(f"Median CNF size: {np.median(list(cnf_sizes.values()))}")
    print(f"Minimum CNF size: {min(list(cnf_sizes.values()))}")
    print(f"Maximum CNF size: {max(list(cnf_sizes.values()))}")
    print(f"CNF sizes: {len(cnf_sizes)}")
    # print(cnf_sizes)
