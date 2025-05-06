import os
import re
import glob
import json
from tqdm import tqdm
from collections import defaultdict
from scipy.stats import pearsonr
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np

def RewriteMap(InMap):
    OutMap = {}
    for key, value in InMap.items():
        key_parts = key.split('.')
        new_key = key_parts[0]
        OutMap[new_key] = value
    return OutMap

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
    return polynomial