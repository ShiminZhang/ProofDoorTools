import os
import sys
import shutil
from tqdm import tqdm
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
def parse_memory_limit(memory_limit_str):
    """
    Parse memory limit string to bytes.
    Examples: '10g' -> 10 * 1024 * 1024 * 1024, '500m' -> 500 * 1024 * 1024
    Default is 10g if the input is not a valid memory limit.
    """
    if memory_limit_str == '-1':
        return -1
    
    try:
        if memory_limit_str.endswith('g'):
            return int(memory_limit_str[:-1]) * 1024 * 1024 * 1024
        elif memory_limit_str.endswith('m'):
            return int(memory_limit_str[:-1]) * 1024 * 1024
        elif memory_limit_str.endswith('k'):
            return int(memory_limit_str[:-1]) * 1024
        else:
            # Try to parse as bytes
            return int(memory_limit_str)
    except (ValueError, AttributeError):
        # Default to 10GB if parsing fails
        return 10 * 1024 * 1024 * 1024

def check_uncomputed_PDS(k_value,memory_limit=-1):
    PDS_dir = get_PDS_dir(k_value)
    json_files = os.listdir(PDS_dir)
    interpolant_dir = get_interpolant_dir(k_value)
    interpolant_files = os.listdir(interpolant_dir)
    smts_dir = get_smts_dir(k_value)
    for file in tqdm(sorted(interpolant_files)):
        if file.endswith(".interpolant"):
            # Skip empty interpolant files
            if os.path.getsize(os.path.join(interpolant_dir, file)) == 0:
                continue
            if memory_limit != -1:
                if os.path.getsize(os.path.join(interpolant_dir, file)) > memory_limit:
                    continue
            json_file = file.replace(".interpolant", ".json")
            if json_file not in json_files:
                count,msg = count_and_save(
                    os.path.join(interpolant_dir, file),
                    os.path.join(smts_dir, file.replace(".interpolant", ".smt2")))

def main():
    k_value = sys.argv[1]
    memory_limit = parse_memory_limit(sys.argv[2])
    if len(sys.argv) < 2:
        print("Usage: python check_uncomputed_PDS.py <k_value>")
        sys.exit(1)
    relocate_PDS_files(k_value)
    check_uncomputed_PDS(k_value,memory_limit)
    
    
    

if __name__ == "__main__":
    main()
