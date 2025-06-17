import os
import re
import glob
import json
from tqdm import tqdm
from collections import defaultdict
from scipy.stats import pearsonr
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np
from z3 import *
import re

        
def group_files_by_basename(directory, k_value, force_name=None, limit=-1, file_extension='.cnf'):
    """Group CNF files by basename for a given k value."""
    file_groups = {}
    count = 0
    for filename in tqdm(os.listdir(directory)):
        if filename.endswith(file_extension):
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
            file_groups[basename].sort(key=lambda x: int(x.split('.')[-2]))
                
    #check if the file group for each basename is valid
    invalid_keys = []
    if limit > 0:
        for basename, files in file_groups.items():
            if len(files) != limit:
                # print(f"basename: {basename}")
                # print(f"files: {files}")
                invalid_keys.append(basename)
            
    for key in invalid_keys:
        print(f"deleting {key} because it has only {len(file_groups[key])} files while {limit} is expected")
        del file_groups[key]
    # sort by the index of the name
    # file_groups = dict(sorted(file_groups.items(), key=lambda item: int(item[0].split('.')[-2])))
    return file_groups

def RewriteMap(InMap):
    OutMap = {}
    for key, value in InMap.items():
        key_parts = key.split('.')
        new_key = key_parts[0]
        OutMap[new_key] = value
    return OutMap

def convert_to_dimacs(clauses):
    """Convert parsed clauses to DIMACS CNF format."""
    # Create a mapping of variable names to integers
    var_map = {}
    var_counter = 1
    
    dimacs_clauses = []
    # print(f"clauses: {clauses}")
    for clause in clauses:
        # print(f"clause: {clause}")
        dimacs_clause = []
            
        if clause not in var_map:
            var_map[clause] = var_counter
            var_counter += 1
            
        for literal in clause.strip().split(" "):
            is_negated = literal.startswith('Not(')
            is_negated_by_sign = literal.startswith('-')
            literal = literal.replace("-", "")
            if "aux_" in literal:
                if is_negated:
                    var_name = literal[4:-1]
                else:
                    var_name = literal
                var_name = var_name.split("_")[1]
            else:
                if is_negated:
                    var_name = literal[5:-1]
                else:
                    var_name = literal[1:]
            
            if is_negated or is_negated_by_sign:
                dimacs_clause.append(f"-{var_name} ")
            else:
                dimacs_clause.append(f"{var_name} ")
        if len(dimacs_clause) > 0:
            dimacs_clauses.append("".join(dimacs_clause) + " 0")
    # after this, we need to replace auxillary variables with new available literals
    for i in range(len(dimacs_clauses)):
        clause = dimacs_clauses[i]
        for literal in clause.strip().split(" "):
            if "aux_" in literal:
                var_name = literal.split("aux_")[1]
                dimacs_clauses[i] = dimacs_clauses[i].replace(literal, f"{var_name}")
        dimacs_clauses[i] = dimacs_clauses[i].replace("v", "")
    max_literal = 0
    for clause in dimacs_clauses:
        for literal in clause.strip().split(" "):
            if literal and literal != "0":
                # print(literal)
                abs_value = abs(int(literal))
                max_literal = max(max_literal, abs_value)
    # Create the DIMACS header
    header = f"p cnf {max_literal} {len(dimacs_clauses)}"
    
    # Create a variable mapping comment section
    var_mapping = [f"c {var_id} = {var_name}" for var_name, var_id in var_map.items()]
    return header, var_mapping, dimacs_clauses

def parse_cnf_list(input_file, auxilliary_map=None, original_var_count=0):
    clauses = []
    with open(input_file, 'r') as f:
        lines = f.readlines()
    reading_line=""
    for i in range(len(lines)):
        line = lines[i]
        line = line.replace("(or ", "Or(")
        line = line.replace("(not ", "Not(")
        if ".." in line:
            print(input_file)
            print(line)
            break
        line = line.strip()
        if reading_line:
            reading_line += f" {line}"
            if line.endswith(")"):
                reading_line = reading_line[:-1]
                reading_line = reading_line.replace("Or(", "")
                reading_line = reading_line.replace(",", "")
                reading_line = reading_line.strip()
                clauses.append(reading_line)
                # print(f"reading_line: {reading_line}")
                reading_line = ""
                continue
            continue
        if not line:
            continue
        if line.startswith("Or("):
            if line.endswith(")"):
                line = line[:-1]
                line = line.replace("Or(", "")
                line = line.strip()
                line = line.replace(",", "")
                clauses.append(line)
            elif line.endswith(","):
                reading_line = line
            continue
        
        if line.startswith('Not('):
            # Handle negated variables
            var = line[4:-1].strip()  # Extract variable name from Not(var)
            clauses.append(f"-{var}")
        else:
            # Handle positive variables
            clauses.append(line)
    if auxilliary_map is None:
        print("WARNING: auxilliary variables will not be added to the map")
    # add auxilliary variables to the map
    for i in range(len(clauses)):
        clause = clauses[i]
        for literal in clause.strip().split(" "):
            if "!" in literal:
                # print(literal)
                var_name = literal.split("!")[1].replace(")", "")
                next_available_auxilliary_var = original_var_count + len(auxilliary_map) + 1
                if (var_name, input_file) not in auxilliary_map:
                    auxilliary_map[(var_name, input_file)] = next_available_auxilliary_var
                else:
                    next_available_auxilliary_var = auxilliary_map[(var_name, input_file)]
                # Use regex to match k!var_name as a whole word to avoid partial matches
                clause = re.sub(r'\bk!' + var_name + r'\b', f"aux_{next_available_auxilliary_var}", clause)
        clauses[i] = clause
    return clauses

def parse_interpolant_cnf_to_dimacs(input_file,output_file=None):
    """Parse a CNF list from a file or string."""
    print("Parsing CNF list from file:", input_file)
    clauses = []
    with open(input_file, 'r') as f:
        lines = f.readlines()
    reading_line=""
    for i in range(len(lines)):
        line = lines[i]
        line = line.strip()
        if reading_line:
            reading_line += f" {line}"
            if line.endswith(")"):
                reading_line = reading_line[:-1]
                reading_line = reading_line.replace("Or(", "")
                reading_line = reading_line.replace(",", "")
                reading_line = reading_line.strip()
                clauses.append(reading_line)
                # print(f"reading_line: {reading_line}")
                reading_line = ""
                continue
            continue
        if not line:
            continue
        if line.startswith("Or("):
            if line.endswith(")"):
                line = line[:-1]
                line = line.replace("Or(", "")
                line = line.strip()
                line = line.replace(",", "")
                clauses.append(line)
            elif line.endswith(","):
                reading_line = line
            continue
        
        if line.startswith('Not('):
            # Handle negated variables
            var = line[4:-1].strip()  # Extract variable name from Not(var)
            clauses.append(f"-{var}")
        else:
            # Handle positive variables
            clauses.append(line)
            
    header, var_mapping, dimacs_clauses = convert_to_dimacs(clauses)
    if output_file:
        with open(output_file, 'w') as f:
            f.write(header + "\n")
            for mapping in var_mapping:
                f.write(mapping + "\n")
            for clause in dimacs_clauses:
                f.write(clause + "\n")
    return header, dimacs_clauses

def ComputeCorrelation(SolvingTimeMap,ProofDoorSizeMap,NameLeft="SolvingTime",NameRight="ProofDoorSize"):
    # Compute the correlation between the proof door size and the solving time
    # Use the Pearson correlation coefficient
    
    # Extract keys that exist in both maps
    common_keys = [key for key in SolvingTimeMap if key in ProofDoorSizeMap]
    # show key comparison in detail
    # for key in ProofDoorSizeMap:
    #     if key not in SolvingTimeMap:
    #         print(f"{key} not in SolvingTimeMap")
    # for key in SolvingTimeMap:
    #     if key not in ProofDoorSizeMap:
    #         print(f"{key} not in ProofDoorSizeMap")
    print(f"{NameRight} keys: {len(ProofDoorSizeMap)}")
    # print(ProofDoorSizeMap)
    # for key in ProofDoorSizeMap:
    #     print(f"{key}: {ProofDoorSizeMap[key]}")
    print(f"{NameLeft} keys: {len(SolvingTimeMap)}")
    print(f"common_keys: {len(common_keys)}")
    if not common_keys:
        print("No common keys found between ProofDoorSizeMap and SolvingTimeMap")
        return None
    
    # Extract the values for common keys
    proof_door_sizes = [ProofDoorSizeMap[key] for key in common_keys]
    solving_times = [SolvingTimeMap[key] for key in common_keys]
    for key in common_keys:
        print(f"{key}: {ProofDoorSizeMap[key]} {SolvingTimeMap[key]}")
    # Convert to numpy arrays
    proof_door_sizes = np.array(proof_door_sizes)
    solving_times = np.array(solving_times)
    # print(proof_door_sizes)
    # print(solving_times)
    print(f"{NameRight} size: {len(ProofDoorSizeMap)}")
    print(f"{NameLeft} size: {len(SolvingTimeMap)}")
    print(f"{NameRight} size with common keys: {len(proof_door_sizes)}")
    print(f"{NameLeft} size with common keys: {len(solving_times)}")
    # Calculate Pearson correlation coefficient
    correlation, p_value = pearsonr(proof_door_sizes, solving_times)
    
    print(f"Pearson correlation coefficient: {correlation}")
    print(f"P-value: {p_value}")
    
    return {
        "correlation": correlation,
        "p_value": p_value,
        "sample_size": len(common_keys)
    }

def GetData(folder,name, use_cache = False, bit=None):
    file_name = f'{folder}*{name}.*log'
    cache_name = f'{folder}/{name}.solverCache.json'
    log_files = glob.glob(file_name)
    file_counted = 0
    print(f'{file_name} matched {len(log_files)}')
    if len(log_files) == 0 and not use_cache:
        return None,None,None,None
    
    data_for_this_solver = []
    sum_time = 0.0
    instance_mem_map = {}
    data_for_this_solver,instance_time_map,par2 = [],{},-1
    if use_cache and os.path.isfile(cache_name):
        with open(cache_name, "r") as file:
            result_table = json.load(file)
            data_for_this_solver = result_table["data"]
            instance_time_map = result_table["map"]
            par2 = result_table["par2"]
            instance_mem_map = {}
            # instance_mem_map = result_table["mem"]
    else:
        for filename in tqdm(log_files):
            basename = os.path.basename(filename)
            if bit:
                if f"bits_{bit}." not in basename:
                    continue
            file_counted += 1
            key = basename
            solved = False
            
            with open(filename, 'rb') as file:
                # print(f"processing {filename}")
                file.seek(0, 2)
                position = file.tell()
                line = b''
                linecnt=0
                phase=0 # 0 for time, 1 for mem
                while position >= 0 and linecnt <= 500:        
                    # print(linecnt)
                    file.seek(position)
                    char = file.read(1)
                    if char == b'\n' and line:
                        linecnt+=1
                        decoded_line = line.decode('utf-8')
                        if "raising signal" in decoded_line:
                            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!! {filename}")
                            continue
                            # break
                        if "mylog" in decoded_line:
                            continue
                        if phase ==1:
                            if "maximum-resident-set-size:" in decoded_line:
                                match = re.search(r'(\d*)\s+MB', decoded_line)
                                if match:
                                    time = float(match.group(1))
                                    instance_mem_map[key] = time
                                    break
                            
                            break
                        if "process-time" in decoded_line or "total process time" in decoded_line:
                            match = re.search(r'(\d+\.?\d*)\s+seconds', decoded_line) or re.search(r'total process time[^:]*:\s*([0-9]+(?:\.[0-9]+)?)\s*seconds', decoded_line)
                            if match:
                                # print(basename)
                                time = float(match.group(1))
                                sum_time += time
                                solved = True
                                data_for_this_solver.append(time)
                                instance_time_map[key] = time
                                phase = 1
                            
                        if "CPU time" in decoded_line in decoded_line:
                            match = re.search(r'CPU time[^:]*:\s*([0-9]+(?:\.[0-9]+)?)\s*s', decoded_line)
                            if match:
                                # print(basename)
                                time = float(match.group(1))
                                sum_time += time
                                solved = True
                                data_for_this_solver.append(time)
                                instance_time_map[key] = time
                                phase = 1
                        line = b''
                    else:
                        line = char + line
                    position -= 1
                if not solved:
                    sum_time += 10000.0 
                    # sum_time += 5000.0 
        
        if file_counted > 0:
            # print(f"par2 calculatedby {sum_time}/{file_counted}")
            par2 = sum_time / file_counted
        else:
            par2 = None
            
        with open(cache_name, "w") as file:
            result_table = {}
            result_table["data"] = data_for_this_solver
            result_table["map"] = instance_time_map
            result_table["par2"] = par2
            result_table["mem"] = instance_mem_map
            json.dump(result_table, file)
    if not bit:
        print(f"Par2 {par2}, #solved {len(data_for_this_solver)}")
    return data_for_this_solver,instance_time_map,par2,instance_mem_map

def PolynomialRegression(x_dict,y_dict,degree=2):
    common_keys = [key for key in x_dict if key in y_dict]
    x = [x_dict[key] for key in common_keys]
    y = [y_dict[key] for key in common_keys]
    # Fit a polynomial of degree 2 to the data
    coefficients = np.polyfit(x, y, degree)
    # Create a polynomial function
    polynomial = np.poly1d(coefficients)
    
    # Generate fitted values
    y_pred = polynomial(x)

    # Evaluate fit quality
    r2 = r2_score(y, y_pred)
    mse = mean_squared_error(y, y_pred)

    print(f"Polynomial coefficients:\n{coefficients}")
    print(f"R² score: {r2:.4f}")
    print(f"Mean Squared Error: {mse:.4f}")
    print(f"Size of common keys: {len(common_keys)}")
    return 
    

def read_smt2_file(filename):
    # Parse SMT2 file
    solver = Solver()
    formulas = parse_smt2_file(filename)
    # The parse_smt2_file function doesn't directly return declarations
    # We need to parse the file separately to get declarations
    
    # Read the file content
    with open(filename, 'r') as file:
        content = file.read()
    
    # Extract declarations using string parsing
    declarations = []
    for line in content.split('\n'):
        if line.startswith('(declare-const'):
            # Extract variable name from declaration
            declarations.append(line)
    
    print(f"Found {len(declarations)} variable declarations")
    asserts = []
    print(f"Found {len(formulas)} formulas")
    for f in formulas:
        if is_and(f):
            asserts.append(f)
    assert1 = asserts[0]
    assert2 = asserts[1]

    # if len(asserts) != 2:
    #     print("Error: SMT2 file must contain exactly 2 asserts")
    #     sys.exit(1)
        
    return assert1, assert2, declarations

def read_interpolant(filename, definitions):
    # Skip first line of interpolant file
    with open(filename) as f:
        next(f)  # Skip first line
        interpolant_str = f.read()
    # Check if the interpolant string starts with "(interpolants" and replace it with "(assert"
    if interpolant_str.startswith("(interpolants"):
        interpolant_str = "(assert" + interpolant_str[13:]
    # print(interpolant_str[0:-2])
    # Remove the last ")" from the interpolant string
    # if interpolant_str.endswith(")"):
    # interpolant_str = interpolant_str[:-2]
    # print(interpolant_str)
    # Parse as SMT2 formula    
    input = ""
    for d in definitions:
        input += d + "\n"
    input += interpolant_str
    # print(input)
    # print(parse_smt2_string(input))
    formula = parse_smt2_string(input)[0]
    return formula

def to_pure_smt2(smt_file_path):
    # read the smt file
    with open(smt_file_path, 'r') as file:
        lines = file.readlines()
        content = ""
        start_removed = False
        ignore_first_and_flag = False
        for line in lines:
            if "(compute-interpolant" in line and not start_removed:
                # Replace compute-interpolant with assert
                content += line.replace("(compute-interpolant", "(assert")
                start_removed = True
                continue
            if "(and" in line:
                if ignore_first_and_flag:
                    content += line.replace("(and", ")\n (assert \n (and")
                    continue
                else:
                    ignore_first_and_flag = True
                    content += line
            else:
                content += line
    return content
                
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