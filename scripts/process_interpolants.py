import os
from count_interpolant_lines import count_lines
from count_interpolant_byz3 import count_lines_byz3
import glob
import json         
import re
from tqdm import tqdm
import argparse
import numpy as np
from scipy.stats import pearsonr
from utils.process_cnf import compute_cnf_size_for_category

def process_interpolants(k_path,to_cnf=False):
    interpolants_dir = f"ProofDoorBenchmark/interpolants/{k_path}"
    smts_dir = f"ProofDoorBenchmark/smts/{k_path}"
    results_map = {}
    if not os.path.exists(interpolants_dir):
        print(f"Error: Directory '{interpolants_dir}' not found.")
        return
    
    # Get all files in the directory
    files = [f for f in os.listdir(interpolants_dir) if f.endswith('.interpolant')]
    
    if not files:
        print(f"No .interpolant files found in '{interpolants_dir}'")
        return
    
    print("File\t\t\tSize")
    print("-" * 40)
    
    for file in sorted(files):
        smt_path = os.path.join(smts_dir, file.replace('.interpolant', '.smt2'))
        file_path = os.path.join(interpolants_dir, file)
        # line_count, let_count = count_lines_byz3(file_path)
        # if line_count == 0 and let_count == 0:
        #     continue
        
        # proofdoor_size = line_count + let_count - 3
        proofdoor_size = count_lines_byz3(file_path,smt_path,to_cnf)
        print(f"{file}\t{proofdoor_size}")
        results_map[file] = proofdoor_size
    
    return results_map

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

def ComputeCorrelation(SolvingTimeMap,ProofDoorSizeMap):
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
    print(f"ProofDoorSizeMap keys: {len(ProofDoorSizeMap)}")
    # print(ProofDoorSizeMap)
    # for key in ProofDoorSizeMap:
    #     print(f"{key}: {ProofDoorSizeMap[key]}")
    print(f"SolvingTimeMap keys: {len(SolvingTimeMap)}")
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
    print(f"ProofDoorSizeMap: {len(ProofDoorSizeMap)}")
    print(f"SolvingTimeMap: {len(SolvingTimeMap)}")
    print(f"proof_door_sizes: {len(proof_door_sizes)}")
    print(f"solving_times: {len(solving_times)}")
    # Calculate Pearson correlation coefficient
    correlation, p_value = pearsonr(proof_door_sizes, solving_times)
    
    print(f"Pearson correlation coefficient: {correlation}")
    print(f"P-value: {p_value}")
    
    return {
        "correlation": correlation,
        "p_value": p_value,
        "sample_size": len(common_keys)
    }
    
def ComputeCNFvsInterpolantSizeRatio(CNFMap,InterpolantMap):
    # Compute the ratio of the size of the CNF to the size of the interpolant
    # Use the Pearson correlation coefficient
    common_keys = [key for key in CNFMap if key in InterpolantMap]
    cnf_sizes = [CNFMap[key] for key in common_keys]
    interpolant_sizes = [InterpolantMap[key] for key in common_keys]
    print(f"Average interpolant size: {sum(interpolant_sizes) / len(interpolant_sizes)}")
    print(f"Average matched CNF size: {sum(cnf_sizes) / len(cnf_sizes)}")
    print(f"number of matched instances: {len(common_keys)}")
    ratio = [cnf_sizes[i] / interpolant_sizes[i] for i in range(len(common_keys))]
    print(ratio)
    return ratio
    
if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process interpolants')
    parser.add_argument('--UseCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--UseLogCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--UseCNFCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--ProcessLogOnly', action='store_true', help='Use cached data if available')
    parser.add_argument('--ProcessInterpolantOnly', action='store_true', help='Use cached data if available')
    parser.add_argument('--SkipInterpolant', action='store_true', help='Use cached data if available')
    parser.add_argument('--CompareCombinedInstances', action='store_true', help='Use cached data if available')
    parser.add_argument('--Solver', type=str, default='cadical', help='SAT solver to use')
    parser.add_argument('--K', type=int, default=80, help='K value')
    parser.add_argument('--EstimatePDSize', action='store_true', help='Estimate PD size')
    parser.add_argument('--FormulaCategory', type=str, default='linear', help='Formula category')
    parser.add_argument('--CheckCNFvsInterpolantSizeRatio', action='store_true', help='Check CNF vs Interpolant Size Ratio')
    parser.add_argument('--ToCNF', action='store_true', help='Convert to CNF')
    parser.add_argument('--CheckInterpolantCNFSizeCorrelation', action='store_true', help='Check Interpolant CNF size correlation')
    
    # Parse arguments
    args = parser.parse_args()
    use_cache = args.UseCache 
    solver = args.Solver
    check_cnf_vs_interpolant_size_ratio = args.CheckCNFvsInterpolantSizeRatio
    K = args.K
    formula_category = args.FormulaCategory
    if args.ProcessInterpolantOnly:
        results_map = process_interpolants(K,args.ToCNF)
        with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'w') as f:
            for file, size in results_map.items():
                f.write(f"{file}\t{size}\n")
        exit()
        
    # If use_cache is True, try to read the interpolants map from file
    if use_cache or args.SkipInterpolant and os.path.exists('./ProofSizeMap/data.json'):
        print("Using cached interpolant sizes from file")
        results_map = {}
        data = json.load(open('./ProofSizeMap/data.json', 'r'))
        for key, value in data.items():
            k_value = key.split('.')[1]
            if k_value != str(K):
                continue
            results_map[key] = value
        # with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'r') as f:
        #     for line in f:
        #         parts = line.strip().split('\t')
        #         if len(parts) == 2:
        #             file_name, size_tuple = parts
        #             # Parse the tuple string "(90, 'UNSAT')" to get just the size
        #             size = int(size_tuple.split(',')[0].strip('('))
        #             results_map[file_name] = size
        if results_map:
            print("Loaded cached interpolant sizes")
    elif not args.ProcessLogOnly:
        results_map = process_interpolants(K,args.ToCNF)
    # print(results_map)
    
    # Write results to a file
    if not args.ProcessLogOnly and not args.UseCache:
        with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'w') as f:
            for file, size in results_map.items():
                f.write(f"{file}\t{size}\n")
    
    cadical_data,cadical_map,cadical_par2,cadical_mem = GetData(f"./ProofDoorBenchmark/{formula_category}/{K}/", solver, args.UseLogCache or use_cache)

    # print(cadical_map)
            
    # Rewrite cadical_map with keys' first part before "."
    rewritten_cadical_map = {}
    for key, value in cadical_map.items():
        # Extract the first part of the key before the first "."
        key_parts = key.split('.')
        new_key = key_parts[0]
        rewritten_cadical_map[new_key] = value
    
    if args.CompareCombinedInstances:
        combined_data,combined_map,combined_par2,combined_mem = GetData(f"./ProofDoorBenchmark/combined/{formula_category}/", solver, False)
        # print(cadical_map)
        # print(combined_map)
        for key in combined_map:
            rewritten_key = key.split('.')[0]
            if rewritten_key in rewritten_cadical_map:
                print(f"{key} {combined_map[key]} {rewritten_cadical_map[rewritten_key]}")
        exit()
    # Rewrite results_map (interpolants map) with keys' first part before "."
    proof_door_size_map = {}
    interpolant_size_map = results_map
    skip_keys = []
    max_interpolant_size = {}
    for key, value in results_map.items():
        key_parts = key.split('.')
        new_key = key_parts[0]
        max_interpolant_size[new_key] = max(max_interpolant_size.get(new_key, 100), value[0])
    
    for key, value in results_map.items():
        # Extract the first part of the key before the first "."
        if key in skip_keys:
            continue
        key_parts = key.split('.')
        new_key = key_parts[0]
        k_value = key_parts[1]
        value=value[0]
        if value < 0:
            if args.EstimatePDSize:
                value = max_interpolant_size[new_key]
            else:
                skip_keys.append(key)
                # print(f"Warning: {key} interpolants exists only for parts")
                continue
            # if new_key in proof_door_size_map:
            #     skip_keys.append(key)
            #     print(f"Warning: {key} interpolants exists only for parts")
            # continue
        if new_key not in proof_door_size_map:
            proof_door_size_map[new_key] = value
        else:
            proof_door_size_map[new_key] += value
            
    if args.CheckInterpolantCNFSizeCorrelation:
        print("-" * 100)
        print(f"Checking Interpolant CNF size correlation for K={K}")
        cnf_sizes = compute_cnf_size_for_category(formula_category,K,args.UseCNFCache or use_cache)
        print(f"CNF sizes: {len(cnf_sizes)}")
        print(f"Average CNF size: {sum(cnf_sizes.values()) / len(cnf_sizes)}")
        interpolant_sizes_for_category = {}
        cnf_sizes_for_correlation = []
        proofdoor_size_map_for_category = {}
        
        # print(f"Interpolant sizes: {(interpolant_size_map)}")
        # print(f"CNF sizes: {(cnf_sizes)}")
        for key, value in interpolant_size_map.items():
            if value[0] < 0:
                continue
            base_name = key.split('.')[0]
            if base_name in cnf_sizes:
                if base_name not in proofdoor_size_map_for_category.keys():
                    proofdoor_size_map_for_category[base_name] = []
                # print(f"{key} {value[0]} {cnf_sizes[base_name]}")
                interpolant_sizes_for_category[key] = value[0]
                cnf_sizes_for_correlation.append(cnf_sizes[base_name])  
                proofdoor_size_map_for_category[base_name].append(value[0])
        # interpolant_sizes_for_category = list(interpolant_sizes_for_category.values())
        interpolant_sizes_for_category_list = []
        for key, value in interpolant_sizes_for_category.items():
            interpolant_sizes_for_category_list.append(value)
        cnf_sizes_for_correlation = np.array(cnf_sizes_for_correlation)
        interpolant_sizes_for_category_list = np.array(interpolant_sizes_for_category_list   )
        correlation, p_value = pearsonr(interpolant_sizes_for_category_list, cnf_sizes_for_correlation)
        print(f"Correlation between interpolant size and cnf size: {correlation}")
        print(f"P-value: {p_value}")
        print(f"total cnf number: {len(cnf_sizes)}")
        print(f"total interpolant number: {len(interpolant_sizes_for_category)}")
        print(f"total proofdoor number: {len(proofdoor_size_map_for_category)}")    
        for key in interpolant_sizes_for_category.keys():
            base_name = key.split('.')[0]
            print(f"{base_name} {interpolant_sizes_for_category[key]} {cnf_sizes[base_name]}")
        # correlation of average size of interpolants in a proofdoor to cnf size
        average_interpolant_size_for_category = {}
        cnf_sizes_for_correlation = []
        for key, value in proofdoor_size_map_for_category.items():
            if len(value) == 0:
                continue
            average_interpolant_size_for_category[key] = (sum(value) / len(value), cnf_sizes[key])
            # cnf_sizes_for_correlation.append(cnf_sizes[key])
        average_interpolant_size_for_category_list = []
        cnf_sizes_for_correlation_list = []
        for key, value in average_interpolant_size_for_category.items():
            average_interpolant_size_for_category_list.append(value[0])
            cnf_sizes_for_correlation_list.append(value[1]  )
        average_interpolant_size_for_category_list = np.array(average_interpolant_size_for_category_list)
        cnf_sizes_for_correlation_list = np.array(cnf_sizes_for_correlation_list)
        correlation, p_value = pearsonr(average_interpolant_size_for_category_list, cnf_sizes_for_correlation_list)
        # check if the data used for pearsonr are correctly matched according to basename
        
        print(f"Correlation between average interpolant size and cnf size: {correlation}")
        print(f"P-value: {p_value}")
        # print(average_interpolant_size_for_category)
        # print(cnf_sizes_for_correlation)
        # print(cnf_sizes)
        # print(interpolant_size_map)
        print("-" * 100)
        
        # exit()
        
        
    if check_cnf_vs_interpolant_size_ratio:
        print("-" * 100)
        print(f"Checking CNF vs Interpolant Size Ratio for K={K}")
        cnf_path = f"ProofDoorBenchmark/{formula_category}/{K}/"
        cnf_sizes = {}
        if (use_cache or args.UseCNFCache) and os.path.exists(f'{cnf_path}/cnfs_sizes.json'):
            cnf_sizes = json.load(open(f'{cnf_path}/cnfs_sizes.json', 'r'))
        else:
            for file in os.listdir(cnf_path):
                if file.endswith('.cnf'):
                    cnf_sizes[file] = os.path.getsize(os.path.join(cnf_path, file))
            json.dump(cnf_sizes, open(f'{cnf_path}/cnfs_sizes.json', 'w'))
        print(f"CNF sizes: {len(cnf_sizes)}")
        print(f"Average CNF size: {sum(cnf_sizes.values()) / len(cnf_sizes)}")
        rewritten_cnf_map = {}
        for key, value in cnf_sizes.items():
            key_parts = key.split('.')
            new_key = key_parts[0]
            rewritten_cnf_map[new_key] = value
        print(f"Rewritten cnf map: {len(rewritten_cnf_map)}")
        ratio = ComputeCNFvsInterpolantSizeRatio(rewritten_cnf_map, proof_door_size_map)
        print(f"CNF vs Interpolant Size Ratio: {ratio}")
        print(f"Average ratio: {sum(ratio) / len(ratio)}")
        print("-" * 100)
        
        
    print(f"Rewritten cadical map: {len(rewritten_cadical_map)}")
    # print(rewritten_cadical_map)
    print(f"Rewritten interpolants map: {len(proof_door_size_map)}")
    # print(proof_door_size_map)
    ComputeCorrelation(rewritten_cadical_map, proof_door_size_map)
    print(f"Par2 score: {cadical_par2}")
    