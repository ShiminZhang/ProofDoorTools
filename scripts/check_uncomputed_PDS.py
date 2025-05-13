import os
import sys
import shutil
from utils.paths import get_interpolant_dir, get_PDS_data_dir, get_PDS_dir, get_smts_dir
from count_interpolant_byz3 import count_by_z3, count_and_save

def relocate_PDS_files(k_value):
    # read all json files in PDS_dir
    PDS_data_dir = get_PDS_data_dir()
    PDS_dir = get_PDS_dir(k_value)
    json_files = os.listdir(PDS_data_dir)
    for file in json_files:
        if file.endswith(".json"):
            file_k = file.split(".")[1]
            if file_k == k_value:
                shutil.move(os.path.join(PDS_data_dir, file), os.path.join(PDS_dir, file))

def check_uncomputed_PDS(k_value):
    PDS_dir = get_PDS_dir(k_value)
    json_files = os.listdir(PDS_dir)
    interpolant_dir = get_interpolant_dir(k_value)
    interpolant_files = os.listdir(interpolant_dir)
    smts_dir = get_smts_dir(k_value)
    for file in interpolant_files:
        if file.endswith(".interpolant"):
            # Skip empty interpolant files
            if os.path.getsize(os.path.join(interpolant_dir, file)) == 0:
                continue
            json_file = file.replace(".interpolant", ".json")
            if json_file not in json_files:
                count,msg = count_and_save(
                    os.path.join(interpolant_dir, file),
                    os.path.join(smts_dir, file.replace(".interpolant", ".smt2")))

def main():
    k_value = sys.argv[1]
    if len(sys.argv) < 2:
        print("Usage: python check_uncomputed_PDS.py <k_value>")
        sys.exit(1)
    relocate_PDS_files(k_value)
    check_uncomputed_PDS(k_value)
    
    
    

if __name__ == "__main__":
    main()
