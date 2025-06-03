import os
import sys
import shutil
from tqdm import tqdm
import json
from utils.paths import get_interpolant_dir, get_PDS_data_dir, get_PDS_dir, get_smts_dir
from count_interpolant_byz3 import count_by_z3, count_and_save
from utils.utils import parse_memory_limit
from utils.proofdoor_size import relocate_PDS_files, get_all_interpolant_files, get_uncomputed_interpolant_files,get_subsumed_PDS_interpolant_files

def compute_PDS(k_value,interpolants_to_compute,memory_limit=-1):
    PDS_dir = get_PDS_dir(k_value)
    json_files = os.listdir(PDS_dir)
    interpolant_dir = get_interpolant_dir(k_value)
    print(f"len(json_files): {len(json_files)}")
    smts_dir = get_smts_dir(k_value)
    basename_ignore=[]
    print(f"Checking {len(interpolants_to_compute)} uncomputed files")
    for file in tqdm(interpolants_to_compute):
        print(file)
        if file.endswith(".interpolant"):
            basename = file.split(".")[0]
            if basename in basename_ignore:
                print(f"Skipping {file} because it is in basename_ignore")
                continue
            # json_file = file.replace(".interpolant", ".json")
            # json_file = f"{file}.json"
            
            if memory_limit != -1:
                if os.path.getsize(os.path.join(interpolant_dir, file)) > memory_limit:
                    continue
                
            # if json_file not in json_files:
            print(f"Counting {file}")
            count,msg = count_and_save(
                os.path.join(interpolant_dir, file),
                os.path.join(smts_dir, file.replace(".interpolant", ".smt2")))
            if count < 0:
                print(f"Error counting {file}")
                basename_ignore.append(basename)
                    
def main():
    k_value = sys.argv[1]
    memory_limit = parse_memory_limit(sys.argv[2])
    if len(sys.argv) < 3:
        print("Usage: python check_uncomputed_PDS.py <k_value> <memory_limit>")
        sys.exit(1)
    relocate_PDS_files(k_value)
    uncomputed_files = get_uncomputed_interpolant_files(k_value)
    # all_interpolant_files = get_all_interpolant_files(k_value)
    # subsumed_interpolant_files = get_subsumed_PDS_interpolant_files(k_value)
    force_file = ["6s43.40.2.interpolant"]
    # print(len(all_interpolant_files))
    # print(f"len(subsumed_interpolant_files): {len(subsumed_interpolant_files)}")
    # compute_PDS(k_value,all_interpolant_files,memory_limit)
    # compute_PDS(k_value,subsumed_interpolant_files,memory_limit)
    compute_PDS(k_value,uncomputed_files,memory_limit)

if __name__ == "__main__":
    main()
