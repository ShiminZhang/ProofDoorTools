import os
import json
from tqdm import tqdm
import argparse
import numpy as np

def compute_cnf_sizes(cnf_path,K,use_cache=False):
    cnf_sizes = {}
    if use_cache and os.path.exists(f'./cnfs/{K}/cnfs_sizes.json'):
        cnf_sizes = json.load(open(f'./cnfs/{K}/cnfs_sizes.json', 'r'))
    else:
        for file in tqdm(os.listdir(cnf_path)):
            if file.endswith('.cnf'):
                cnf_sizes[file] = os.path.getsize(os.path.join(cnf_path, file))
    json.dump(cnf_sizes, open(f'./cnfs/{K}/cnfs_sizes.json', 'w'))
    return cnf_sizes

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--UseCache", action="store_true")
    
    args = parser.parse_args()
    cnf_sizes = compute_cnf_sizes(f"./cnfs/{args.K}",args.K,args.UseCache)
        
    average_cnf_size = sum(cnf_sizes.values()) / len(cnf_sizes)
    std_cnf_size = np.std(list(cnf_sizes.values()))
    print(f"Average CNF size: {average_cnf_size}")
    print(f"Standard deviation of CNF size: {std_cnf_size}")
    print(f"Median CNF size: {np.median(list(cnf_sizes.values()))}")
    print(f"Minimum CNF size: {min(list(cnf_sizes.values()))}")
    print(f"Maximum CNF size: {max(list(cnf_sizes.values()))}")
    print(f"CNF sizes: {len(cnf_sizes)}")
    print(cnf_sizes)
