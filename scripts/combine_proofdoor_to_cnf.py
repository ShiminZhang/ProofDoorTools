# [Not(v288),
#  v3903,
#  Not(v3393),
#  Not(v291),
#  v803,
#  Not(v293),
#  Not(v292),
#  v604,
#  v1375,
#  v1288,
#  v741,
#  v3373,
#  Not(v3380),
#  v637,
#  v3900,
#  Not(v3590),
#  v804,
#  v3339,
#  Not(v3354),
#  v719]

import os
import sys
# from utils.categories import get_category
from tqdm import tqdm
from utils.utils import convert_to_dimacs, parse_interpolant_cnf_to_dimacs,parse_cnf_list
from utils.paths import get_interpolant_cnf_dir
import re

def write_dimacs_file(input_file, output_file=None):
    """Process a CNF file and write to DIMACS format."""
    if output_file is None:
        output_file = input_file + ".dimacs"
    
    # clauses = parse_cnf_list(input_file)
    # header, var_mapping, dimacs_clauses = convert_to_dimacs(clauses)
    header, dimacs_clauses = parse_interpolant_cnf_to_dimacs(input_file)
    
    with open(output_file, 'w') as f:
        f.write(header + "\n")
        for clause in dimacs_clauses:
            f.write(clause + "\n")
    
    print(f"Converted {input_file} to DIMACS format in {output_file}")
    return output_file

def group_cnf_files_by_index(directory, k_value,index, force_name=None, ):
    """Group CNF files by index for a given k value."""
    file_groups = {}
    count = 0
    for filename in tqdm(os.listdir(directory)):
        if filename.endswith('.cnf'):
            if force_name is not None and force_name not in filename:
                continue
            parts = filename.split('.')
            if len(parts) >= 4 and parts[1].isdigit() and int(parts[1]) == k_value:
                basename = parts[0]
                if int(parts[2]) != index:
                    continue
                if basename not in file_groups:
                    file_groups[basename] = []
                file_groups[basename].append(os.path.join(directory, filename))
    return file_groups
            
def group_cnf_files_by_basename(directory, k_value, force_name=None, limit=-1):
    """Group CNF files by basename for a given k value."""
    file_groups = {}
    count = 0
    for filename in tqdm(os.listdir(directory)):
        if filename.endswith('.cnf'):
            if force_name is not None and force_name not in filename:
                continue
            parts = filename.split('.')
            if len(parts) >= 4 and parts[1].isdigit() and int(parts[1]) == k_value:
                basename = parts[0]
                if limit > 0 and int(parts[2]) >= limit:
                    continue
                if basename not in file_groups:
                    file_groups[basename] = []
                file_groups[basename].append(os.path.join(directory, filename))
    return file_groups

def combine_clauses_from_files(files, original_var_count, n_value):
    """Combine all clauses from a list of CNF files, sharing the same auxiliary map."""
    all_clauses = []
    auxilliary_map = {}
    if n_value != "all":
        files = files[:n_value]
    # print(f"files: {files}")
    for file_path in files:
        clauses = parse_cnf_list(file_path, auxilliary_map, original_var_count)
        all_clauses.extend(clauses)
    return all_clauses, auxilliary_map

def write_combined_dimacs_file(output_file, all_clauses, var_mapping):
    """Write the combined DIMACS file with header, var mapping, and clauses."""
    header, _, dimacs_clauses = convert_to_dimacs(all_clauses)
    with open(output_file, 'w') as f:
        f.write(header + "\n")
        for mapping in var_mapping:
            f.write(mapping + "\n")
        for clause in dimacs_clauses:
            f.write(clause + "\n")

def parse_dimacs_file(file):
    """Parse a DIMACS file, returning header info and clauses."""
    clauses = []
    var_count = 0
    clause_count = 0
    with open(file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('c'):
                continue
            elif line.startswith('p'):
                parts = line.split()
                var_count = int(parts[2])
                clause_count = int(parts[3])
            elif line:
                clauses.append(line)
    return var_count, clause_count, clauses

def parse_cnf_file(file):
    """Parse a CNF file, returning header info and clauses."""
    clauses = []
    var_count = 0
    clause_count = 0
    with open(file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('c'):
                continue
            elif line.startswith('p'):
                parts = line.split()
                var_count = int(parts[2])
                clause_count = int(parts[3])
            elif line:
                clauses.append(line)
    return var_count, clause_count, clauses

def combine_with_original_cnf(dimacs_file, original_cnf, output_file):
    """Combine a DIMACS file with the original CNF file into a new file."""
    dimacs_var_count, dimacs_clause_count, dimacs_clauses = parse_dimacs_file(dimacs_file)
    original_var_count, original_clause_count, original_clauses = parse_cnf_file(original_cnf)
    total_var_count = max(dimacs_var_count, original_var_count)
    total_clause_count = len(dimacs_clauses) + len(original_clauses)
    new_header = f"p cnf {total_var_count} {total_clause_count}"
    with open(output_file, 'w') as combined_f:
        combined_f.write(new_header + "\n")
        for clause in dimacs_clauses:
            combined_f.write(clause + "\n")
        for clause in original_clauses:
            combined_f.write(clause + "\n")
    print(f"Combined {dimacs_file} and {original_cnf} into {output_file}")

def combine_single_i_interpolant_to_cnf(directory, k_value, index, force_name=None):             
        file_groups = group_cnf_files_by_index(directory, k_value, index, force_name)
        dimacs_files = []
        for basename, files in tqdm(file_groups.items()):
            output_dir = f"ProofDoorBenchmark/combined_cnfs/"
            original_cnf_path = f"ProofDoorBenchmark/cnfs/{k_value}/"
            original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
            print(f"original_cnf: {original_cnf}")
            original_var_count = 0
            if os.path.exists(original_cnf):
                with open(original_cnf, 'r') as f:
                    lines = f.readlines()
                for line in lines:
                    if "p cnf" in line:
                        parts = line.split()
                        original_var_count = int(parts[2])
                        break
            else:
                print(f"Original CNF file {original_cnf} not found, skipping combination")
                exit(0)
                continue
            os.makedirs(output_dir, exist_ok=True)
            output_file = f"{output_dir}/{basename}.{k_value}.index_{index}.dimacs"
            valid_group = True
            if not valid_group:
                continue
            auxilliary_map = {}
            assert(len(files) == 1)
            all_clauses = parse_cnf_list(files[0], auxilliary_map, original_var_count)
            header, var_mapping, dimacs_clauses = convert_to_dimacs(all_clauses)
            with open(output_file, 'w') as f:
                f.write(header + "\n")
                for mapping in var_mapping:
                    f.write(mapping + "\n")
                for clause in dimacs_clauses:
                    f.write(clause + "\n")
            dimacs_files.append(output_file)
            print(f"Combined {len(files)} files: ({files})  for {basename} into {output_file}")                 
                
def combine_first_n_interpolant_to_cnf(directory, k_value, n_value=-1, force_name=None):           
        if n_value == -1:
            n_value = "all"
        if n_value == 0:
            file_groups = group_cnf_files_by_basename(directory, k_value, force_name, 1)
            print(f"file_groups: {file_groups}")
            for basename, files in tqdm(file_groups.items()):
                basename = os.path.basename(files[0])
                basename = basename.split('.')[0]
                original_cnf_path = f"ProofDoorBenchmark/cnfs/{k_value}/"
                original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
                output_dir = f"ProofDoorBenchmark/combined_cnfs/"
                print(f"copying {original_cnf} to {basename}.{k_value}.combined.0.cnf")
                combined_output = f"{output_dir}/{basename}.{k_value}.combined.0.cnf"
                os.system(f"cp {original_cnf} {combined_output}")
            return
                
                
        file_groups = group_cnf_files_by_basename(directory, k_value, force_name, n_value)
        dimacs_files = []
        for basename, files in tqdm(file_groups.items()):
            output_dir = f"ProofDoorBenchmark/combined_cnfs/"
            original_cnf_path = f"ProofDoorBenchmark/cnfs/{k_value}/"
            original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
            print(f"original_cnf: {original_cnf}")
            original_var_count = 0
            if os.path.exists(original_cnf):
                with open(original_cnf, 'r') as f:
                    lines = f.readlines()
                for line in lines:
                    if "p cnf" in line:
                        parts = line.split()
                        original_var_count = int(parts[2])
                        break
            else:
                print(f"Original CNF file {original_cnf} not found, skipping combination")
                exit(0)
                continue
            os.makedirs(output_dir, exist_ok=True)
            output_file = f"{output_dir}/{basename}.{k_value}.{n_value}.dimacs"
            files.sort(key=lambda f: int(f.split('.')[-3]))
            valid_group = True
            if not valid_group:
                continue
            all_clauses, auxilliary_map = combine_clauses_from_files(files, original_var_count, n_value)
            header, var_mapping, dimacs_clauses = convert_to_dimacs(all_clauses)
            with open(output_file, 'w') as f:
                f.write(header + "\n")
                for mapping in var_mapping:
                    f.write(mapping + "\n")
                for clause in dimacs_clauses:
                    f.write(clause + "\n")
            dimacs_files.append(output_file)
            print(f"Combined {len(files)} files: ({files})  for {basename} into {output_file}")
            
        for file in dimacs_files:
            basename = os.path.basename(file)
            basename = basename.split('.')[0]
            original_cnf_path = f"ProofDoorBenchmark/cnfs/{k_value}/"
            original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
            if os.path.exists(original_cnf):
                combined_output = f"{output_dir}/{basename}.{k_value}.combined.{n_value}.cnf"
                combine_with_original_cnf(file, original_cnf, combined_output)
            else:
                print(f"Original CNF file {original_cnf} not found, skipping combination")                      
                              
def main():
    # only_category = "exponential"
    force_name = None
    if len(sys.argv) >= 2:
        k_value = int(sys.argv[1])
        # directory = sys.argv[1]
        directory = get_interpolant_cnf_dir()
        limit = int(sys.argv[2] if len(sys.argv) > 2 else -1)
        # for n in range(limit):
        #     combine_first_n_interpolant_to_cnf(directory, k_value, n+1, force_name)
        combine_first_n_interpolant_to_cnf(directory, k_value, 0, force_name)
        sys.exit(0)
    # input_file = sys.argv[1]
    # output_file = sys.argv[2] if len(sys.argv) > 2 else None
    # write_dimacs_file(input_file, output_file)

if __name__ == "__main__":
    main()
