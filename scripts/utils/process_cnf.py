import os
import json
from tqdm import tqdm
import argparse
import numpy as np
# from catagory import get_instance_list
from utils.catagory import get_instance_list

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
