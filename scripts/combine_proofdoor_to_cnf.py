import os
import sys
# from utils.categories import get_category
from tqdm import tqdm
from utils.utils import convert_to_dimacs, parse_interpolant_cnf_to_dimacs,parse_cnf_list
from utils.paths import get_interpolant_cnf_dir,get_interpolant_dimacs_dir,get_CNF_dir
from utils.process_cnf import CNF
from prepare_single import prepare_cnf
from debug.logging import LOG, TOGGLE_SHOWLOG
from utils.catagory import get_instance_list
import argparse
import re
import csv
from utils.utils import GetDataFromLog
import random
from typing import Optional

CADICAL_BINARY = "./solvers/cadical"
SLURM_LOG_DIR = "./SlurmLogs/solve_combine/"

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

def group_cnf_files_by_index(directory, k_value,index, force_name=None, limit=-1):
    """Group CNF files by index for a given k value."""
    print(f"try group files in {directory} together")
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
    print(f"try group files in {directory} together based on basename")
    file_groups = {}
    count = 0
    for filename in tqdm(os.listdir(directory)):
        if filename.endswith('.smtcnf'):
            basename = filename.split('.')[0]
            if (force_name is not None) and force_name != basename:
                # print(f"skipping {filename} because {basename} does not contain {force_name}")
                continue
            parts = filename.split('.')
            if int(parts[1]) == k_value:
                # print("match")
                basename = parts[0]
                if limit != "all" and limit > 0 and int(parts[2]) >= limit:
                    continue
                if basename not in file_groups:
                    file_groups[basename] = []
                file_groups[basename].append(os.path.join(directory, filename))
    invalid_keys = []
    if limit > 0:
        for basename, files in file_groups.items():
            if len(files) != limit:
                print(f"basename: {basename} len(files): {len(files)} limit: {limit}")
                # print(f"files: {files}")
                invalid_keys.append(basename)
            
    for key in invalid_keys:
        print(f"deleting {key} because it has only {len(file_groups[key])} files while {limit} is expected")
        del file_groups[key]
    return file_groups

def list_smtcnf_files_for_instance(instance: str, k_value: int, pddef: int) -> list:
    """Return sorted list of .smtcnf file paths for a given instance and K."""
    directory = get_interpolant_cnf_dir(k_value, pddef)
    files = []
    if not os.path.exists(directory):
        return files
    for filename in os.listdir(directory):
        if not filename.endswith(".smtcnf"):
            continue
        parts = filename.split(".")
        if len(parts) < 4:
            continue
        if parts[0] != instance:
            continue
        try:
            k_in_name = int(parts[1])
        except ValueError:
            continue
        if k_in_name != k_value:
            continue

        with open(os.path.join(directory, filename), 'r') as f:
            # check if false is contained
            if "False" in f.read():
                return None
        files.append(os.path.join(directory, filename))
    # sort by interpolant index
    files.sort(key=lambda p: int(os.path.basename(p).split(".")[2]))
    return files

def combine_clauses_from_all_files(files, original_var_count, auxilliary_map):
    """Combine all clauses from a list of CNF files, sharing the same auxiliary map."""
    all_clauses = []
    for file_path in files:
        clauses = parse_cnf_list(file_path, auxilliary_map, original_var_count)
        all_clauses.extend(clauses)
    return all_clauses, auxilliary_map

def combine_clauses_from_files(files, original_var_count, n_value, previous_parsed_cnf_clauses_for_file, auxilliary_map):
    """Combine all clauses from a list of CNF files, sharing the same auxiliary map."""
    all_clauses = []
    if n_value != "all":
        files = files[:n_value]
    # print(f"files: {files}")
    # assert(len(previous_parsed_cnf_clauses_for_file) == len(files) - 1)
    if not (len(previous_parsed_cnf_clauses_for_file) == len(files) - 1):
        LOG(f"ASSTIONFAIL len(previous_parsed_cnf_clauses_for_file): {len(previous_parsed_cnf_clauses_for_file)}")
        LOG(f"len(files): {len(files)}")
        # exit(0)
        
    for i in range(len(previous_parsed_cnf_clauses_for_file)):
        all_clauses.extend(previous_parsed_cnf_clauses_for_file[i])
        
    # for file_path in files:
    file_path = files[-1]
    # print(f"parse_cnf_list: {file_path}")
    clauses = parse_cnf_list(file_path, auxilliary_map, original_var_count)
    previous_parsed_cnf_clauses_for_file[len(previous_parsed_cnf_clauses_for_file)] = clauses
    all_clauses.extend(clauses)
    return all_clauses, auxilliary_map, previous_parsed_cnf_clauses_for_file

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

def _max_var_in_clause_line(clause_line: str) -> int:
    """
    Given a DIMACS/DRAT clause line like "1 -3 7 0" (or without trailing 0),
    return max absolute variable index.
    """
    max_v = 0
    for tok in clause_line.strip().split():
        if tok == "0":
            continue
        try:
            v = abs(int(tok))
        except Exception:
            continue
        if v > max_v:
            max_v = v
    return max_v

def parse_drat_add_clauses(drat_path: str) -> list:
    """
    Parse a DRAT file and return a list of *added* clauses as DIMACS lines.
    - Skips deletion lines starting with 'd'
    - Skips comment lines starting with 'c'
    """
    add_clauses = []
    with open(drat_path, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("c"):
                continue
            if line.startswith("d"):
                continue
            # Keep the clause line as-is (typically ends with 0)
            add_clauses.append(line)
    return add_clauses

def resolve_original_drat_path(original_cnf_path: str, instance: str, K: int) -> Optional[str]:
    """
    Try common conventions for original CaDiCaL drat path.
    """
    candidates = [
        f"{original_cnf_path}.cadicalplain.drat",              # most common in this repo
        f"{get_CNF_dir(K)}/{instance}.{K}.cadicalplain.drat",  # legacy convention
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None

def write_random_drat_add_combined_cnf(
    *,
    original_cnf_path: str,
    proofdoor_combined_cnf_path: str,
    original_drat_path: str,
    output_cnf_path: str,
    seed: int,
) -> dict:
    """
    Build a baseline combined CNF by sampling add-clauses from the original DRAT proof.
    Sampling size equals the number of proofdoor-added clauses:
        |clauses(proofdoor_combined)| - |clauses(original)|
    """
    orig_var_count, _, orig_clauses = parse_cnf_file(original_cnf_path)
    _, _, proofdoor_clauses = parse_cnf_file(proofdoor_combined_cnf_path)
    n_added = max(0, len(proofdoor_clauses) - len(orig_clauses))

    drat_adds = parse_drat_add_clauses(original_drat_path)
    rng = random.Random(seed)
    if n_added >= len(drat_adds):
        sampled = drat_adds[:]  # take all we have
    else:
        sampled = rng.sample(drat_adds, n_added)

    max_var = orig_var_count
    for cl in sampled:
        max_var = max(max_var, _max_var_in_clause_line(cl))

    os.makedirs(os.path.dirname(output_cnf_path), exist_ok=True)
    with open(output_cnf_path, "w") as f:
        f.write(f"p cnf {max_var} {len(orig_clauses) + len(sampled)}\n")
        for clause in orig_clauses:
            f.write(clause + "\n")
        for clause in sampled:
            # Ensure DIMACS termination (defensive)
            if clause.endswith(" 0") or clause.endswith("\t0") or clause.endswith(" 0 "):
                f.write(clause.strip() + "\n")
            else:
                f.write(clause.strip() + " 0\n")

    return {
        "n_added_target": n_added,
        "n_drat_adds_total": len(drat_adds),
        "n_sampled": len(sampled),
        "seed": seed,
        "output": output_cnf_path,
    }

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
        if force_name is not None and len(file_groups) == 0:
            print(f"No files found for {force_name} with index {index}")
            exit(0)

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

def combine_first_n_interpolant_to_cnf_single(
    basename,files,
    k_value,
    n_value,
    previous_parsed_cnf_clauses,
    auxilliary_map,
    pddef=0
    ):
    """
    For a given instance `basename` and K-level `k_value`, take the original CNF
    and append clauses from the first `n_value` interpolant files (in index order).

    Steps:
      1. Use `CNF` to convert selected `.smtcnf` interpolants into `.cnf`.
      2. Read the original CNF clauses.
      3. Read the interpolant CNF clauses in order and append them.
      4. Write a new combined CNF with an updated header.

    This matches the intended semantics: "use CNF class to turn smtcnf into cnf,
    then directly concatenate the clauses in sequence into the original cnf".
    """
    # Directory for combined CNFs (pddef-aware).
    combined_cnf_dir = get_interpolant_dimacs_dir(k_value,pddef)
    output_dir = combined_cnf_dir

    # Path to original CNF.
    original_cnf_path = get_CNF_dir(k_value)
    original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
    
    if n_value == -1:
        # Special value meaning "use all interpolants".
        n_value_label = "all"
    else:
        n_value_label = n_value

    if n_value == 0:
        print(f"copyingoriginal_cnf: {original_cnf}")
        os.system(f"cp {original_cnf} {output_dir}/{basename}.{k_value}.combined.0.cnf")
        return previous_parsed_cnf_clauses, auxilliary_map
    
    # Helper: extract the interpolant index from a filename like
    # "6s339rb22.45.30.smtcnf" or "6s339rb22.45.30.cnf".
    def _extract_interp_index(path):
        name = os.path.basename(path)
        parts = name.split(".")
        # Expected: <basename>.<K>.<idx>.<ext>
        if len(parts) >= 3 and parts[2].isdigit():
            return int(parts[2])
        # Fallback: scan from the end for a numeric part before the extension.
        for p in reversed(parts[:-1]):
            if p.isdigit():
                return int(p)
        return 0

    # Sort interpolant files by their index, then select the first n.
    sorted_smt_files = sorted(files, key=_extract_interp_index)
    total_interpolants = len(sorted_smt_files)
    if n_value == -1:
        n_to_use = total_interpolants
    else:
        n_to_use = min(n_value, total_interpolants)

    selected_smt_files = sorted_smt_files[:n_to_use]

    # Convert selected .smtcnf interpolants to .cnf via CNF class.
    cnf_files = []
    for smt_cnf_file in selected_smt_files:
        cnf_obj = CNF(smt_cnf_file)
        cnf_files.append(cnf_obj.cnf_path)

    # Ensure bookkeeping map has an entry for this basename (even though
    # we no longer rely on incremental caching inside this function).
    if basename not in previous_parsed_cnf_clauses.keys():
        previous_parsed_cnf_clauses[basename] = {}

    print(f"original_cnf: {original_cnf}")
    if not os.path.exists(original_cnf):
        print(f"Original CNF file {original_cnf} not found, skipping combination")
        exit(0)

    # Read original CNF clauses.
    original_var_count, original_clause_count, original_clauses = parse_cnf_file(original_cnf)
    max_var = original_var_count
    combined_clauses = list(original_clauses)

    # Append interpolant CNF clauses in order.
    for cnf_path in cnf_files:
        interp_var_count, interp_clause_count, interp_clauses = parse_cnf_file(cnf_path)
        max_var = max(max_var, interp_var_count)
        combined_clauses.extend(interp_clauses)

    os.makedirs(output_dir, exist_ok=True)

    # Decide suffix for the combined file name.
    suffix = n_value_label
    combined_output = f"{output_dir}/{basename}.{k_value}.combined.{suffix}.cnf"

    # Write the combined CNF with updated header.
    new_header = f"p cnf {max_var} {len(combined_clauses)}"
    with open(combined_output, 'w') as f:
        f.write(new_header + "\n")
        for clause in combined_clauses:
            f.write(clause + "\n")

    print(
        f"Combined original CNF {original_cnf} with {len(cnf_files)} interpolant CNFs "
        f"into {combined_output}"
    )

    return previous_parsed_cnf_clauses, auxilliary_map
    
           
def combine_first_n_interpolant_to_cnf(
    directory, k_value, n_value=-1, force_name=None,
    previous_parsed_cnf_clauses=None, auxilliary_map=None):      
        if previous_parsed_cnf_clauses is None:
            previous_parsed_cnf_clauses = {}
        if auxilliary_map is None:
            auxilliary_map = {}
        if n_value == -1:
            n_value = "all"
        if n_value == 0:
            file_groups = group_cnf_files_by_basename(directory, k_value, force_name, k_value)
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
                
        file_groups = group_cnf_files_by_basename(directory, k_value, force_name, k_value)
        dimacs_files = []
        for basename, files in tqdm(file_groups.items()):
            if basename not in previous_parsed_cnf_clauses.keys():
                previous_parsed_cnf_clauses[basename] = {}
            output_dir = f"ProofDoorBenchmark/combined_cnfs/{k_value}/"
            os.makedirs(output_dir, exist_ok=True)
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
            all_clauses, auxilliary_map = combine_clauses_from_all_files(files, original_var_count, auxilliary_map)
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
        return previous_parsed_cnf_clauses, auxilliary_map

def contain_false(name, K):
    smtcnf_path = f"ProofDoorBenchmark/interpolant_cnfs/{K}/{name}.{K}.smtcnf"

def main():
    TOGGLE_SHOWLOG(True)
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv_path", type=str, default="category.csv", help="CSV with columns: instance_name,K,smt2cnf_status")
    parser.add_argument("--pddef", type=int, default=1)
    parser.add_argument("--copy_original_only", action="store_true", default=False, help="Only copy original CNF as combined.0.cnf")
    parser.add_argument("--run", action="store_true", default=False, help="Submit slurm jobs to solve original and combined CNFs")
    parser.add_argument("--compare", action="store_true", default=False, help="Compare solving time between original and combined CNFs and print improvement ratio")
    parser.add_argument("--random_drat_add", action="store_true", default=False, help="Also create a baseline combined CNF by sampling add-clauses from original .drat (same count as proofdoor-added clauses)")
    parser.add_argument("--random_drat_seed", type=int, default=0, help="Random seed for --random_drat_add sampling")
    parser.add_argument("--random_drat_tag", type=str, default="dratrand", help="Tag used in output filename for --random_drat_add")
    args = parser.parse_args()

    # Read CSV and collect instances where smt2cnf_status == 'done'
    targets = []
    with open(args.csv_path, "r") as f:
        reader = csv.DictReader(f)
        required = {"instance_name", "K", "smt2cnf_status"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for row in reader:
            if (row.get("smt2cnf_status") or "").strip().lower() != "done":
                continue
            instance = row["instance_name"].strip()
            try:
                K = int(row["K"])
            except Exception:
                continue
            targets.append((instance, K))

    print(f"Found {len(targets)} (instance,K) with SMT→CNF done from {args.csv_path}")

    # Optionally run solvers via slurm
    if args.run:
        os.makedirs(SLURM_LOG_DIR, exist_ok=True)
        for instance, K in tqdm(targets):
            cnf_dir = get_CNF_dir(K)
            original_cnf = f"{cnf_dir}{instance}.{K}.cnf"
            assert(os.path.exists(original_cnf))
            # original run via prepare_single script (produces standard cadicalplain logs)
            activate_python = "source .env; source $PYENVPATH"
            # combined run: solve combined-K CNF
            combined_dir = get_interpolant_dimacs_dir(K, args.pddef)
            combined_full = f"{combined_dir}/{instance}.{K}.combined.{K}.cnf"
            if not os.path.exists(combined_full):
                print(f"[SKIP] Combined CNF not found: {combined_full}")
                continue
            comb_log = f"{combined_full}.cadicalplain.log"
            comb_drat = f"{combined_full}.cadicalplain.drat"
            cadical_cmd = f"{activate_python} && {CADICAL_BINARY} --plain --no-binary {combined_full} {comb_drat} > {comb_log} 2>&1"
            slurm_out_comb = f"{SLURM_LOG_DIR}/comb_{instance}.{K}.%j.log"
            os.system(f"sbatch --job-name=solve_comb_{instance}.{K} --time=00:00:5000 --mem=16g --output={slurm_out_comb} --wrap=\"{cadical_cmd}\"")

            if args.random_drat_add:
                rand_cnf = f"{combined_dir}/{instance}.{K}.combined.{args.random_drat_tag}.seed{args.random_drat_seed}.cnf"
                if not os.path.exists(rand_cnf):
                    drat_path = resolve_original_drat_path(original_cnf, instance, K)
                    if drat_path is None:
                        print(f"[SKIP] Original DRAT proof not found for {instance}.{K} (needed for --random_drat_add)")
                    else:
                        info = write_random_drat_add_combined_cnf(
                            original_cnf_path=original_cnf,
                            proofdoor_combined_cnf_path=combined_full,
                            original_drat_path=drat_path,
                            output_cnf_path=rand_cnf,
                            seed=args.random_drat_seed,
                        )
                        print(f"[OK] Wrote random-DRAT combined CNF: {info}")
                if os.path.exists(rand_cnf):
                    rand_log = f"{rand_cnf}.cadicalplain.log"
                    rand_drat = f"{rand_cnf}.cadicalplain.drat"
                    rand_cmd = f"{activate_python} && {CADICAL_BINARY} --plain --no-binary {rand_cnf} {rand_drat} > {rand_log} 2>&1"
                    slurm_out_rand = f"{SLURM_LOG_DIR}/rand_{instance}.{K}.%j.log"
                    os.system(f"sbatch --job-name=solve_rand_{instance}.{K} --time=00:00:5000 --mem=16g --output={slurm_out_rand} --wrap=\"{rand_cmd}\"")
        return
    previous_parsed_cnf_clauses = {}
    auxilliary_map = {}

    for instance, K in tqdm(targets):
        # Ensure original CNF exists
        original_cnf_path = get_CNF_dir(K)
        original_cnf = f"{original_cnf_path}{instance}.{K}.cnf"
        if not os.path.exists(original_cnf) or os.path.getsize(original_cnf) == 0:
            print(f"[REGENERATE] Original CNF missing: {original_cnf}")
            prepare_cnf(instance, K, force_refresh=True)

        # Copy original to combined.0.cnf
        combined_dir = get_interpolant_dimacs_dir(K, args.pddef)
        os.makedirs(combined_dir, exist_ok=True)
        combined_zero = f"{combined_dir}/{instance}.{K}.combined.0.cnf"
        os.system(f"cp {original_cnf} {combined_zero}")
        print(f"[OK] Wrote original-only combined CNF: {combined_zero}")
        if args.copy_original_only:
            continue

        # Collect all .smtcnf files for this instance and K
        smtcnf_files = list_smtcnf_files_for_instance(instance, K, args.pddef)
        if not smtcnf_files:
            print(f"[SKIP] No SMT CNF files for {instance}.{K}")
            continue

        # Combine all interpolants into a full combined CNF
        previous_parsed_cnf_clauses, auxilliary_map = combine_first_n_interpolant_to_cnf_single(
            instance, smtcnf_files, K, K, previous_parsed_cnf_clauses, auxilliary_map, pddef=args.pddef
        )

        if args.random_drat_add:
            combined_full = f"{combined_dir}/{instance}.{K}.combined.{K}.cnf"
            if not os.path.exists(combined_full):
                print(f"[SKIP] Proofdoor combined CNF not found (needed for clause count): {combined_full}")
                continue
            drat_path = resolve_original_drat_path(original_cnf, instance, K)
            if drat_path is None:
                print(f"[SKIP] Original DRAT proof not found for {instance}.{K} (needed for --random_drat_add)")
                continue
            rand_out = f"{combined_dir}/{instance}.{K}.combined.{args.random_drat_tag}.seed{args.random_drat_seed}.cnf"
            info = write_random_drat_add_combined_cnf(
                original_cnf_path=original_cnf,
                proofdoor_combined_cnf_path=combined_full,
                original_drat_path=drat_path,
                output_cnf_path=rand_out,
                seed=args.random_drat_seed,
            )
            print(f"[OK] Wrote random-DRAT combined CNF: {info}")
    # Optionally compare solving times
    if args.compare:
        total = 0
        improved = 0
        sum_orig = 0.0
        sum_comb = 0.0
        sum_rand = 0.0
        improved_rand = 0
        total_rand = 0
        missing = 0
        details = []
        for instance, K in tqdm(targets):
            orig_log = f"{get_CNF_dir(K)}/{instance}.{K}.cnf.cadicalplain.log"
            comb_log = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{K}.cnf.cadicalplain.log"
            rand_log = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{args.random_drat_tag}.seed{args.random_drat_seed}.cnf.cadicalplain.log"

            if not (os.path.exists(orig_log) and os.path.exists(comb_log)):
                missing += 1
                continue
            t_orig = GetDataFromLog(orig_log)
            t_comb = GetDataFromLog(comb_log)
            t_rand = GetDataFromLog(rand_log) if (args.random_drat_add and os.path.exists(rand_log)) else None
            if t_orig is None or t_comb is None:
                missing += 1
                continue
            total += 1
            sum_orig += t_orig
            sum_comb += t_comb
            if t_comb < t_orig:
                improved += 1
            red_pd = (t_orig - t_comb) / t_orig if t_orig and t_orig > 0 else 0.0

            red_rand = None
            if t_rand is not None:
                sum_rand += t_rand
                total_rand += 1
                if t_rand < t_orig:
                    improved_rand += 1
                red_rand = (t_orig - t_rand) / t_orig if t_orig and t_orig > 0 else 0.0

            details.append((instance, K, t_orig, t_comb, t_rand, red_pd, red_rand))

        print(f"[COMPARE] Valid pairs: {total}, missing/invalid: {missing}")
        if total > 0:
            avg_orig = sum_orig / total
            avg_comb = sum_comb / total
            overall_reduction = (avg_orig - avg_comb) / avg_orig if avg_orig > 0 else 0.0
            print(f"[COMPARE] Improved count: {improved}/{total} ({improved/total:.1%})")
            print(f"[COMPARE] Avg original time: {avg_orig:.3f}s, Avg combined time: {avg_comb:.3f}s, Reduction: {overall_reduction:.1%}")

            if args.random_drat_add:
                avg_rand = (sum_rand / total_rand) if total_rand > 0 else 0.0
                overall_red_rand = (avg_orig - avg_rand) / avg_orig if avg_orig > 0 else 0.0
                if total_rand > 0:
                    print(f"[COMPARE] Random-DRAT improved count: {improved_rand}/{total_rand} ({improved_rand/total_rand:.1%})")
                    print(f"[COMPARE] Avg random-DRAT time: {avg_rand:.3f}s, Reduction vs orig: {overall_red_rand:.1%} (tag={args.random_drat_tag}, seed={args.random_drat_seed})")
                else:
                    print(f"[COMPARE] Random-DRAT logs missing for all instances (tag={args.random_drat_tag}, seed={args.random_drat_seed})")

            # Sort by proofdoor reduction
            details.sort(key=lambda x: x[5], reverse=True)
            for instance, K, t_orig, t_comb, t_rand, red_pd, red_rand in details[:5]:
                comb_path = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{K}.cnf.cadicalplain.log"
                if args.random_drat_add:
                    rand_path = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{args.random_drat_tag}.seed{args.random_drat_seed}.cnf.cadicalplain.log"
                    rand_str = f", rand={t_rand:.3f}s, red_rand={red_rand:.1%}" if t_rand is not None and red_rand is not None else ", rand=N/A"
                    print(f"[TOP] {instance}.{K}: orig={t_orig:.3f}s, pd={t_comb:.3f}s, red_pd={red_pd:.1%}{rand_str}, pd_log: {comb_path}, rand_log: {rand_path}")
                else:
                    print(f"[TOP] {instance}.{K}: orig={t_orig:.3f}s, pd={t_comb:.3f}s, red_pd={red_pd:.1%}, pd_log: {comb_path}")

            for instance, K, t_orig, t_comb, t_rand, red_pd, red_rand in details[5:]:
                comb_path = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{K}.cnf.cadicalplain.log"
                if args.random_drat_add:
                    rand_path = f"{get_interpolant_dimacs_dir(K, args.pddef)}/{instance}.{K}.combined.{args.random_drat_tag}.seed{args.random_drat_seed}.cnf.cadicalplain.log"
                    rand_str = f", rand={t_rand:.3f}s, red_rand={red_rand:.1%}" if t_rand is not None and red_rand is not None else ", rand=N/A"
                    print(f"[REST] {instance}.{K}: orig={t_orig:.3f}s, pd={t_comb:.3f}s, red_pd={red_pd:.1%}{rand_str}, pd_log: {comb_path}, rand_log: {rand_path}")
                else:
                    print(f"[REST] {instance}.{K}: orig={t_orig:.3f}s, pd={t_comb:.3f}s, red_pd={red_pd:.1%}, pd_log: {comb_path}")
            
    sys.exit(0)
    # input_file = sys.argv[1]
    # output_file = sys.argv[2] if len(sys.argv) > 2 else None
    # write_dimacs_file(input_file, output_file)

if __name__ == "__main__":
    main()
