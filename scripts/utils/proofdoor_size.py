import os
import shutil
from utils.paths import get_PDS_data_dir, get_PDS_dir, get_interpolant_dir, get_smts_dir,get_interpolant_cnf_dir
from tqdm import tqdm
import json

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

def get_all_interpolant_files(k_value):
    interpolant_dir = get_interpolant_dir(k_value)
    interpolant_files = sorted(os.listdir(interpolant_dir))
    return interpolant_files

def get_subsumed_PDS_interpolant_files(k_value):
    interpolant_cnf_dir = get_interpolant_cnf_dir()
    interpolant_cnfs = os.listdir(interpolant_cnf_dir)
    interpolant_files = []
    for file in interpolant_cnfs:
        if file.endswith(".smt2.cnf"):
            with open(os.path.join(interpolant_cnf_dir, file), "r") as f:
                interpolant = f.read()
            if "..)" in interpolant:
                name = file.replace("smt2.cnf", "interpolant")
                interpolant_files.append(name)
    return interpolant_files

def get_uncomputed_interpolant_files(k_value):
    PDS_dir = get_PDS_dir(k_value)
    json_files = os.listdir(PDS_dir)
    interpolant_files = get_all_interpolant_files(k_value)
    uncomputed_files=[]
    
    for file in tqdm(interpolant_files):
        if file.endswith(".interpolant"):
            json_file = f"{file}.json"
            json_file_path = os.path.join(PDS_dir, json_file)
            if os.path.exists(json_file_path):
                continue
            if json_file in json_files and os.path.getsize(json_file_path) > 0:
                with open(json_file_path, "r") as f:
                    data = json.load(f)
                    if data[file][0] < 0:
                        print(f"not skipping {file} because of error")
                    else:
                        print(f"Skipping {file} because it is already computed")
                        continue
            uncomputed_files.append(file)
    return uncomputed_files
       