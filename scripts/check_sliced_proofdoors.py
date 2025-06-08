import os
import json
from utils.utils import GetData
from utils.paths import get_CNF_dir

def main():
    # get all the files in the sliced_proofdoors folder
    k_value = 40
    solver = "minisat"
    combined_cnfs_dir = "./ProofDoorBenchmark/combined_cnfs/"
    original_cnfs_dir = get_CNF_dir(k_value)
    original_data,original_instance_time_map,par2,_ = GetData(original_cnfs_dir,solver, False)
    combined_data,combined_instance_time_map,par2,_ = GetData(combined_cnfs_dir,solver, False)
    print(len(combined_instance_time_map))
    print(len(original_instance_time_map))
    # Sort instance_time_map by key
    for key, value in sorted(combined_instance_time_map.items()):
        print(f"{key} :: {value}")
    
    sorted_instance_time_map = dict(sorted(combined_instance_time_map.items()))
    original_combined_map = {}
    basenames = set()
    # ignore_basenames = set(["beembrptwo3b2","dspfilters_fastfir_second-p16"])
    # print(original_instance_time_map)
    for key, value in combined_instance_time_map.items():
        basename = key.split(".")[0]
        # if basename not in ignore_basenames:
        basenames.add(basename)
        
    for basename in basenames:
        original_combined_map[basename] = [0] * (k_value + 1)
        cnf_key = basename + f".{k_value}.cnf.{solver}.log"
        original_combined_map[basename][0] = original_instance_time_map[cnf_key]
        for i in range(1,k_value + 1):
            combined_key = basename + f".{k_value}.combined.{i}.cnf.{solver}.log"
            if combined_key in combined_instance_time_map:
                original_combined_map[basename][i] = combined_instance_time_map[combined_key]
            
    with open("slicedexp_{solver}.json", "w") as f:
        json.dump(original_combined_map, f, indent=4)
    print(original_combined_map)
    print(sorted_instance_time_map)
    


if __name__ == "__main__":
    main()